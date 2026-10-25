"""Carrier roster: the firm's own owner-operators and their dispatch terms (rules ported from hermes-freight).

Field names, the ObjectId `_id` and the unique, non-sparse `phone` index are the plugin's, so both read the same
documents. Money and contract terms (`SENSITIVE_CARRIER_FIELDS`) need an approval unless the writer may set them
directly (the firm owner); consent is never written here, only through the consent ledger (`consent.py`).

Soft delete and the unique phone index: the plugin's `phone_1` index is unique and not sparse, so a missing phone
counts as null and a second deleted carrier would collide. Deleting therefore moves the real number to
`phone_deleted` and writes a per-record tombstone `"deleted:<id>"` into `phone`. Tombstones are unique, never
normalize to a real number (so phone lookups, including the plugin's consent check, cannot match them), and the
real number is free to be added again as a new carrier.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from bson import ObjectId

from ..mongo import Doc, MongoDb
from . import fields
from .errors import Conflict, Invalid
from .store import WriteContext, get_by_id, insert, list_live, soft_delete, update

CARRIERS = "carriers"
LOADS = "loads"
REF_TYPE = "carrier"
EQUIPMENT_TYPES = frozenset({"dry_van", "reefer", "flatbed", "step_deck", "power_only", "box_truck", "hotshot"})
MAX_FEE_PCT = 25.0
SENSITIVE_CARRIER_FIELDS = frozenset({"dispatch_fee_pct", "rate_floor_per_mile", "consent", "agreement_signed"})
CARRIER_STATUSES = ("onboarding", "active", "paused", "offboarded")
DEFAULT_STATUS = "onboarding"
OFFBOARDED = "offboarded"
DELETED_PHONE_PREFIX = "deleted:"
APPROVAL_KIND = "carrier_terms_change"
CLOSED_LOAD_STATUSES = ("declined", "cancelled", "paid", "tonu")
DUPLICATE_PHONE = ("duplicate_phone", "a carrier with this phone number already exists")
LANE_ENDS = ("origin", "destination")
REQUIRED_ON_UPDATE = frozenset({"phone"})

Rule = Callable[[str, Any], Any]


def _equipment(field: str, value: Any) -> list[str]:
    """Validate equipment types (plugin rule).

    Args:
        field: Field name.
        value: List of equipment names.

    Returns:
        Deduplicated equipment names in the given order.

    Raises:
        Invalid: On an unknown type.
    """
    items = fields.text_list(field, value)
    if set(items) - EQUIPMENT_TYPES:
        raise Invalid(field, f"unknown equipment; allowed: {', '.join(sorted(EQUIPMENT_TYPES))}")
    return list(dict.fromkeys(items))


def _fee(field: str, value: Any) -> float:
    """Validate the dispatch fee percent (plugin rule: 0 < fee <= MAX_FEE_PCT).

    Args:
        field: Field name.
        value: Number.

    Returns:
        The fee.

    Raises:
        Invalid: If out of range or not a number.
    """
    fee = _number(field, value)
    if not 0 < fee <= MAX_FEE_PCT:
        raise Invalid(field, f"{field} must be in (0, {MAX_FEE_PCT}]")
    return fee


def _floor(field: str, value: Any) -> float:
    """Validate the rate floor per mile (plugin rule: positive).

    Args:
        field: Field name.
        value: Number.

    Returns:
        The floor.

    Raises:
        Invalid: If not positive.
    """
    floor = _number(field, value)
    if floor <= 0:
        raise Invalid(field, f"{field} must be positive")
    return floor


def _number(field: str, value: Any) -> float:
    """Read a finite number (booleans are not numbers here).

    Args:
        field: Field name.
        value: Raw value.

    Returns:
        The float.

    Raises:
        Invalid: If it is not a number.
    """
    if isinstance(value, bool) or not isinstance(value, int | float) or value != value:
        raise Invalid(field, f"{field} must be a number")
    return float(value)


def _flag(field: str, value: Any) -> bool:
    """Require a boolean.

    Args:
        field: Field name.
        value: Raw value.

    Returns:
        The boolean.

    Raises:
        Invalid: If it is not a boolean.
    """
    if not isinstance(value, bool):
        raise Invalid(field, f"{field} must be true or false")
    return value


def _lanes(field: str, value: Any) -> list[dict[str, str | None]]:
    """Validate preferred lanes as {origin, destination} pairs (plugin shape).

    Args:
        field: Field name.
        value: List of mappings.

    Returns:
        The lanes.

    Raises:
        Invalid: If a lane is not a mapping or has neither end.
    """
    lanes: list[dict[str, str | None]] = []
    for index, lane in enumerate(_mappings(field, value)):
        ends = {end: fields.text(field, lane.get(end)) for end in LANE_ENDS}
        if not any(ends.values()):
            raise Invalid([field, index], "a lane needs an origin or a destination")
        lanes.append(ends)
    return lanes


def _mappings(field: str, value: Any) -> list[Mapping[str, Any]]:
    """Read a bounded list of mappings.

    Args:
        field: Field name.
        value: Raw list.

    Returns:
        The mappings.

    Raises:
        Invalid: If it is not a list of mappings or is too long.
    """
    if value is None:
        return []
    if not isinstance(value, list | tuple):
        raise Invalid(field, f"{field} must be a list")
    items: list[Any] = list(value)  # pyright: ignore[reportUnknownArgumentType]
    if len(items) > fields.MAX_LIST_ITEMS:
        raise Invalid(field, f"{field} has more than {fields.MAX_LIST_ITEMS} items")
    if not all(isinstance(item, Mapping) for item in items):
        raise Invalid(field, f"{field} items must be objects")
    return items


RULES: Mapping[str, Rule] = {
    "phone": fields.phone,
    "name": fields.text,
    "company": fields.text,
    "mc_number": fields.digits,
    "dot_number": fields.digits,
    "email": fields.email,
    "equipment": _equipment,
    "dispatch_fee_pct": _fee,
    "rate_floor_per_mile": _floor,
    "home_base": fields.text,
    "preferred_lanes": _lanes,
    "avoid": fields.text_list,
    "notes": lambda field, value: fields.text(field, value, fields.MAX_NOTE_CHARS),
    "agreement_signed": _flag,
    "status": lambda field, value: fields.choice(field, value, CARRIER_STATUSES),
    "tags": fields.tags,
    "insurance_expires_at": fields.aware_datetime,
}


def validate(changes: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize carrier fields; a None value is kept (it means "remove" on update).

    Args:
        changes: Proposed field values.

    Returns:
        Cleaned values.

    Raises:
        Invalid: On an unknown field, a required field set to None, or a bad value.
    """
    clean: dict[str, Any] = {}
    for name, value in changes.items():
        rule = RULES.get(name)
        if rule is None:
            raise Invalid(name, "this field cannot be written here")
        if value is None:
            if name in REQUIRED_ON_UPDATE:
                raise Invalid(name, f"{name} cannot be removed")
            clean[name] = None
            continue
        clean[name] = rule(name, value)
    return clean


