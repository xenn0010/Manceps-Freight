"""Read models for the dispatch screen: the truck board and the weekly dashboard."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from manceps_core.loads import board, dashboard, money
from manceps_core.loads.views import DELIVERY, PICKUP, first_stop, lane_text, last_stop
from manceps_core.mongo import Doc
from manceps_core.repo.fleet import TRUCKS
from manceps_core.repo.load_fields import BOOKABLE_CARRIER_STATUSES
from manceps_core.repo.store import list_live

from ..auth.principal import FirmViewer
from ..context import firm_db, get_context
from ..errors import ApiError
from ..firmzone import firm_zone
from ..pagination import DEFAULT_LIMIT, CursorQuery, LimitQuery, Page, decode_cursor, encode_cursor
from .common import text_of

router = APIRouter(prefix="/v1", tags=["board"])

DEFAULT_CARRIER_STATUS = "onboarding"
BoardStatus = Literal["open", "offered", "needs_approval", "booked", "in_transit", "at_pickup", "at_delivery",
                      "delivered"]
Tone = Literal["grey", "amber", "green"]
STATUS_DOC = ("Derived: no current load = open (amber); a pending approval on the load before dispatch = "
              "needs_approval (amber); offered/evaluating/countered = offered (grey); approved/booked/"
              "ratecon_received/dispatched = booked (green); at_pickup, in_transit, at_delivery = same name (green); "
              "delivered/pod_received/invoiced = delivered (grey).")
ELD_DOC = "Always null until an ELD integration reports it; never estimated."


class BoardDriver(BaseModel):
    """The truck's driver."""

    id: str
    name: str | None
    phone: str | None


class BoardLoad(BaseModel):
    """The truck's current load, with the facts the board card shows."""

    id: str
    ref: str
    status: str
    lane: str | None
    broker_name: str | None
    broker_ref: str | None
    rate_cents: int | None
    rate_per_mile_cents: int | None
    loaded_miles: float | None
    deadhead_miles: float | None
    commodity: str | None
    weight_lbs: int | None
    equipment: str | None
    pickup_at: datetime | None
    delivery_at: datetime | None


class BoardRow(BaseModel):
    """One active truck on the dispatch board."""

    truck_id: str
    unit: str
    equipment: str | None
    carrier_id: str
    carrier_name: str | None
    driver: BoardDriver | None
    home_base: str | None = Field(description="The carrier's home base (not a position).")
    status: BoardStatus = Field(description=STATUS_DOC)
    tone: Tone
    now: str = Field(description="What the current load is doing, from its status and stops only.")
    next: str | None = Field(description="Next stop and window in the firm's timezone.")
    load: BoardLoad | None
    pending_approval: bool
    position: dict[str, Any] | None = Field(description=ELD_DOC)
    hos: dict[str, Any] | None = Field(description="Hours of service. " + ELD_DOC)
    duty: str | None = Field(description="Duty status. " + ELD_DOC)


class DayTotal(BaseModel):
    """One day of a week."""

    date: date
    revenue_cents: int
    loads_booked: int


class WeekTotal(BaseModel):
    """One week's totals."""

    days: list[DayTotal]
    revenue_cents: int
    loads_booked: int
    loaded_miles: float


class DashboardSummary(BaseModel):
    """Revenue by booking day for the firm's week and the week before (loads booked or later, firm timezone)."""

    week_start: date
    timezone: str
    this_week: WeekTotal
    last_week: WeekTotal
    revenue_change_cents: int
    avg_rate_per_mile_cents: int | None = Field(description="This week's revenue / loaded miles, rounded half up.")


def _board_load(load: Doc) -> BoardLoad:
    """Render the current load for a card.

    Args:
        load: Load.

    Returns:
        The model.
    """
    rate, miles = load.get("rate_cents"), load.get("loaded_miles")
    rate = rate if isinstance(rate, int) and not isinstance(rate, bool) else None
    miles = float(miles) if isinstance(miles, int | float) and not isinstance(miles, bool) else None
    deadhead, weight = load.get("deadhead_miles"), load.get("weight_lbs")
    pickup, delivery = first_stop(load, PICKUP), last_stop(load, DELIVERY)
    return BoardLoad(
        id=str(load["_id"]), ref=str(load["ref"]), status=str(load["status"]), lane=lane_text(load),
        broker_name=text_of(load, "broker_name"), broker_ref=text_of(load, "broker_ref"), rate_cents=rate,
        rate_per_mile_cents=None if rate is None else money.per_mile_cents(rate, miles), loaded_miles=miles,
        deadhead_miles=float(deadhead) if isinstance(deadhead, int | float) else None,
        commodity=text_of(load, "commodity"), weight_lbs=weight if isinstance(weight, int) else None,
        equipment=text_of(load, "equipment"), pickup_at=None if pickup is None else pickup.get("window_start"),
        delivery_at=None if delivery is None else delivery.get("window_start"))


