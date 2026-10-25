"""Turn an imported loads row into load fields: split the lane, build stops in the firm's timezone, and resolve the
truck (by unit), driver and carrier (by phone) to records of this firm. The load repository then validates the
result exactly as it validates an API create, so the import accepts nothing the API would refuse.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from manceps_core.mongo import MongoDb
from manceps_core.repo import fields, loads
from manceps_core.repo.carriers import CARRIERS
from manceps_core.repo.errors import Invalid
from manceps_core.repo.fleet import DRIVERS, TRUCKS

from .schema import CARRIER_PHONE, normalize_key

LANE_SPLIT = re.compile(r"\s*(?:→|->|=>|–|—|\s-\s|\bto\b)\s*", re.IGNORECASE)
PLACE = re.compile(r"^(?P<city>.+?)(?:,\s*(?P<state>[A-Za-z]{2}))?$")
DIRECT = ("broker_mc", "broker_name", "broker_ref", "loaded_miles", "deadhead_miles", "rate_cents", "commodity",
          "notes")
SLUG_NOISE = re.compile(r"[^a-z0-9]+")
LIVE = {"deleted_at": None}
IMPORT_SOURCE = "import"
LANE_PARTS = 2

Cache = dict[str, Any]


def _place(text: str | None) -> dict[str, str]:
    """Split "Fresno, CA" into city and state.

    Args:
        text: Place text.

    Returns:
        {city, state?} (empty when blank).
    """
    if not text or not text.strip():
        return {}
    match = PLACE.match(text.strip())
    if match is None:
        return {"city": text.strip()}
    place = {"city": match.group("city").strip()}
    if match.group("state"):
        place["state"] = match.group("state").upper()
    return place


def _ends(values: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """Find origin and destination from their own columns, else from the lane.

    Args:
        values: Row values.

    Returns:
        (origin, destination).

    Raises:
        Invalid: When a lane cannot be split in two.
    """
    origin, destination = values.get("origin"), values.get("destination")
    lane = values.get("lane")
    if lane and not (origin and destination):
        parts = [part for part in LANE_SPLIT.split(str(lane)) if part.strip()]
        if len(parts) != LANE_PARTS:
            raise Invalid("lane", "write the lane as Origin → Destination")
        origin, destination = origin or parts[0], destination or parts[1]
    return (None if origin is None else str(origin)), (None if destination is None else str(destination))


def _local(moment: Any, zone: ZoneInfo) -> datetime | None:
    """Give a naive time the firm's timezone.

    Args:
        moment: Datetime or None.
        zone: Firm timezone.

    Returns:
        Aware datetime, or None.
    """
    if not isinstance(moment, datetime):
        return None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=zone)


def stops_for(values: Mapping[str, Any], zone: ZoneInfo) -> list[dict[str, Any]]:
    """Build pickup and delivery stops from a row.

    Args:
        values: Row values.
        zone: Firm timezone (for times without an offset).

    Returns:
        Stop inputs (none when the row names neither end nor time).

    Raises:
        Invalid: On an unsplittable lane.
    """
    origin, destination = _ends(values)
    stops: list[dict[str, Any]] = []
    for kind, place, moment in (("pickup", origin, values.get("pickup_at")),
                                ("delivery", destination, values.get("delivery_at"))):
        stop: dict[str, Any] = {"type": kind, **_place(place)}
        when = _local(moment, zone)
        if when is not None:
            stop["window_start"] = when
        if len(stop) > 1:
            stops.append(stop)
    return stops


def _one(db: MongoDb, collection: str, query: Mapping[str, Any], field: str, what: str) -> dict[str, Any]:
    """Find exactly one live record.

    Args:
        db: Firm database.
        collection: Collection.
        query: Filter.
        field: Row field for errors.
        what: Record kind for errors.

    Returns:
        The record.

    Raises:
        Invalid: When none or several match.
    """
    found = list(db[collection].find({**query, **LIVE}, {"carrier_id": 1}, limit=2))
    if len(found) != 1:
        raise Invalid(field, f"no single {what} in your firm matches" if found else f"no {what} in your firm matches")
    return found[0]


def _references(db: MongoDb, values: Mapping[str, Any], cache: Cache) -> dict[str, str]:
    """Resolve truck unit, driver phone and carrier phone to ids (the carrier defaults to the truck's or driver's).

    Args:
        db: Firm database.
        values: Row values.
        cache: Lookups already made in this run.

    Returns:
        carrier_id, truck_id and driver_id when known.

    Raises:
        Invalid: On an unknown or ambiguous reference or a malformed phone.
    """
    refs: dict[str, str] = {}
    lookups = (("truck_unit", TRUCKS, "truck", "unit", None), ("driver_phone", DRIVERS, "driver", "phone", "phone"),
               (CARRIER_PHONE, CARRIERS, "carrier", "phone", "phone"))
    for field, collection, what, key, kind in lookups:
        raw = values.get(field)
        if raw is None:
            continue
        wanted = str(raw).strip() if kind is None else normalize_key(kind, raw)
        if wanted is None:
            raise Invalid(field, "enter a 10-digit US phone number")
        token = f"{collection}:{wanted}"
        if token not in cache:
            cache[token] = _one(db, collection, {key: wanted}, field, what)
        record = cache[token]
        refs[f"{what}_id"] = str(record["_id"])
        if what != "carrier" and record.get("carrier_id") is not None:
            refs.setdefault("carrier_from_" + what, str(record["carrier_id"]))
    carrier = refs.get("carrier_id") or refs.get("carrier_from_truck") or refs.get("carrier_from_driver")
    clean = {name: value for name, value in refs.items() if not name.startswith("carrier_from_")}
    if carrier is not None:
        clean["carrier_id"] = carrier
    return clean


def load_values(db: MongoDb, values: Mapping[str, Any], zone: ZoneInfo, cache: Cache) -> dict[str, Any]:
    """Convert a row and validate it with the load repository.

    Args:
        db: Firm database.
        values: Row values (coerced).
        zone: Firm timezone.
        cache: Reference lookups for this run.

    Returns:
        The fields a load create would store (source import).

    Raises:
        Invalid: When the row breaks a load rule.
    """
    out: dict[str, Any] = {key: values[key] for key in DIRECT if values.get(key) is not None}
    if values.get("weight_lbs") is not None:
        out["weight_lbs"] = round(float(values["weight_lbs"]))
    if values.get("equipment"):
        out["equipment"] = SLUG_NOISE.sub("_", str(values["equipment"]).lower()).strip("_")
    stops = stops_for(values, zone)
    if stops:
        out["stops"] = stops
    out.update(_references(db, values, cache))
    clean = loads.validate_new(db, {**out, "source": IMPORT_SOURCE})
    if values.get("ref"):
        clean["ref"] = fields.text("ref", values["ref"], fields.NAME_MAX)
    return clean
