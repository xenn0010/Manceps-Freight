"""Drivers and trucks, each owned by a live carrier of the same firm.

`drivers.phone` and `trucks.vin` are unique (sparse). A deleted driver gets the same phone tombstone as a carrier;
a deleted truck moves its VIN to `vin_deleted`, so both can be added again. `carrier_id` is stored as the carrier's
id text.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from bson import ObjectId

from ..mongo import Doc, MongoDb
from . import fields
from .carriers import CARRIERS, DELETED_PHONE_PREFIX, EQUIPMENT_TYPES
from .errors import Invalid, NotFound
from .store import WriteContext, get_by_id, insert, list_live, soft_delete, update

DRIVERS = "drivers"
TRUCKS = "trucks"
DRIVER_STATUSES = ("active", "inactive")
DEFAULT_DRIVER_STATUS = "active"
VIN_PATTERN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
PLATE_MAX = 16
UNIT_MAX = 32
MAX_TRUCK_WEIGHT_LBS = 200_000
DUPLICATE_DRIVER_PHONE = ("duplicate_phone", "a driver with this phone number already exists")
DUPLICATE_VIN = ("duplicate_vin", "a truck with this VIN already exists")

Rule = Callable[[str, Any], Any]


def _vin(field: str, value: Any) -> str:
    """Validate a 17-character VIN (no I, O or Q).

    Args:
        field: Field name.
        value: Raw value.

    Returns:
        The uppercased VIN.

    Raises:
        Invalid: If malformed.
    """
    vin = str(value).strip().upper()
    if not VIN_PATTERN.fullmatch(vin):
        raise Invalid(field, "a VIN is 17 letters and digits without I, O or Q")
    return vin


def _weight(field: str, value: Any) -> int:
    """Validate a gross weight in pounds.

    Args:
        field: Field name.
        value: Raw value.

    Returns:
        The weight.

    Raises:
        Invalid: If not a whole number in (0, MAX_TRUCK_WEIGHT_LBS].
    """
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= MAX_TRUCK_WEIGHT_LBS:
        raise Invalid(field, f"{field} must be a whole number from 1 to {MAX_TRUCK_WEIGHT_LBS}")
    return value


def _carrier_ref(db: MongoDb) -> Rule:
    """Build a rule checking carrier_id names a live carrier of this firm.

    Args:
        db: Firm database.

    Returns:
        The rule, returning the carrier id text.
    """

    def rule(field: str, value: Any) -> str:
        try:
            carrier = get_by_id(db, CARRIERS, value, "carrier")
        except NotFound as exc:
            raise Invalid(field, "no such carrier in this firm") from exc
        return str(carrier["_id"])

    return rule


def _driver_rules(db: MongoDb) -> Mapping[str, Rule]:
    """Rules for driver fields.

    Args:
        db: Firm database.

    Returns:
        Field name to rule.
    """
    return {"carrier_id": _carrier_ref(db), "name": fields.text, "phone": fields.phone, "email": fields.email,
            "status": lambda field, value: fields.choice(field, value, DRIVER_STATUSES),
            "license_state": fields.state, "license_expires_at": fields.aware_datetime}


def _truck_rules(db: MongoDb) -> Mapping[str, Rule]:
    """Rules for truck fields.

    Args:
        db: Firm database.

    Returns:
        Field name to rule.
    """
    return {"carrier_id": _carrier_ref(db), "unit": lambda field, value: fields.text(field, value, UNIT_MAX),
            "equipment": lambda field, value: fields.choice(field, value, EQUIPMENT_TYPES), "vin": _vin,
            "plate": lambda field, value: fields.text(field, value, PLATE_MAX), "plate_state": fields.state,
            "max_weight_lbs": _weight}


@dataclass(frozen=True)
class _Spec:
    """How one fleet record kind is stored: collection, field rules, required fields and its unique-index error."""

    collection: str
    rules: Callable[[MongoDb], Mapping[str, Rule]]
    required: frozenset[str]
    duplicate: tuple[str, str]


def _validate(rules: Mapping[str, Rule], changes: Mapping[str, Any], required: frozenset[str]) -> dict[str, Any]:
    """Apply field rules; None is kept (remove on update) unless the field is required.

    Args:
        rules: Field rules.
        changes: Proposed values.
        required: Fields that cannot be removed.

    Returns:
        Cleaned values.

    Raises:
        Invalid: On unknown fields, removing a required field, or bad values.
    """
    clean: dict[str, Any] = {}
    for name, value in changes.items():
        rule = rules.get(name)
        if rule is None:
            raise Invalid(name, "this field cannot be written here")
        if value is None and name in required:
            raise Invalid(name, f"{name} is required")
        clean[name] = None if value is None else rule(name, value)
    return clean


def _create(db: MongoDb, ctx: WriteContext, kind: str, values: Mapping[str, Any],
            defaults: Mapping[str, Any]) -> Doc:
    """Validate and insert a driver or truck.

    Args:
        db: Firm database.
        ctx: Writer.
        kind: driver or truck.
        values: Proposed fields.
        defaults: Values used when absent.

    Returns:
        The stored record.

    Raises:
        Invalid: On missing required fields or bad values.
        Conflict: On a duplicate phone or VIN.
    """
    spec = SPECS[kind]
    missing = [name for name in sorted(spec.required) if values.get(name) is None]
    if missing:
        raise Invalid(missing[0], f"{missing[0]} is required")
    clean = {key: value for key, value in _validate(spec.rules(db), values, spec.required).items() if value is not None}
    return insert(db, ctx, spec.collection, kind, {**defaults, **clean}, spec.duplicate)


SPECS: Mapping[str, _Spec] = {
    "driver": _Spec(DRIVERS, _driver_rules, frozenset({"carrier_id", "name"}), DUPLICATE_DRIVER_PHONE),
    "truck": _Spec(TRUCKS, _truck_rules, frozenset({"carrier_id", "unit"}), DUPLICATE_VIN),
}


def create_driver(db: MongoDb, ctx: WriteContext, values: Mapping[str, Any]) -> Doc:
    """Add a driver to a carrier of this firm.

    Args:
        db: Firm database.
        ctx: Writer.
        values: Proposed fields.

    Returns:
        The stored driver.

    Raises:
        Invalid: On missing or bad fields (including an unknown carrier).
        Conflict: duplicate_phone.
    """
    return _create(db, ctx, "driver", values, {"status": DEFAULT_DRIVER_STATUS})


def create_truck(db: MongoDb, ctx: WriteContext, values: Mapping[str, Any]) -> Doc:
    """Add a truck to a carrier of this firm.

    Args:
        db: Firm database.
        ctx: Writer.
        values: Proposed fields.

    Returns:
        The stored truck.

    Raises:
        Invalid: On missing or bad fields (including an unknown carrier).
        Conflict: duplicate_vin.
    """
    return _create(db, ctx, "truck", values, {})


def get_record(db: MongoDb, kind: str, record_id: Any) -> Doc:
    """Load a live driver or truck.

    Args:
        db: Firm database.
        kind: driver or truck.
        record_id: Id text.

    Returns:
        The record.

    Raises:
        NotFound: If absent, malformed or deleted.
    """
    return get_by_id(db, SPECS[kind].collection, record_id, kind)


def update_record(db: MongoDb, ctx: WriteContext, kind: str, record_id: Any, changes: Mapping[str, Any]) -> Doc:
    """Change a driver or truck (None removes an optional field).

    Args:
        db: Firm database.
        ctx: Writer.
        kind: driver or truck.
        record_id: Id text.
        changes: Proposed fields.

    Returns:
        The updated record.

    Raises:
        NotFound: If the record is not live.
        Invalid: On bad values or an empty change.
        Conflict: On a duplicate phone or VIN.
    """
    if not changes:
        raise Invalid("body", "send at least one field to change")
    spec = SPECS[kind]
    current = get_record(db, kind, record_id)
    clean = _validate(spec.rules(db), changes, spec.required)
    return update(db, ctx, spec.collection, kind, current, clean, spec.duplicate)


def delete_record(db: MongoDb, ctx: WriteContext, kind: str, record_id: Any) -> Doc:
    """Soft-delete a driver (phone tombstone) or truck (VIN moved aside) so both can be added again.

    Args:
        db: Firm database.
        ctx: Writer.
        kind: driver or truck.
        record_id: Id text.

    Returns:
        The deleted record.

    Raises:
        NotFound: If the record is not live.
    """
    current = get_record(db, kind, record_id)
    if kind == "driver":
        changes = {"phone": f"{DELETED_PHONE_PREFIX}{current['_id']}", "phone_deleted": current["phone"]} \
            if current.get("phone") else {}
        return soft_delete(db, ctx, DRIVERS, kind, current, changes)
    changes = {"vin_deleted": current["vin"]} if current.get("vin") else {}
    return soft_delete(db, ctx, TRUCKS, kind, current, changes, ("vin",) if current.get("vin") else ())


def list_records(db: MongoDb, kind: str, filters: Mapping[str, Any], after: ObjectId | None,
                 limit: int) -> list[Doc]:
    """List live drivers or trucks, oldest first.

    Args:
        db: Firm database.
        kind: driver or truck.
        filters: Optional carrier_id and status.
        after: Cursor id.
        limit: Page size.

    Returns:
        Up to limit + 1 records.
    """
    query = {key: filters[key] for key in ("carrier_id", "status") if filters.get(key)}
    return list_live(db, SPECS[kind].collection, query, after, limit)
