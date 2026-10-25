"""Load field rules: references within the firm, stops, money, miles and the free-text sheet columns."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from bson import ObjectId

from ..loads import money
from ..loads.views import mapping
from ..mongo import Doc, MongoDb
from . import fields
from .carriers import CARRIERS, DEFAULT_STATUS, EQUIPMENT_TYPES
from .errors import Invalid, NotFound
from .fleet import DRIVERS, TRUCKS
from .store import get_by_id

FACILITIES = "facilities"
SOURCES = ("manual", "email", "call", "sms", "board", "import")
BOOKABLE_CARRIER_STATUSES = frozenset({"active", "onboarding"})
STOP_TYPES = ("pickup", "delivery")
MAX_STOPS = 20
MAX_ACCESSORIALS = 20
MAX_LOAD_WEIGHT_LBS = 200_000
MILES_DECIMALS = 1
BROKER_REF_MAX = 64
ADDRESS_MAX = 500
KIND_MAX = 64

Rule = Callable[[str, Any], Any]


def _whole(field: str, value: Any, low: int, high: int) -> int:
    """Require a whole number in a range (booleans are refused).

    Args:
        field: Field name.
        value: Raw value.
        low: Minimum.
        high: Maximum.

    Returns:
        The number.

    Raises:
        Invalid: If not a whole number in [low, high].
    """
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise Invalid(field, f"{field} must be a whole number from {low} to {high}")
    return value


def _miles(field: str, value: Any, allow_zero: bool) -> float:
    """Validate a distance in miles, rounded to one decimal.

    Args:
        field: Field name.
        value: Raw value.
        allow_zero: Zero is valid (deadhead).

    Returns:
        The miles.

    Raises:
        Invalid: If not a finite number in range.
    """
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise Invalid(field, f"{field} must be a number of miles")
    miles = round(float(value), MILES_DECIMALS)
    if miles < 0 or (miles == 0 and not allow_zero) or miles > money.MAX_MILES:
        raise Invalid(field, f"{field} must be more than 0 and at most {money.MAX_MILES:g}")
    return miles


def _flag(field: str, value: Any) -> bool:
    """Require a boolean.

    Args:
        field: Field name.
        value: Raw value.

    Returns:
        The boolean.

    Raises:
        Invalid: If not a boolean.
    """
    if not isinstance(value, bool):
        raise Invalid(field, f"{field} must be true or false")
    return value


def _accessorials(field: str, value: Any) -> list[dict[str, Any]]:
    """Validate accessorial charges [{kind, amount_cents}].

    Args:
        field: Field name.
        value: Raw list.

    Returns:
        The charges.

    Raises:
        Invalid: On a malformed item or too many.
    """
    if not isinstance(value, list | tuple):
        raise Invalid(field, f"{field} must be a list")
    items: list[Any] = list(value)  # pyright: ignore[reportUnknownArgumentType]
    if len(items) > MAX_ACCESSORIALS:
        raise Invalid(field, f"at most {MAX_ACCESSORIALS} accessorials")
    charges: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise Invalid([field, index], "an accessorial is an object {kind, amount_cents}")
        entry: Mapping[str, Any] = item  # pyright: ignore[reportUnknownVariableType]
        charges.append({"kind": fields.text(field, entry.get("kind"), KIND_MAX, required=True),
                        "amount_cents": _whole(field, entry.get("amount_cents"), 0, money.MAX_RATE_CENTS)})
    return charges


def bookable_carrier(db: MongoDb, carrier_id: Any) -> Doc:
    """Load a live carrier of this firm that may carry loads (active or onboarding).

    Args:
        db: Firm database.
        carrier_id: Id text.

    Returns:
        The carrier.

    Raises:
        Invalid: If it is not a live, bookable carrier of this firm.
    """
    try:
        carrier = get_by_id(db, CARRIERS, carrier_id, "carrier")
    except NotFound as exc:
        raise Invalid("carrier_id", "no such carrier in this firm") from exc
    if str(carrier.get("status") or DEFAULT_STATUS) not in BOOKABLE_CARRIER_STATUSES:
        raise Invalid("carrier_id", "this carrier is paused or offboarded")
    return carrier


def _member_of(db: MongoDb, collection: str, what: str, carrier_id: str | None) -> Rule:
    """Build a rule for a driver or truck id: a live record of this firm, of the load's carrier when known.

    Args:
        db: Firm database.
        collection: drivers or trucks.
        what: Record kind.
        carrier_id: The load's carrier after the change, or None.

    Returns:
        The rule returning the id text.
    """

    def rule(field: str, value: Any) -> str:
        try:
            doc = get_by_id(db, collection, value, what)
        except NotFound as exc:
            raise Invalid(field, f"no such {what} in this firm") from exc
        if carrier_id is not None and str(doc.get("carrier_id")) != carrier_id:
            raise Invalid(field, f"this {what} belongs to another carrier")
        return str(doc["_id"])

    return rule


def _stop(db: MongoDb, field: str, raw: Any, seq: int, stop_id: ObjectId | None) -> dict[str, Any]:
    """Validate one stop.

    Args:
        db: Firm database.
        field: Field name for errors.
        raw: Stop mapping.
        seq: Position.
        stop_id: Existing id, or None for a new stop.

    Returns:
        The stored stop.

    Raises:
        Invalid: On a malformed stop.
    """
    if not isinstance(raw, Mapping):
        raise Invalid(field, "a stop is an object")
    item: Mapping[str, Any] = raw  # pyright: ignore[reportUnknownVariableType]
    stop: dict[str, Any] = {"id": str(stop_id or ObjectId()), "seq": seq,
                            "type": fields.choice(f"{field}.type", item.get("type"), STOP_TYPES)}
    for key in ("city", "address"):
        value = fields.text(f"{field}.{key}", item.get(key), ADDRESS_MAX)
        if value is not None:
            stop[key] = value
    for key, rule in (("state", fields.state), ("window_start", fields.aware_datetime),
                      ("window_end", fields.aware_datetime)):
        if item.get(key) is not None:
            stop[key] = rule(f"{field}.{key}", item[key])
    if item.get("facility_id") is not None:
        stop["facility_id"] = _member_of(db, FACILITIES, "facility", None)(f"{field}.facility_id",
                                                                            item["facility_id"])
    _check_window(field, stop.get("window_start"), stop.get("window_end"))
    return stop


def _check_window(field: str, start: datetime | None, end: datetime | None) -> None:
    """Refuse a window that ends before it starts.

    Args:
        field: Field name.
        start: Window start, or None.
        end: Window end, or None.

    Raises:
        Invalid: If end is before start.
    """
    if start is not None and end is not None and end < start:
        raise Invalid(f"{field}.window_end", "the window ends before it starts")


def validate_stops(db: MongoDb, value: Any, existing: list[Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Validate a full stop list, keeping ids of stops passed back with their id.

    Args:
        db: Firm database.
        value: List of stop mappings.
        existing: Current stops (ids reused when the client sends them).

    Returns:
        The stops, sequenced in the given order.

    Raises:
        Invalid: On a malformed list or stop.
    """
    if not isinstance(value, list | tuple):
        raise Invalid("stops", "stops must be a list")
    items: list[Any] = list(value)  # pyright: ignore[reportUnknownArgumentType]
    if len(items) > MAX_STOPS:
        raise Invalid("stops", f"at most {MAX_STOPS} stops")
    known = {str(stop.get("id")) for stop in existing or []}
    stops: list[dict[str, Any]] = []
    for seq, item in enumerate(items, start=1):
        stop = mapping(item)
        raw_id = None if stop is None else stop.get("id")
        keep = ObjectId(str(raw_id)) if raw_id is not None and str(raw_id) in known else None
        stops.append(_stop(db, f"stops.{seq - 1}", item, seq, keep))
    return stops


