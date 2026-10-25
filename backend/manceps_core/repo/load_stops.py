"""Single-stop edits on a load: add, change, remove. Each rewrites the validated stop list in one audited update."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..loads import machine
from ..loads.views import stops_of
from ..mongo import Doc, MongoDb
from .errors import Conflict, Invalid, NotFound
from .load_fields import MAX_STOPS, validate_stops
from .load_status import record_event
from .loads import LOADS, REF_TYPE, get_load
from .store import WriteContext, update

STOP_KEYS = ("type", "city", "state", "address", "facility_id", "window_start", "window_end")


def _open_load(db: MongoDb, load_id: Any) -> Doc:
    """Load a load whose stops may still change.

    Args:
        db: Firm database.
        load_id: Load id.

    Returns:
        The load.

    Raises:
        NotFound: If the load is not live.
        Conflict: 409 load_closed for paid, declined, cancelled or TONU loads.
    """
    load = get_load(db, load_id)
    if load.get("status") in machine.TERMINAL:
        raise Conflict("load_closed", "this load is closed; its stops cannot change", {"status": load["status"]})
    return load


def _plain(stop: Mapping[str, Any]) -> dict[str, Any]:
    """Copy a stored stop's editable fields and id.

    Args:
        stop: Stored stop.

    Returns:
        The fields.
    """
    return {"id": stop.get("id"), **{key: stop[key] for key in STOP_KEYS if stop.get(key) is not None}}


def _save(db: MongoDb, ctx: WriteContext, load: Doc, stops: list[dict[str, Any]], event: str,
          stop_id: str | None) -> Doc:
    """Validate and store a new stop list, then add a timeline entry.

    Args:
        db: Firm database.
        ctx: Writer.
        load: The load.
        stops: Proposed stops (ids kept for existing ones).
        event: Timeline entry type.
        stop_id: Affected stop id, or None.

    Returns:
        The updated load.

    Raises:
        Invalid: On a bad stop.
    """
    clean = validate_stops(db, stops, load.get("stops") or [])
    after = update(db, ctx, LOADS, REF_TYPE, load, {"stops": clean})
    record_event(db, ctx, after, event, {"stop_id": stop_id or clean[-1]["id"]})
    return after


def _stop_index(load: Mapping[str, Any], stop_id: str) -> int:
    """Find a stop by id.

    Args:
        load: The load.
        stop_id: Stop id.

    Returns:
        Its index in the stored list.

    Raises:
        NotFound: If the load has no such stop.
    """
    for index, stop in enumerate(stops_of(load)):
        if str(stop.get("id")) == stop_id:
            return index
    raise NotFound("stop")


def add_stop(db: MongoDb, ctx: WriteContext, load_id: Any, stop: Mapping[str, Any], position: int | None) -> Doc:
    """Add a stop at a position (1-based; at the end when None).

    Args:
        db: Firm database.
        ctx: Writer.
        load_id: Load id.
        stop: Stop fields.
        position: Where to insert it.

    Returns:
        The updated load.

    Raises:
        NotFound: If the load is not live.
        Conflict: load_closed.
        Invalid: On a bad stop, a bad position or too many stops.
    """
    load = _open_load(db, load_id)
    stops = [_plain(item) for item in stops_of(load)]
    if len(stops) >= MAX_STOPS:
        raise Invalid("stops", f"at most {MAX_STOPS} stops")
    index = len(stops) if position is None else position - 1
    if not 0 <= index <= len(stops):
        raise Invalid("position", f"position must be from 1 to {len(stops) + 1}")
    stops.insert(index, {key: value for key, value in stop.items() if key != "id"})
    after = _save(db, ctx, load, stops, "stop_added", None)
    return after


def update_stop(db: MongoDb, ctx: WriteContext, load_id: Any, stop_id: str, changes: Mapping[str, Any]) -> Doc:
    """Change one stop (None removes an optional stop field).

    Args:
        db: Firm database.
        ctx: Writer.
        load_id: Load id.
        stop_id: Stop id.
        changes: Stop fields.

    Returns:
        The updated load.

    Raises:
        NotFound: If the load or stop is missing.
        Conflict: load_closed.
        Invalid: On bad values or an empty change.
    """
    if not changes:
        raise Invalid("body", "send at least one field to change")
    load = _open_load(db, load_id)
    index = _stop_index(load, stop_id)
    stops = [_plain(item) for item in stops_of(load)]
    merged = {**stops[index], **changes}
    stops[index] = {key: value for key, value in merged.items() if value is not None}
    return _save(db, ctx, load, stops, "stop_updated", stop_id)


def delete_stop(db: MongoDb, ctx: WriteContext, load_id: Any, stop_id: str) -> Doc:
    """Remove one stop.

    Args:
        db: Firm database.
        ctx: Writer.
        load_id: Load id.
        stop_id: Stop id.

    Returns:
        The updated load.

    Raises:
        NotFound: If the load or stop is missing.
        Conflict: load_closed.
    """
    load = _open_load(db, load_id)
    index = _stop_index(load, stop_id)
    stops = [_plain(item) for position, item in enumerate(stops_of(load)) if position != index]
    clean = validate_stops(db, stops, load.get("stops") or [])
    after = update(db, ctx, LOADS, REF_TYPE, load, {"stops": clean})
    record_event(db, ctx, after, "stop_deleted", {"stop_id": stop_id})
    return after
