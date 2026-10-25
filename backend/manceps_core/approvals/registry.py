"""Approval kinds: what each one proposes, who may decide it, and how its payload is checked.

`always_human` marks kinds that may never be approved by anything but a person deciding in the app: no autonomy
setting, policy or agent path may approve them (founder decision: booking a load and signing a Rate Con always need
the owner). `auto_approvable` is the single switch a future autonomy feature must consult, and it returns False for
these kinds whatever the caller passes. Payload checks run with the repositories' own field rules; the API layer
adds typed models for the schema. The pure action code lives in `actions.py`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from ..loads import machine
from ..loads.money import MAX_RATE_CENTS
from ..mongo import Doc, MongoDb
from ..repo import carriers, fields
from ..repo.errors import Conflict, Invalid
from ..repo.load_fields import bookable_carrier
from ..repo.loads import get_load

OWNER, DISPATCHER = "owner", "dispatcher"
ROLE_RANK: Mapping[str, int] = {"viewer": 1, "dispatcher": 2, "owner": 3}
LOAD, CARRIER = "load", "carrier"
MONEY, CONTRACT, TERMS = "money", "contract", "terms"
DOCUMENT_REF_MAX = 128
REASON_MAX = 500
TERM_FIELDS = frozenset({"dispatch_fee_pct", "rate_floor_per_mile", "agreement_signed"})
AMENDABLE = machine.CONTRACTED - machine.TERMINAL - {machine.INVOICED}
ACCEPTABLE = frozenset({machine.EVALUATING, machine.COUNTERED})

PayloadCheck = Callable[[MongoDb, Doc, Mapping[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class Kind:
    """One approval kind."""

    name: str
    subject_type: str
    required_role: str
    risk: str
    always_human: bool
    check: PayloadCheck


def _only(payload: Mapping[str, Any], allowed: frozenset[str]) -> None:
    """Refuse payload keys a kind does not know.

    Args:
        payload: Raw payload.
        allowed: Known keys.

    Raises:
        Invalid: On an unknown key.
    """
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise Invalid(["payload", unknown[0]], "this field is not part of the proposal")


def _cents(payload: Mapping[str, Any]) -> int:
    """Read a required rate in cents.

    Args:
        payload: Raw payload.

    Returns:
        The rate.

    Raises:
        Invalid: If missing or not a positive whole number of cents.
    """
    value = payload.get("rate_cents")
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= MAX_RATE_CENTS:
        raise Invalid(["payload", "rate_cents"], "rate_cents must be a positive whole number of cents")
    return value


def _text(payload: Mapping[str, Any], name: str, max_len: int, required: bool) -> str | None:
    """Read a payload text field with the shared text rule.

    Args:
        payload: Raw payload.
        name: Field name.
        max_len: Maximum characters.
        required: Refuse a blank value.

    Returns:
        The trimmed text, or None.

    Raises:
        Invalid: If required and blank, or too long (located at payload.<name>).
    """
    try:
        return fields.text(name, payload.get(name), max_len, required=required)
    except Invalid as exc:
        raise Invalid(["payload", name], exc.message) from exc


def _check_accept_rate(db: MongoDb, load: Doc, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Check an accept_rate proposal: the load is being negotiated (or contracted, for an amendment).

    Args:
        db: Firm database.
        load: The load.
        payload: {rate_cents, carrier_id?}.

    Returns:
        The normalized payload.

    Raises:
        Invalid: On a bad rate or carrier.
        Conflict: illegal_transition when the load cannot take a rate now.
    """
    _only(payload, frozenset({"rate_cents", "carrier_id"}))
    clean: dict[str, Any] = {"rate_cents": _cents(payload)}
    if payload.get("carrier_id") is not None:
        clean["carrier_id"] = str(bookable_carrier(db, payload["carrier_id"])["_id"])
    status = str(load.get("status"))
    if status not in ACCEPTABLE | AMENDABLE:
        raise Conflict("illegal_transition", f"a rate cannot be accepted for a load in {status}; evaluate it first",
                       {"from": status, "to": machine.APPROVED})
    return clean