def _rules(db: MongoDb, carrier_id: str | None) -> Mapping[str, Rule]:
    """Field rules for a load.

    Args:
        db: Firm database.
        carrier_id: The load's carrier after the change (driver and truck must belong to it).

    Returns:
        Field name to rule.
    """
    return {
        "carrier_id": lambda field, value: str(bookable_carrier(db, value)["_id"]),
        "driver_id": _member_of(db, DRIVERS, "driver", carrier_id),
        "truck_id": _member_of(db, TRUCKS, "truck", carrier_id),
        "broker_mc": fields.digits, "broker_name": fields.text,
        "broker_ref": lambda field, value: fields.text(field, value, BROKER_REF_MAX),
        "source": lambda field, value: fields.choice(field, value, SOURCES),
        "equipment": lambda field, value: fields.choice(field, value, EQUIPMENT_TYPES),
        "weight_lbs": lambda field, value: _whole(field, value, 1, MAX_LOAD_WEIGHT_LBS),
        "commodity": fields.text,
        "loaded_miles": lambda field, value: _miles(field, value, False),
        "deadhead_miles": lambda field, value: _miles(field, value, True),
        "rate_cents": lambda field, value: _whole(field, value, 0, money.MAX_RATE_CENTS),
        "accessorials": _accessorials,
        "notes": lambda field, value: fields.text(field, value, fields.MAX_NOTE_CHARS),
        "flag": _flag,
        "stops": lambda field, value: validate_stops(db, value),
    }


def validate(db: MongoDb, changes: Mapping[str, Any], carrier_id: str | None) -> dict[str, Any]:
    """Validate load fields; None is kept (it removes an optional field on update).

    Args:
        db: Firm database.
        changes: Proposed fields.
        carrier_id: The load's carrier after the change.

    Returns:
        Cleaned values.

    Raises:
        Invalid: On an unknown field or a bad value.
    """
    rules = _rules(db, carrier_id)
    clean: dict[str, Any] = {}
    for name, value in changes.items():
        rule = rules.get(name)
        if rule is None:
            raise Invalid(name, "this field cannot be written here")
        clean[name] = None if value is None else rule(name, value)
    if clean.get("flag", False) is None:
        clean["flag"] = False
    return clean
