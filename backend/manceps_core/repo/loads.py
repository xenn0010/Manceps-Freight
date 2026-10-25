"""Loads: validation, create, inline edits and listing (status moves live in `load_status.py`).

A load is created in `offered` with a firm-unique ref `L-<year>-<5 digits>` from the `loads_<year>` counter. Every
reference (carrier, driver, truck, facility) must be a live record of the same firm, and a driver or truck must
belong to the load's carrier (bring-your-own-carrier). Once a load is contracted (booked or later) its rate and
carrier are the contract: changing them is 409 `approval_required` (`accept_rate`). Closed loads (paid, declined,
cancelled, TONU) accept only notes and the flag.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from bson import ObjectId

from .. import events
from ..counters import next_value
from ..loads import machine
from ..mongo import Doc, MongoDb
from . import fields
from .errors import Conflict, Invalid
from .load_fields import validate, validate_stops
from .store import DESCENDING, WriteContext, get_by_id, insert, list_live, ref_of, update

LOADS = "loads"
LOAD_EVENTS = "load_events"
REF_TYPE = "load"
REF_FORMAT = "L-{year}-{number:05d}"
COUNTER_FORMAT = "loads_{year}"
DEFAULT_SOURCE = "manual"
CONTRACT_FIELDS = frozenset({"rate_cents", "carrier_id"})
CLOSED_EDITABLE = frozenset({"notes", "flag"})
CREATE_ONLY = frozenset({"source"})
CREATED_EVENT, UPDATED_EVENT = "load.created", "load.updated"



def record_event(db: MongoDb, ctx: WriteContext, load: Mapping[str, Any], event_type: str,
                 data: Mapping[str, Any]) -> None:
    """Append one entry to a load's timeline.

    Args:
        db: Firm database.
        ctx: Writer.
        load: The load.
        event_type: created, updated, status_changed, evaluated, stop_added...
        data: Small details.
    """
    db[LOAD_EVENTS].insert_one({"load_id": load["_id"], "type": event_type, "at": ctx.now(), "by": dict(ctx.who),
                                "data": dict(data)})


def announce(db: MongoDb, ctx: WriteContext, load: Mapping[str, Any], event_type: str,
             data: Mapping[str, Any]) -> None:
    """Add a timeline entry and emit the matching firm event (load.<type>).

    Args:
        db: Firm database.
        ctx: Writer.
        load: The load after the change.
        event_type: created or updated.
        data: Small details.
    """
    record_event(db, ctx, load, event_type, data)
    events.emit(db, f"load.{event_type}", ref_of(REF_TYPE, load),
                {"load_id": str(load["_id"]), "ref": load.get("ref"), **data}, ctx.clock)


def validate_new(db: MongoDb, values: Mapping[str, Any]) -> dict[str, Any]:
    """Apply every rule a new load must pass, without writing (imports preview rows with it).

    Args:
        db: Firm database.
        values: Proposed fields.

    Returns:
        The fields create_load stores (defaults included, ref and status excluded).

    Raises:
        Invalid: On bad values.
    """
    carrier = values.get("carrier_id")
    clean = {key: value for key, value in validate(db, values, None if carrier is None else str(carrier)).items()
             if value is not None}
    clean.setdefault("source", DEFAULT_SOURCE)
    clean.setdefault("flag", False)
    clean.setdefault("stops", [])
    clean.setdefault("accessorials", [])
    return clean


def next_ref(db: MongoDb, now: datetime) -> str:
    """Allocate the next load ref of the year.

    Args:
        db: Firm database.
        now: Current time (its UTC year names the counter).

    Returns:
        "L-2026-00042".
    """
    return REF_FORMAT.format(year=now.year, number=next_value(db, COUNTER_FORMAT.format(year=now.year)))


def create_load(db: MongoDb, ctx: WriteContext, values: Mapping[str, Any], record_id: ObjectId | None = None) -> Doc:
    """Create a load in `offered` (audited; a `created` timeline entry and a `load.created` event follow).

    Args:
        db: Firm database.
        ctx: Writer.
        values: Proposed fields.
        record_id: Reserved id (imports), or None.

    Returns:
        The stored load.

    Raises:
        Invalid: On bad values.
        Conflict: duplicate_load when record_id is taken.
    """
    clean = validate_new(db, values)
    now = ctx.now()
    stored = {**clean, "ref": next_ref(db, now), "status": machine.OFFERED, "status_changed_at": now}
    load = insert(db, ctx, LOADS, REF_TYPE, stored, ("duplicate_load", "this load already exists"), record_id)
    announce(db, ctx, load, "created", {"status": machine.OFFERED})
    return load


def get_load(db: MongoDb, load_id: Any) -> Doc:
    """Load a live load.

    Args:
        db: Firm database.
        load_id: Id text or ObjectId.

    Returns:
        The load.

    Raises:
        NotFound: If absent, malformed or deleted.
    """
    return get_by_id(db, LOADS, load_id, REF_TYPE)


def check_edit(current: Mapping[str, Any], changes: Mapping[str, Any]) -> None:
    """Refuse edits the load's status does not allow.

    Args:
        current: The load as stored.
        changes: Proposed fields (status excluded).

    Raises:
        Conflict: 409 load_closed, or 409 approval_required for the rate or carrier of a contracted load.
        Invalid: 422 for fields that are fixed at creation.
    """
    status = str(current.get("status"))
    fixed = sorted(CREATE_ONLY & changes.keys())
    if fixed:
        raise Invalid(fixed[0], f"{fixed[0]} is set when the load is created")
    if status in machine.TERMINAL and set(changes) - CLOSED_EDITABLE:
        raise Conflict("load_closed", "this load is closed; only notes and the flag can change",
                       {"status": status})
    contract = sorted(CONTRACT_FIELDS & {key for key, value in changes.items() if value != current.get(key)})
    if contract and status not in machine.NEGOTIABLE:
        raise Conflict("approval_required", "the rate and carrier of an accepted load change only through approval",
                       {"approval_kind": machine.ACCEPT_RATE_KIND, "fields": contract})


def update_load(db: MongoDb, ctx: WriteContext, load_id: Any, changes: Mapping[str, Any]) -> Doc:
    """Change a load's non-status fields (None removes an optional field), audited.

    Args:
        db: Firm database.
        ctx: Writer.
        load_id: Load id.
        changes: Proposed fields.

    Returns:
        The updated load.

    Raises:
        NotFound: If the load is not live.
        Conflict: load_closed or approval_required.
        Invalid: On bad values, an empty change, or removing the carrier of a contracted load.
    """
    if not changes:
        raise Invalid("body", "send at least one field to change")
    current = get_load(db, load_id)
    check_edit(current, changes)
    carrier = changes["carrier_id"] if "carrier_id" in changes else current.get("carrier_id")
    kept = {key: current[key] for key in ("driver_id", "truck_id")
            if "carrier_id" in changes and key not in changes and current.get(key) is not None}
    clean = validate(db, {**kept, **changes}, None if carrier is None else str(carrier))
    if "stops" in clean and clean["stops"] is not None:
        clean["stops"] = validate_stops(db, changes["stops"], current.get("stops") or [])
    after = update(db, ctx, LOADS, REF_TYPE, current, clean)
    announce(db, ctx, after, "updated", {"fields": sorted(clean)})
    return after


def list_loads(db: MongoDb, filters: Mapping[str, Any], after: ObjectId | None, limit: int) -> list[Doc]:
    """List live loads, newest first.

    Args:
        db: Firm database.
        filters: Optional status, carrier_id, driver_id, truck_id, broker_mc, flag, pickup_from, pickup_to, q.
        after: Cursor id.
        limit: Page size.

    Returns:
        Up to limit + 1 loads.
    """
    query: dict[str, Any] = {key: filters[key] for key in ("status", "carrier_id", "driver_id", "truck_id",
                                                           "broker_mc") if filters.get(key)}
    if filters.get("flag") is not None:
        query["flag"] = bool(filters["flag"])
    window = {op: filters[key] for op, key in (("$gte", "pickup_from"), ("$lt", "pickup_to")) if filters.get(key)}
    if window:
        query["stops"] = {"$elemMatch": {"type": "pickup", "window_start": window}}
    if filters.get("q"):
        query["$or"] = [{"ref": fields.contains(filters["q"])}, {"broker_name": fields.contains(filters["q"])},
                        {"broker_ref": fields.contains(filters["q"])}]
    return list_live(db, LOADS, query, after, limit, DESCENDING)
