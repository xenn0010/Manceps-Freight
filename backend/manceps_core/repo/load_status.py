"""Load status moves and the load timeline.

Two entry points move a load:
- `transition`: a direct request (API or import). It refuses every move the machine reserves for approvals.
- `move_by_approval`: called only by the approvals module while applying an approval. It refuses to act unless the
  approval was decided `approve` by a human user principal and its kind is the one the move needs.
Every move is a conditional update on the current status (two writers cannot both move the same load), appends a
`load_events` row, emits `load.status_changed` and writes an audit record.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument

from .. import events
from ..loads import machine
from ..loads.views import mapping
from ..mongo import Doc, MongoDb
from .errors import Conflict, Invalid
from .load_fields import bookable_carrier
from .loads import LOAD_EVENTS, LOADS, REF_TYPE, get_load, record_event
from .store import LIVE, WriteContext, ensure_auditable, ref_of

STATUS_EVENT = "load.status_changed"
REASON_MAX = 500
HUMAN_KIND = "user"
APPROVE = "approve"
APPLYING_STATUSES = frozenset({"approved", "apply_failed"})
KIND_FOR_TARGET: Mapping[str, str] = {
    machine.APPROVED: machine.ACCEPT_RATE_KIND, machine.BOOKED: machine.ACCEPT_RATE_KIND,
    machine.CANCELLED: machine.CANCEL_KIND, machine.RATECON_RECEIVED: machine.RATECON_KIND,
}


def _require_carrier(db: MongoDb, load: Mapping[str, Any], target: str) -> None:
    """Refuse a contracted status without a live, bookable carrier of this firm (bring-your-own-carrier).

    Args:
        db: Firm database.
        load: The load.
        target: Wanted status.

    Raises:
        Conflict: 409 carrier_required.
    """
    if target not in machine.NEEDS_CARRIER:
        return
    try:
        if load.get("carrier_id") is None:
            raise Invalid("carrier_id", "no carrier")
        bookable_carrier(db, load["carrier_id"])
    except Invalid as exc:
        raise Conflict("carrier_required", "assign an active carrier of this firm before booking this load",
                       {"to": target}) from exc


def _require_ratecon(load: Mapping[str, Any], target: str) -> None:
    """Refuse dispatching before the rate confirmation was approved.

    Args:
        load: The load.
        target: Wanted status.

    Raises:
        Conflict: 409 approval_required (approve_ratecon).
    """
    if target in machine.NEEDS_RATECON_APPROVAL and not load.get("ratecon_approval"):
        raise Conflict("approval_required", "the rate confirmation needs an approved approve_ratecon first",
                       {"approval_kind": machine.RATECON_KIND, "to": target})


def _move(db: MongoDb, ctx: WriteContext, load: Doc, target: str, extra: Mapping[str, Any],
          trail: Mapping[str, Any]) -> Doc:
    """Move a load from its loaded status to `target` with one conditional update, then record it.

    Args:
        db: Firm database.
        ctx: Writer.
        load: The load as loaded.
        target: New status.
        extra: Extra fields to set with the status.
        trail: Details for the timeline (reason, approval id).

    Returns:
        The load after the move.

    Raises:
        Conflict: 409 status_changed if another writer moved it first.
        NotFound: If it vanished.
    """
    source = str(load["status"])
    now = ctx.now()
    ensure_auditable(extra, trail)
    after = db[LOADS].find_one_and_update(
        {"_id": load["_id"], "status": source, **LIVE},
        {"$set": {**extra, "status": target, "status_changed_at": now, "updated_at": now}},
        return_document=ReturnDocument.AFTER)
    if after is None:
        get_load(db, load["_id"])
        raise Conflict("status_changed", "the load changed status meanwhile; reload and try again",
                       {"from": source, "to": target})
    record_event(db, ctx, after, "status_changed", {"from": source, "to": target, **trail})
    events.emit(db, STATUS_EVENT, ref_of(REF_TYPE, after),
                {"load_id": str(after["_id"]), "ref": after.get("ref"), "from": source, "to": target}, ctx.clock)
    ctx.audit(db, "load.transition", ref_of(REF_TYPE, after), load, after)
    return after


def _reason_fields(target: str, reason: str | None) -> dict[str, Any]:
    """Fields recording why a load closed.

    Args:
        target: New status.
        reason: Reason text, or None.

    Returns:
        Fields to set.
    """
    if reason is None:
        return {}
    fields: dict[str, Any] = {"status_reason": reason}
    if target == machine.CANCELLED:
        fields["cancelled_reason"] = reason
    return fields


def clean_reason(reason: str | None) -> str | None:
    """Validate a free-text reason.

    Args:
        reason: Raw reason.

    Returns:
        The trimmed reason, or None.

    Raises:
        Invalid: If too long.
    """
    if reason is None or not reason.strip():
        return None
    if len(reason.strip()) > REASON_MAX:
        raise Invalid("reason", f"reason is longer than {REASON_MAX} characters")
    return reason.strip()


def transition(db: MongoDb, ctx: WriteContext, load_id: Any, target: str, reason: str | None = None) -> Doc:
    """Move a load directly (never into approved or booked, never cancelling a contracted load).

    Args:
        db: Firm database.
        ctx: Writer.
        load_id: Load id.
        target: Wanted status.
        reason: Optional reason (stored for cancelled, declined and tonu).

    Returns:
        The load after the move.

    Raises:
        NotFound: If the load is not live.
        Conflict: illegal_transition, approval_required, carrier_required or status_changed.
        Invalid: On a too-long reason.
    """
    load = get_load(db, load_id)
    source = str(load.get("status"))
    if target not in machine.TRANSITIONS:
        raise Invalid("to", "unknown status")
    machine.check_direct(source, target)
    _require_carrier(db, load, target)
    _require_ratecon(load, target)
    cleaned = clean_reason(reason)
    return _move(db, ctx, load, target, _reason_fields(target, cleaned), {"reason": cleaned} if cleaned else {})


def check_human_approval(approval: Mapping[str, Any], target: str) -> None:
    """Refuse to act on anything but an approval a human decided `approve`, of the kind the move needs.

    Args:
        approval: The approval document.
        target: Wanted load status.

    Raises:
        Conflict: 409 approval_not_valid.
    """
    decided_by = mapping(approval.get("decided_by"))
    human = decided_by is not None and decided_by.get("kind") == HUMAN_KIND
    if (approval.get("decision") != APPROVE or approval.get("status") not in APPLYING_STATUSES or not human
            or approval.get("kind") != KIND_FOR_TARGET.get(target)):
        raise Conflict("approval_not_valid", "this move needs an approval decided by a person",
                       {"to": target, "approval_id": str(approval.get("_id"))})


def move_by_approval(db: MongoDb, ctx: WriteContext, load_id: Any, target: str, approval: Mapping[str, Any],
                     extra: Mapping[str, Any] | None = None) -> Doc:
    """Move a load as part of applying an approval (the only way into approved and booked).

    Args:
        db: Firm database.
        ctx: Writer (the approval).
        load_id: Load id.
        target: Wanted status.
        approval: The approval being applied.
        extra: Extra fields to set with the status.

    Returns:
        The load after the move.

    Raises:
        NotFound: If the load is not live.
        Conflict: approval_not_valid, illegal_transition, carrier_required or status_changed.
    """
    check_human_approval(approval, target)
    load = get_load(db, load_id)
    machine.require_legal(str(load.get("status")), target)
    _require_carrier(db, load, target)
    fields = dict(extra or {})
    if target == machine.BOOKED:
        fields.update({"booked_at": ctx.now(), "accepted_approval_id": str(approval["_id"])})
    return _move(db, ctx, load, target, fields, {"approval_id": str(approval["_id"])})


def list_events(db: MongoDb, load_id: Any, after: ObjectId | None, limit: int) -> list[Doc]:
    """List a load's timeline, oldest first.

    Args:
        db: Firm database.
        load_id: Load id.
        after: Cursor id.
        limit: Page size.

    Returns:
        Up to limit + 1 entries.

    Raises:
        NotFound: If the load is not live.
    """
    load = get_load(db, load_id)
    query: dict[str, Any] = {"load_id": load["_id"]}
    if after is not None:
        query["_id"] = {"$gt": after}
    return list(db[LOAD_EVENTS].find(query, limit=limit + 1).sort([("_id", 1)]))

