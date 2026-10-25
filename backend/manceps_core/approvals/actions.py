"""What an approved approval does. Every action is idempotent: applying the same approval twice changes nothing.

Each action runs only after a person decided `approve` (checked again by `load_status.move_by_approval` for every
status move). Preconditions are checked before the first write, so a refused action leaves the subject unchanged
and the approval is marked `apply_failed` (a later decision retry re-runs it).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ..loads import machine
from ..mongo import Doc, MongoDb
from ..repo import carriers
from ..repo.errors import Conflict
from ..repo.load_fields import bookable_carrier
from ..repo.load_status import move_by_approval, record_event
from ..repo.loads import LOADS, REF_TYPE, get_load
from ..repo.store import WriteContext, update

Action = Callable[[MongoDb, WriteContext, Doc], dict[str, Any]]


def _payload(approval: Mapping[str, Any]) -> Mapping[str, Any]:
    """Read an approval's stored payload.

    Args:
        approval: Approval document.

    Returns:
        The payload mapping.
    """
    payload = approval.get("payload")
    return payload if isinstance(payload, Mapping) else {}  # pyright: ignore[reportUnknownVariableType]


def _subject_id(approval: Mapping[str, Any]) -> str:
    """Read an approval's subject id.

    Args:
        approval: Approval document.

    Returns:
        The id text.
    """
    return str(approval["subject_ref"]["id"])


def _result(load: Mapping[str, Any], **extra: Any) -> dict[str, Any]:
    """Describe a load after an action.

    Args:
        load: The load.
        **extra: More fields.

    Returns:
        The apply result.
    """
    return {"load_id": str(load["_id"]), "status": load.get("status"), "rate_cents": load.get("rate_cents"), **extra}


def accept_rate(db: MongoDb, ctx: WriteContext, approval: Doc) -> dict[str, Any]:
    """Set the accepted rate (and carrier), then book the load; on a contracted load, amend its rate.

    Args:
        db: Firm database.
        ctx: Writer (the approval).
        approval: The approval.

    Returns:
        The load's state after the action.

    Raises:
        Conflict: carrier_required, illegal_transition or approval_not_valid.
        Invalid: When the proposed carrier is no longer bookable.
        NotFound: When the load is gone.
    """
    payload = _payload(approval)
    load = get_load(db, _subject_id(approval))
    status = str(load.get("status"))
    if status in machine.CONTRACTED and load.get("accepted_approval_id") == str(approval["_id"]):
        return _result(load, already_applied=True)
    carrier_id = payload.get("carrier_id", load.get("carrier_id"))
    if carrier_id is None:
        raise Conflict("carrier_required", "assign an active carrier of this firm before booking this load")
    bookable_carrier(db, carrier_id)
    changes = {"rate_cents": payload["rate_cents"], "carrier_id": str(carrier_id)}
    if status in machine.CONTRACTED:
        if status in machine.TERMINAL or status == machine.INVOICED:
            raise Conflict("illegal_transition", "this load can no longer change its rate", {"from": status})
        load = update(db, ctx, LOADS, REF_TYPE, load, changes)
        record_event(db, ctx, load, "rate_amended", {"approval_id": str(approval["_id"]), **changes})
        return _result(load, amended=True)
    if status not in {machine.EVALUATING, machine.COUNTERED, machine.APPROVED}:
        raise Conflict("illegal_transition", f"a rate cannot be accepted for a load in {status}",
                       {"from": status, "to": machine.APPROVED})
    load = update(db, ctx, LOADS, REF_TYPE, load, changes)
    record_event(db, ctx, load, "rate_accepted", {"approval_id": str(approval["_id"]), **changes})
    if status != machine.APPROVED:
        load = move_by_approval(db, ctx, load["_id"], machine.APPROVED, approval)
    load = move_by_approval(db, ctx, load["_id"], machine.BOOKED, approval)
    return _result(load)


def approve_ratecon(db: MongoDb, ctx: WriteContext, approval: Doc) -> dict[str, Any]:
    """Record the signed-off Rate Con and move a booked load to ratecon_received.

    Args:
        db: Firm database.
        ctx: Writer (the approval).
        approval: The approval.

    Returns:
        The load's state after the action.

    Raises:
        Conflict: rate_mismatch, illegal_transition or approval_not_valid.
        NotFound: When the load is gone.
    """
    payload = _payload(approval)
    load = get_load(db, _subject_id(approval))
    existing = load.get("ratecon_approval")
    if isinstance(existing, Mapping) and existing.get("approval_id") == str(approval["_id"]):  # pyright: ignore[reportUnknownMemberType]
        return _result(load, already_applied=True)
    if load.get("rate_cents") != payload["rate_cents"]:
        raise Conflict("rate_mismatch", "the Rate Con's rate differs from the load's booked rate",
                       {"load_rate_cents": load.get("rate_cents")})
    record = {"approval_id": str(approval["_id"]), "at": ctx.now(), "rate_cents": payload["rate_cents"],
              "document_ref": payload.get("document_ref")}
    status = str(load.get("status"))
    if status == machine.BOOKED:
        load = move_by_approval(db, ctx, load["_id"], machine.RATECON_RECEIVED, approval, {"ratecon_approval": record})
    elif status == machine.RATECON_RECEIVED:
        load = update(db, ctx, LOADS, REF_TYPE, load, {"ratecon_approval": record})
        record_event(db, ctx, load, "ratecon_approved", {"approval_id": str(approval["_id"])})
    else:
        raise Conflict("illegal_transition", "only a booked load can take a Rate Con", {"from": status})
    return _result(load)


def cancel_load(db: MongoDb, ctx: WriteContext, approval: Doc) -> dict[str, Any]:
    """Cancel a load.

    Args:
        db: Firm database.
        ctx: Writer (the approval).
        approval: The approval.

    Returns:
        The load's state after the action.

    Raises:
        Conflict: illegal_transition or approval_not_valid.
        NotFound: When the load is gone.
    """
    load = get_load(db, _subject_id(approval))
    if load.get("status") == machine.CANCELLED:
        return _result(load, already_applied=True)
    reason = str(_payload(approval)["reason"])
    load = move_by_approval(db, ctx, load["_id"], machine.CANCELLED, approval,
                            {"cancelled_reason": reason, "status_reason": reason})
    return _result(load)


def carrier_terms_change(db: MongoDb, ctx: WriteContext, approval: Doc) -> dict[str, Any]:
    """Write a carrier's fee, floor or agreement through the carrier repository.

    Args:
        db: Firm database.
        ctx: Writer (the approval).
        approval: The approval.

    Returns:
        The carrier id and the fields written.

    Raises:
        NotFound: When the carrier is gone.
        Invalid: When a value no longer passes the carrier rules.
    """
    changes = dict(_payload(approval)["changes"])
    carrier = carriers.update_carrier(db, ctx, _subject_id(approval), changes, allow_sensitive=True)
    return {"carrier_id": str(carrier["_id"]), "fields": sorted(changes)}


ACTIONS: Mapping[str, Action] = {
    "accept_rate": accept_rate,
    "approve_ratecon": approve_ratecon,
    "cancel_load": cancel_load,
    "carrier_terms_change": carrier_terms_change,
}
