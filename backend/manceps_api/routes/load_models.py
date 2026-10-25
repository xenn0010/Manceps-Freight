"""Request and response models for loads, and the renderer shared by the loads, board and approvals routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, Field

from manceps_core.loads import machine, money
from manceps_core.loads.views import DELIVERY, PICKUP, first_stop, lane_text, last_stop, mapping, mappings
from manceps_core.mongo import Doc
from manceps_core.repo.load_fields import ADDRESS_MAX, BROKER_REF_MAX, KIND_MAX, MAX_ACCESSORIALS, MAX_STOPS

from ..auth.models import StrictModel
from .common import ID_MAX, Code, LongText, Name, Number, text_of

LoadStatus = Literal[
    "offered", "evaluating", "countered", "approved", "booked", "ratecon_received", "dispatched", "at_pickup",
    "in_transit", "at_delivery", "delivered", "pod_received", "invoiced", "paid", "declined", "cancelled", "tonu"]
StopType = Literal["pickup", "delivery"]
Source = Literal["manual", "email", "call", "sms", "board", "import"]
Ref = Annotated[str, Field(max_length=ID_MAX)]
Cents = Annotated[int, Field(ge=0, le=money.MAX_RATE_CENTS, description="Integer cents (USD).")]
Miles = Annotated[float, Field(gt=0, le=money.MAX_MILES)]
Address = Annotated[str, Field(max_length=ADDRESS_MAX)]
Reason = Annotated[str, Field(max_length=500)]
EXAMPLE_LOAD: dict[str, Any] = {
    "carrier_id": "6718a0c2e4b0a1b2c3d4e5f6", "truck_id": "6718a0c2e4b0a1b2c3d4e5f7", "broker_mc": "MC-123456",
    "broker_name": "Valley Logistics", "broker_ref": "VL-30981", "rate_cents": 65000, "loaded_miles": 125,
    "stops": [{"type": "pickup", "city": "Fresno", "state": "CA", "window_start": "2026-10-26T19:30:00Z"},
              {"type": "delivery", "city": "Stockton", "state": "CA", "window_start": "2026-10-26T22:30:00Z"}],
    "notes": "Window moved to 15:30", "flag": False,
}


class StopInput(StrictModel):
    """A pickup or delivery."""

    id: Ref | None = Field(default=None, description="Existing stop id (kept when the full list is re-sent).")
    type: StopType
    city: Name | None = None
    state: Code | None = None
    address: Address | None = None
    facility_id: Ref | None = None
    window_start: AwareDatetime | None = None
    window_end: AwareDatetime | None = None


class StopAdd(StopInput):
    """A stop to insert."""

    position: int | None = Field(default=None, ge=1, le=MAX_STOPS, description="1-based; end when omitted.")


class StopPatch(StrictModel):
    """Stop changes; null removes an optional field."""

    type: StopType | None = None
    city: Name | None = None
    state: Code | None = None
    address: Address | None = None
    facility_id: Ref | None = None
    window_start: AwareDatetime | None = None
    window_end: AwareDatetime | None = None


class Accessorial(StrictModel):
    """An extra charge (detention, lumper...)."""

    kind: Annotated[str, Field(max_length=KIND_MAX)]
    amount_cents: Cents


class LoadFields(StrictModel):
    """Writable load fields (the sheet's columns)."""

    carrier_id: Ref | None = None
    driver_id: Ref | None = None
    truck_id: Ref | None = None
    broker_mc: Number | None = None
    broker_name: Name | None = None
    broker_ref: Annotated[str, Field(max_length=BROKER_REF_MAX)] | None = None
    stops: Annotated[list[StopInput], Field(max_length=MAX_STOPS)] | None = None
    equipment: Code | None = None
    weight_lbs: int | None = None
    commodity: Name | None = None
    loaded_miles: Miles | None = None
    deadhead_miles: Annotated[float, Field(ge=0, le=money.MAX_MILES)] | None = None
    rate_cents: Cents | None = Field(default=None, description="Editable while negotiating; after acceptance only "
                                                               "through an accept_rate approval (409).")
    accessorials: Annotated[list[Accessorial], Field(max_length=MAX_ACCESSORIALS)] | None = None
    notes: LongText | None = Field(default=None, description="Dispatcher notes (max 1000 characters).")
    flag: bool | None = None


class LoadCreate(LoadFields):
    """A new load; it starts in `offered`."""

    model_config = {**StrictModel.model_config, "json_schema_extra": {"examples": [EXAMPLE_LOAD]}}

    source: Source | None = None


class LoadPatch(LoadFields):
    """Inline cell edits; null removes an optional field. `status` runs the same checks as a transition."""

    status: LoadStatus | None = Field(default=None, description="approved and booked (and cancelling a booked load) "
                                                                "answer 409 approval_required.")


class TransitionInput(StrictModel):
    """A direct status move."""

    to: Annotated[str, Field(max_length=32, description="Target status.")]
    reason: Reason | None = None


class EvaluateInput(StrictModel):
    """Evaluation options."""

    mpg: float | None = Field(default=None, ge=3.0, le=12.0, description="Truck fuel economy (default 6.5).")


class Stop(BaseModel):
    """A stop."""

    id: str
    seq: int
    type: str
    city: str | None
    state: str | None
    address: str | None
    facility_id: str | None
    window_start: datetime | None
    window_end: datetime | None


class Load(BaseModel):
    """A load with the sheet's derived columns (lane, pickup/delivery time, $/mi)."""

    id: str
    ref: str
    status: str
    carrier_id: str | None
    driver_id: str | None
    truck_id: str | None
    broker_mc: str | None
    broker_name: str | None
    broker_ref: str | None
    source: str | None
    lane: str | None
    pickup_at: datetime | None
    delivery_at: datetime | None
    stops: list[Stop]
    equipment: str | None
    weight_lbs: int | None
    commodity: str | None
    loaded_miles: float | None
    deadhead_miles: float | None
    rate_cents: int | None
    rate_per_mile_cents: int | None = Field(description="rate_cents / loaded_miles, rounded half up.")
    accessorials: list[dict[str, Any]]
    evaluation: dict[str, Any] | None
    notes: str | None
    flag: bool
    cancelled_reason: str | None
    booked_at: datetime | None
    ratecon_approved: bool
    status_changed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LoadEvent(BaseModel):
    """One timeline entry."""

    id: str
    type: str
    at: datetime
    by: dict[str, Any] | None
    data: dict[str, Any]


class BoardColumn(BaseModel):
    """One status column of the kanban board."""

    status: str
    count: int
    items: list[Load]


class LoadBoard(BaseModel):
    """Live loads grouped by status, every non-terminal status in machine order."""

    columns: list[BoardColumn]


KANBAN_STATUSES: tuple[str, ...] = tuple(status for status in machine.STATUSES if status not in machine.TERMINAL)


def _number(doc: Doc, key: str) -> float | None:
    """Read an optional number.

    Args:
        doc: Document.
        key: Field.

    Returns:
        The float, or None.
    """
    value = doc.get(key)
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _whole(doc: Doc, key: str) -> int | None:
    """Read an optional whole number.

    Args:
        doc: Document.
        key: Field.

    Returns:
        The int, or None.
    """
    value = doc.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def render_stop(stop: dict[str, Any]) -> Stop:
    """Render a stop.

    Args:
        stop: Stored stop.

    Returns:
        The model.
    """
    return Stop(id=str(stop.get("id")), seq=int(stop.get("seq") or 0), type=str(stop.get("type")),
                city=text_of(stop, "city"), state=text_of(stop, "state"), address=text_of(stop, "address"),
                facility_id=text_of(stop, "facility_id"), window_start=stop.get("window_start"),
                window_end=stop.get("window_end"))


def _window(load: Doc, kind: str) -> datetime | None:
    """Read the window start of the first pickup or the last delivery.

    Args:
        load: Load.
        kind: pickup or delivery.

    Returns:
        The time, or None.
    """
    stop = first_stop(load, kind) if kind == PICKUP else last_stop(load, kind)
    value = None if stop is None else stop.get("window_start")
    return value if isinstance(value, datetime) else None


def render_load(doc: Doc) -> Load:
    """Render a load.

    Args:
        doc: Load document.

    Returns:
        The model.
    """
    rate, miles = _whole(doc, "rate_cents"), _number(doc, "loaded_miles")
    evaluation = doc.get("evaluation")
    return Load(
        id=str(doc["_id"]), ref=str(doc["ref"]), status=str(doc["status"]), carrier_id=text_of(doc, "carrier_id"),
        driver_id=text_of(doc, "driver_id"), truck_id=text_of(doc, "truck_id"), broker_mc=text_of(doc, "broker_mc"),
        broker_name=text_of(doc, "broker_name"), broker_ref=text_of(doc, "broker_ref"), source=text_of(doc, "source"),
        lane=lane_text(doc), pickup_at=_window(doc, PICKUP), delivery_at=_window(doc, DELIVERY),
        stops=[render_stop(stop) for stop in mappings(doc.get("stops"))],
        equipment=text_of(doc, "equipment"), weight_lbs=_whole(doc, "weight_lbs"),
        commodity=text_of(doc, "commodity"), loaded_miles=miles, deadhead_miles=_number(doc, "deadhead_miles"),
        rate_cents=rate, rate_per_mile_cents=None if rate is None else money.per_mile_cents(rate, miles),
        accessorials=mappings(doc.get("accessorials")), evaluation=mapping(evaluation), notes=text_of(doc, "notes"),
        flag=bool(doc.get("flag")), cancelled_reason=text_of(doc, "cancelled_reason"), booked_at=doc.get("booked_at"),
        ratecon_approved=bool(doc.get("ratecon_approval")), status_changed_at=doc.get("status_changed_at"),
        created_at=doc["created_at"], updated_at=doc["updated_at"])


def render_event(doc: Doc) -> LoadEvent:
    """Render a timeline entry.

    Args:
        doc: load_events document.

    Returns:
        The model.
    """
    by, data = doc.get("by"), doc.get("data")
    return LoadEvent(id=str(doc["_id"]), type=str(doc["type"]), at=doc["at"], by=mapping(by),
                     data=mapping(data) or {})