def _row(truck: Doc, carrier: Doc, context: dict[str, Any], zone: ZoneInfo) -> BoardRow:
    """Build one board row.

    Args:
        truck: Truck.
        carrier: Its carrier.
        context: Output of board.board_context.
        zone: Firm timezone.

    Returns:
        The row.
    """
    load: Doc | None = context["current"].get(str(truck["_id"]))
    pending = load is not None and str(load["_id"]) in context["pending"]
    driver_id = truck.get("driver_id") or (None if load is None else load.get("driver_id"))
    driver = context["drivers"].get(str(driver_id)) if driver_id else None
    status = board.board_status(load, pending)
    return BoardRow(
        truck_id=str(truck["_id"]), unit=str(truck["unit"]), equipment=text_of(truck, "equipment"),
        carrier_id=str(carrier["_id"]), carrier_name=text_of(carrier, "name") or text_of(carrier, "company"),
        driver=None if driver is None else BoardDriver(id=str(driver["_id"]), name=text_of(driver, "name"),
                                                       phone=text_of(driver, "phone")),
        home_base=text_of(carrier, "home_base"), status=status, tone=board.TONES[status],  # pyright: ignore[reportArgumentType]
        now=board.now_text(load), next=board.next_text(load, zone), load=None if load is None else _board_load(load),
        pending_approval=pending, position=None, hos=None, duty=None)


@router.get("/board", operation_id="board_list", summary="Dispatch board")
def board_list(request: Request, principal: FirmViewer, limit: LimitQuery = DEFAULT_LIMIT,
               cursor: CursorQuery = None) -> Page[BoardRow]:
    """One row per active truck (live truck of an active or onboarding carrier), oldest truck first.

    A page may hold fewer rows than `limit` when trucks of paused carriers were skipped; keep following
    `next_cursor` until it is null.

    Args:
        request: Incoming request.
        principal: Firm member.
        limit: Trucks scanned per page.
        cursor: Cursor from the previous page.

    Returns:
        One page of rows.

    Raises:
        ApiError: 400 invalid_cursor.
    """
    db = firm_db(request, principal)
    docs = list_live(db, TRUCKS, {}, decode_cursor(cursor), limit)
    trucks = docs[:limit]
    context = board.board_context(db, trucks, get_context(request).clock())
    zone = firm_zone(request, principal)
    rows: list[BoardRow] = []
    for truck in trucks:
        carrier = context["carriers"].get(str(truck.get("carrier_id")))
        if carrier is not None and str(carrier.get("status") or DEFAULT_CARRIER_STATUS) in BOOKABLE_CARRIER_STATUSES:
            rows.append(_row(truck, carrier, context, zone))
    next_cursor = encode_cursor(trucks[-1]["_id"]) if len(docs) > limit else None
    return Page[BoardRow](items=rows, next_cursor=next_cursor)


@router.get("/dashboard/summary", operation_id="dashboard_summary", summary="Weekly dashboard")
def dashboard_summary(request: Request, principal: FirmViewer,
                      week_start: Annotated[date | None, Query(description="A Monday (firm-local); default: this "
                                                                           "week.")] = None) -> DashboardSummary:
    """Revenue per day this week vs last week, loads booked and average $/mile, in the firm's timezone.

    Args:
        request: Incoming request.
        principal: Firm member.
        week_start: The week's Monday.

    Returns:
        The summary.

    Raises:
        ApiError: 422 when week_start is not a Monday.
    """
    zone = firm_zone(request, principal)
    start = week_start or dashboard.week_start_of(get_context(request).clock(), zone)
    try:
        result = dashboard.summary(firm_db(request, principal), start, zone)
    except ValueError as exc:
        raise ApiError(422, "validation_error", str(exc), {"errors": [
            {"loc": ["query", "week_start"], "msg": str(exc), "type": "value_error"}]}) from exc
    return DashboardSummary.model_validate(result)
