"""The dispatch board: one row per active truck, its driver, its current load and a derived status.

Current load: the truck's non-terminal load that is moving (dispatched to at_delivery) if any, else its most
recently updated non-terminal load. Terminal means paid, declined, cancelled or TONU.

Status and tone (documented mapping, also in the API schema):
    no current load ........................................ open           amber
    a pending approval on the load (before dispatch) ....... needs_approval amber
    offered, evaluating, countered ......................... offered        grey
    approved, booked, ratecon_received, dispatched ......... booked         green
    at_pickup .............................................. at_pickup      green
    in_transit ............................................. in_transit     green
    at_delivery ............................................ at_delivery    green
    delivered, pod_received, invoiced ...................... delivered      grey

Position, hours of service and duty status are never derived or guessed: they stay absent until an ELD integration
reports them. "now" and "next" texts are built only from the load's status and stops.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId

from ..mongo import Doc, MongoDb
from . import machine
from .views import DELIVERY, PICKUP, first_stop, lane_text, last_stop, place_text

OPEN, OFFERED, NEEDS_APPROVAL, BOOKED = "open", "offered", "needs_approval", "booked"
AT_PICKUP, IN_TRANSIT, AT_DELIVERY, DELIVERED = "at_pickup", "in_transit", "at_delivery", "delivered"
GREY, AMBER, GREEN = "grey", "amber", "green"
STATUS_OF_LOAD: Mapping[str, str] = {
    machine.OFFERED: OFFERED, machine.EVALUATING: OFFERED, machine.COUNTERED: OFFERED,
    machine.APPROVED: BOOKED, machine.BOOKED: BOOKED, machine.RATECON_RECEIVED: BOOKED, machine.DISPATCHED: BOOKED,
    machine.AT_PICKUP: AT_PICKUP, machine.IN_TRANSIT: IN_TRANSIT, machine.AT_DELIVERY: AT_DELIVERY,
    machine.DELIVERED: DELIVERED, machine.POD_RECEIVED: DELIVERED, machine.INVOICED: DELIVERED,
}
TONES: Mapping[str, str] = {
    OPEN: AMBER, NEEDS_APPROVAL: AMBER, OFFERED: GREY, BOOKED: GREEN, AT_PICKUP: GREEN, IN_TRANSIT: GREEN,
    AT_DELIVERY: GREEN, DELIVERED: GREY,
}
BOARD_STATUSES: tuple[str, ...] = tuple(TONES)
NOW_LABELS: Mapping[str, str] = {
    machine.OFFERED: "Offer", machine.EVALUATING: "Evaluating", machine.COUNTERED: "Countered",
    machine.APPROVED: "Approved", machine.BOOKED: "Booked", machine.RATECON_RECEIVED: "Rate con received",
    machine.DISPATCHED: "Heading to pickup", machine.AT_PICKUP: "At pickup", machine.IN_TRANSIT: "In transit",
    machine.AT_DELIVERY: "At delivery", machine.DELIVERED: "Delivered", machine.POD_RECEIVED: "POD received",
    machine.INVOICED: "Invoiced",
}
TOWARD_DELIVERY = frozenset({machine.AT_PICKUP, machine.IN_TRANSIT, machine.AT_DELIVERY})
NO_LOAD_TEXT = "No load"
TIME_FORMAT = "%a %H:%M"
HOUR_FORMAT = "%H:%M"
PENDING = "pending"


def board_status(load: Mapping[str, Any] | None, has_pending_approval: bool) -> str:
    """Derive the board status of a truck from its current load.

    Args:
        load: Current load, or None.
        has_pending_approval: A pending approval names the load.

    Returns:
        One of BOARD_STATUSES.
    """
    if load is None:
        return OPEN
    status = str(load.get("status"))
    if has_pending_approval and status not in machine.IN_MOTION and STATUS_OF_LOAD.get(status) != DELIVERED:
        return NEEDS_APPROVAL
    return STATUS_OF_LOAD.get(status, OPEN)


def current_load(loads: Iterable[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """Pick a truck's current load from its non-terminal loads.

    Args:
        loads: The truck's loads.

    Returns:
        A moving load if any, else the most recently updated one, else None.
    """
    live = [load for load in loads if load.get("status") not in machine.TERMINAL]
    if not live:
        return None
    moving = [load for load in live if load.get("status") in machine.IN_MOTION]
    return max(moving or live, key=lambda load: (load.get("updated_at") or datetime.min, str(load.get("_id"))))


def _when(stop: Mapping[str, Any], zone: ZoneInfo) -> str | None:
    """Render a stop's window in the firm's timezone, "Mon 14:00–15:00".

    Args:
        stop: Stop.
        zone: Firm timezone.

    Returns:
        The text, or None without a window.
    """
    start, end = stop.get("window_start"), stop.get("window_end")
    if not isinstance(start, datetime):
        return None
    text = start.astimezone(zone).strftime(TIME_FORMAT)
    if isinstance(end, datetime) and end != start:
        text += "–" + end.astimezone(zone).strftime(HOUR_FORMAT)
    return text


def now_text(load: Mapping[str, Any] | None) -> str:
    """Describe what the truck's load is doing, from its status and stops only.

    Args:
        load: Current load, or None.

    Returns:
        The text.
    """
    if load is None:
        return NO_LOAD_TEXT
    status = str(load.get("status"))
    if status == machine.AT_PICKUP or status == machine.DISPATCHED:
        place = place_text(first_stop(load, PICKUP))
    elif status in (machine.AT_DELIVERY, machine.DELIVERED):
        place = place_text(last_stop(load, DELIVERY))
    else:
        place = lane_text(load)
    label = NOW_LABELS.get(status, status)
    return f"{label} · {place}" if place else label


def next_text(load: Mapping[str, Any] | None, zone: ZoneInfo) -> str | None:
    """Describe the next stop and its window.

    Args:
        load: Current load, or None.
        zone: Firm timezone.

    Returns:
        "Pickup Fresno, CA · Mon 12:30", or None when nothing is next.
    """
    if load is None or STATUS_OF_LOAD.get(str(load.get("status"))) == DELIVERED:
        return None
    toward_delivery = load.get("status") in TOWARD_DELIVERY
    stop = last_stop(load, DELIVERY) if toward_delivery else first_stop(load, PICKUP)
    if stop is None:
        return None
    label = "Delivery" if toward_delivery else "Pickup"
    parts = [part for part in (place_text(stop), _when(stop, zone)) if part]
    return f"{label} {' · '.join(parts)}" if parts else label


def _by_id(db: MongoDb, collection: str, ids: Iterable[Any]) -> dict[str, Doc]:
    """Load live records by id text in one query.

    Args:
        db: Firm database.
        collection: Collection name.
        ids: Id texts (invalid ones are ignored).

    Returns:
        Id text to document.
    """
    wanted = sorted({ObjectId(str(value)) for value in ids if value is not None and ObjectId.is_valid(str(value))})
    if not wanted:
        return {}
    return {str(doc["_id"]): doc for doc in db[collection].find({"_id": {"$in": wanted}, "deleted_at": None})}


def board_context(db: MongoDb, trucks: Sequence[Mapping[str, Any]], now: datetime) -> dict[str, Any]:
    """Fetch everything the rows of a page of trucks need, in a fixed number of queries.

    Args:
        db: Firm database.
        trucks: Page of trucks.
        now: Current time (expired approvals are not pending).

    Returns:
        carriers, loads (by truck id), drivers and pending (load ids with a pending approval).
    """
    truck_ids = [str(truck["_id"]) for truck in trucks]
    loads_by_truck: dict[str, list[Doc]] = {truck_id: [] for truck_id in truck_ids}
    query = {"truck_id": {"$in": truck_ids}, "status": {"$nin": sorted(machine.TERMINAL)}, "deleted_at": None}
    for load in db["loads"].find(query):
        loads_by_truck[str(load["truck_id"])].append(load)
    current = {truck_id: current_load(items) for truck_id, items in loads_by_truck.items()}
    load_ids = [str(load["_id"]) for load in current.values() if load is not None]
    driver_ids = [truck.get("driver_id") for truck in trucks] + [
        load.get("driver_id") for load in current.values() if load is not None]
    pending = {str(doc["subject_ref"]["id"]) for doc in db["approvals"].find(
        {"status": PENDING, "expires_at": {"$gt": now}, "subject_ref.type": "load",
         "subject_ref.id": {"$in": load_ids}}, {"subject_ref": 1})}
    return {"carriers": _by_id(db, "carriers", [truck.get("carrier_id") for truck in trucks]),
            "drivers": _by_id(db, "drivers", driver_ids), "current": current, "pending": pending}