def _check_ratecon(_db: MongoDb, load: Doc, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Check an approve_ratecon proposal: a booked load whose rate equals the Rate Con's.

    Args:
        _db: Firm database.
        load: The load.
        payload: {rate_cents, document_ref?}.

    Returns:
        The normalized payload.

    Raises:
        Invalid: On a bad rate or document reference.
        Conflict: illegal_transition, or rate_mismatch when the Rate Con disagrees with the load.
    """
    _only(payload, frozenset({"rate_cents", "document_ref"}))
    clean: dict[str, Any] = {"rate_cents": _cents(payload)}
    document = _text(payload, "document_ref", DOCUMENT_REF_MAX, False)
    if document is not None:
        clean["document_ref"] = document
    status = str(load.get("status"))
    if status not in {machine.BOOKED, machine.RATECON_RECEIVED} or load.get("ratecon_approval"):
        raise Conflict("illegal_transition", "only a booked load without an approved Rate Con can take one",
                       {"from": status, "to": machine.RATECON_RECEIVED})
    if load.get("rate_cents") != clean["rate_cents"]:
        raise Conflict("rate_mismatch", "the Rate Con's rate differs from the load's booked rate",
                       {"load_rate_cents": load.get("rate_cents")})
    return clean


def _check_cancel(_db: MongoDb, load: Doc, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Check a cancel_load proposal.

    Args:
        _db: Firm database.
        load: The load.
        payload: {reason}.

    Returns:
        The normalized payload.

    Raises:
        Invalid: Without a reason.
        Conflict: illegal_transition when the load cannot be cancelled.
    """
    _only(payload, frozenset({"reason"}))
    reason = _text(payload, "reason", REASON_MAX, True)
    machine.require_legal(str(load.get("status")), machine.CANCELLED)
    return {"reason": reason}


def _check_terms(_db: MongoDb, _carrier: Doc, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Check a carrier_terms_change proposal (consent is never changed here: it has its own ledger).

    Args:
        _db: Firm database.
        _carrier: The carrier.
        payload: {changes: {dispatch_fee_pct?, rate_floor_per_mile?, agreement_signed?}}.

    Returns:
        The normalized payload.

    Raises:
        Invalid: On unknown or bad fields, or no change.
    """
    _only(payload, frozenset({"changes"}))
    changes = payload.get("changes")
    if not isinstance(changes, Mapping) or not changes:
        raise Invalid(["payload", "changes"], "changes must name at least one term")
    raw: Mapping[str, Any] = changes  # pyright: ignore[reportUnknownVariableType]
    unknown = sorted(set(raw) - TERM_FIELDS)
    if unknown:
        raise Invalid(["payload", "changes", unknown[0]], "only fee, floor and agreement go through this approval")
    empty = sorted(name for name, value in raw.items() if value is None)
    if empty:
        raise Invalid(["payload", "changes", empty[0]], "a term cannot be removed through an approval")
    return {"changes": carriers.validate(raw)}


KINDS: Mapping[str, Kind] = {
    "accept_rate": Kind("accept_rate", LOAD, OWNER, MONEY, True, _check_accept_rate),
    "approve_ratecon": Kind("approve_ratecon", LOAD, OWNER, CONTRACT, True, _check_ratecon),
    "carrier_terms_change": Kind("carrier_terms_change", CARRIER, OWNER, TERMS, True, _check_terms),
    "cancel_load": Kind("cancel_load", LOAD, DISPATCHER, CONTRACT, True, _check_cancel),
}


def kind_of(name: str) -> Kind:
    """Look up a kind.

    Args:
        name: Kind name.

    Returns:
        The kind.

    Raises:
        Invalid: For an unknown kind.
    """
    kind = KINDS.get(name)
    if kind is None:
        raise Invalid("kind", f"kind must be one of {', '.join(sorted(KINDS))}")
    return kind


def auto_approvable(name: str, policy_allows: bool) -> bool:
    """The one switch an autonomy feature may consult before approving anything without a person.

    Args:
        name: Kind name.
        policy_allows: What the firm's autonomy settings say.

    Returns:
        False for every always-human kind regardless of policy; otherwise the policy's answer.

    Raises:
        Invalid: For an unknown kind.
    """
    return policy_allows and not kind_of(name).always_human


def load_subject(db: MongoDb, subject_id: Any) -> Doc:
    """Load a load subject.

    Args:
        db: Firm database.
        subject_id: Load id.

    Returns:
        The load.

    Raises:
        NotFound: If it is not a live load of this firm.
    """
    return get_load(db, subject_id)