def check_terms(changes: Mapping[str, Any], allow_sensitive: bool) -> None:
    """Refuse money, contract and consent changes that need an approval, and consent outside the ledger.

    Args:
        changes: Proposed fields.
        allow_sensitive: The writer may set terms directly (firm owner, or an approved request being applied).

    Raises:
        Conflict: 409 approval_required naming the fields and the approval kind.
        Invalid: 422 use_consent_endpoint when consent is sent by a writer allowed to change terms.
    """
    sensitive = sorted(SENSITIVE_CARRIER_FIELDS & set(changes))
    if sensitive and not allow_sensitive:
        raise Conflict("approval_required", "changing a carrier's money, contract or consent terms needs approval",
                       {"approval_kind": APPROVAL_KIND, "fields": sensitive})
    if "consent" in changes:
        raise Invalid("consent", "record consent through POST /v1/carriers/{id}/consent", "use_consent_endpoint")


def create_carrier(db: MongoDb, ctx: WriteContext, values: Mapping[str, Any], allow_sensitive: bool) -> Doc:
    """Add a carrier; the phone is required, normalized and unique within the firm.

    Args:
        db: Firm database.
        ctx: Writer.
        values: Proposed fields.
        allow_sensitive: The writer may set terms directly.

    Returns:
        The stored carrier.

    Raises:
        Conflict: approval_required, or duplicate_phone.
        Invalid: On missing phone or bad values.
    """
    check_terms(values, allow_sensitive)
    if values.get("phone") is None:
        raise Invalid("phone", "phone is required")
    clean = {key: value for key, value in validate(values).items() if value is not None}
    clean.setdefault("status", DEFAULT_STATUS)
    return insert(db, ctx, CARRIERS, REF_TYPE, clean, DUPLICATE_PHONE)


def get_carrier(db: MongoDb, carrier_id: Any) -> Doc:
    """Load a live carrier.

    Args:
        db: Firm database.
        carrier_id: Id text or ObjectId.

    Returns:
        The carrier.

    Raises:
        NotFound: If absent, malformed or deleted.
    """
    return get_by_id(db, CARRIERS, carrier_id, REF_TYPE)


def update_carrier(db: MongoDb, ctx: WriteContext, carrier_id: Any, changes: Mapping[str, Any],
                   allow_sensitive: bool) -> Doc:
    """Change a carrier's fields (None removes an optional field).

    Args:
        db: Firm database.
        ctx: Writer.
        carrier_id: Carrier id.
        changes: Proposed fields.
        allow_sensitive: The writer may set terms directly.

    Returns:
        The updated carrier.

    Raises:
        NotFound: If the carrier is not live.
        Conflict: approval_required, or duplicate_phone.
        Invalid: On bad values or an empty change.
    """
    if not changes:
        raise Invalid("body", "send at least one field to change")
    check_terms(changes, allow_sensitive)
    clean = validate(changes)
    current = get_carrier(db, carrier_id)
    return update(db, ctx, CARRIERS, REF_TYPE, current, clean, DUPLICATE_PHONE)


def has_open_loads(db: MongoDb, carrier_oid: ObjectId) -> bool:
    """Check whether any load assigned to the carrier is still open.

    Args:
        db: Firm database.
        carrier_oid: Carrier id.

    Returns:
        True when a load references the carrier (by ObjectId or its hex) outside the closed statuses.
    """
    query = {"carrier_id": {"$in": [carrier_oid, str(carrier_oid)]}, "status": {"$nin": list(CLOSED_LOAD_STATUSES)}}
    return db[LOADS].count_documents(query, limit=1) > 0


def delete_carrier(db: MongoDb, ctx: WriteContext, carrier_id: Any) -> Doc:
    """Offboard a carrier: soft delete, phone tombstone (see module docstring), status offboarded.

    Args:
        db: Firm database.
        ctx: Writer.
        carrier_id: Carrier id.

    Returns:
        The deleted carrier.

    Raises:
        NotFound: If the carrier is not live.
        Conflict: carrier_has_open_loads.
    """
    current = get_carrier(db, carrier_id)
    if has_open_loads(db, current["_id"]):
        raise Conflict("carrier_has_open_loads", "this carrier still has open loads")
    tombstone = {"phone": f"{DELETED_PHONE_PREFIX}{current['_id']}", "phone_deleted": current.get("phone"),
                 "status": OFFBOARDED}
    return soft_delete(db, ctx, CARRIERS, REF_TYPE, current, tombstone)


def list_carriers(db: MongoDb, filters: Mapping[str, Any], after: ObjectId | None, limit: int) -> list[Doc]:
    """List live carriers, oldest first.

    Args:
        db: Firm database.
        filters: Optional status, equipment, tag and q (name or company contains).
        after: Cursor id.
        limit: Page size.

    Returns:
        Up to limit + 1 carriers.
    """
    query: dict[str, Any] = {key: filters[key] for key in ("status", "equipment") if filters.get(key)}
    if filters.get("tag"):
        query["tags"] = filters["tag"]
    if filters.get("q"):
        query["$or"] = [{"name": fields.contains(filters["q"])}, {"company": fields.contains(filters["q"])}]
    return list_live(db, CARRIERS, query, after, limit)
