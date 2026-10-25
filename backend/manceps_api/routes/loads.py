"""Loads: list, create, read, inline edit, transition, evaluate, stops, timeline and the kanban board."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from pydantic import AwareDatetime

from manceps_core.loads import machine
from manceps_core.loads.evaluate import DEFAULT_MPG
from manceps_core.repo import fields, load_eval, load_status, load_stops, loads
from manceps_core.repo.store import LIVE

from ..auditing import write_context
from ..auth.principal import FirmDispatcher, FirmIdempotency, FirmViewer
from ..context import firm_db, get_context
from ..pagination import DEFAULT_LIMIT, MAX_LIMIT, CursorQuery, LimitQuery, Page, decode_cursor, page_of
from .common import ID_MAX, RecordId
from .load_models import (
    KANBAN_STATUSES,
    BoardColumn,
    EvaluateInput,
    Load,
    LoadBoard,
    LoadCreate,
    LoadEvent,
    LoadPatch,
    LoadStatus,
    StopAdd,
    StopPatch,
    TransitionInput,
    render_event,
    render_load,
)

router = APIRouter(prefix="/v1", tags=["loads"])

DEFAULT_PER_STATUS = 20
IdFilter = Annotated[str | None, Query(max_length=ID_MAX)]


@router.get("/loads", operation_id="loads_list", summary="List loads")
def loads_list(request: Request, principal: FirmViewer, status: LoadStatus | None = None,
               carrier_id: IdFilter = None, driver_id: IdFilter = None, truck_id: IdFilter = None,
               broker_mc: IdFilter = None, flag: bool | None = None, pickup_from: AwareDatetime | None = None,
               pickup_to: AwareDatetime | None = None,
               q: Annotated[str | None, Query(max_length=fields.QUERY_MAX)] = None,
               limit: LimitQuery = DEFAULT_LIMIT, cursor: CursorQuery = None) -> Page[Load]:
    """List live loads, newest first (the loads sheet).

    Args:
        request: Incoming request.
        principal: Firm member.
        status: Only this status.
        carrier_id: Only this carrier.
        driver_id: Only this driver.
        truck_id: Only this truck.
        broker_mc: Only this broker MC (digits).
        flag: Only flagged (true) or unflagged (false) loads.
        pickup_from: First pickup window starts at or after.
        pickup_to: First pickup window starts before.
        q: Ref, broker name or broker ref contains.
        limit: Page size.
        cursor: Cursor from the previous page.

    Returns:
        One page.

    Raises:
        ApiError: 400 invalid_cursor.
    """
    filters: dict[str, Any] = {"status": status, "carrier_id": carrier_id, "driver_id": driver_id,
                               "truck_id": truck_id, "broker_mc": broker_mc, "flag": flag,
                               "pickup_from": pickup_from, "pickup_to": pickup_to, "q": q}
    docs = loads.list_loads(firm_db(request, principal), filters, decode_cursor(cursor), limit)
    return page_of(docs, limit, render_load)


@router.post("/loads", status_code=201, operation_id="loads_create", summary="Create a load")
def loads_create(body: LoadCreate, request: Request, principal: FirmDispatcher, guard: FirmIdempotency) -> Load:
    """Create a load in `offered` (audited, emits load.created).

    Args:
        body: Load fields.
        request: Incoming request.
        principal: Dispatcher or owner.
        guard: Idempotency guard.

    Returns:
        The load.

    Raises:
        RepoError: 422 on invalid values or references outside this firm.
    """
    doc = loads.create_load(firm_db(request, principal), write_context(request, principal),
                            body.model_dump(exclude_unset=True))
    load = render_load(doc)
    guard.save(201, load.model_dump(mode="json"))
    return load


@router.get("/loads/board", operation_id="loads_board", summary="Loads grouped by status")
def loads_board(request: Request, principal: FirmViewer,
                per_status: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_PER_STATUS) -> LoadBoard:
    """Group live, non-terminal loads by status for a kanban view (newest first in each column).

    Args:
        request: Incoming request.
        principal: Firm member.
        per_status: Most loads returned per column (count is always exact).

    Returns:
        The columns.
    """
    db = firm_db(request, principal)
    columns: list[BoardColumn] = []
    for status in KANBAN_STATUSES:
        query = {"status": status, **LIVE}
        items = list(db[loads.LOADS].find(query, limit=per_status).sort([("_id", -1)]))
        columns.append(BoardColumn(status=status, count=db[loads.LOADS].count_documents(query),
                                   items=[render_load(item) for item in items]))
    return LoadBoard(columns=columns)


@router.get("/loads/{load_id}", operation_id="loads_get", summary="Get a load")
def loads_get(load_id: RecordId, request: Request, principal: FirmViewer) -> Load:
    """Return one live load.

    Args:
        load_id: Load id.
        request: Incoming request.
        principal: Firm member.

    Returns:
        The load.

    Raises:
        RepoError: 404.
    """
    return render_load(loads.get_load(firm_db(request, principal), load_id))


@router.patch("/loads/{load_id}", operation_id="loads_update", summary="Edit a load")
def loads_update(load_id: RecordId, body: LoadPatch, request: Request, principal: FirmDispatcher) -> Load:
    """Edit load cells (audited). The rate or carrier of an accepted load, and a status of approved or booked (or
    cancelling a booked load), answer 409 approval_required naming the approval kind.

    Args:
        load_id: Load id.
        body: Changes.
        request: Incoming request.
        principal: Dispatcher or owner.

    Returns:
        The load.

    Raises:
        RepoError: 404, 409 approval_required, illegal_transition, load_closed or carrier_required, 422.
    """
    db, ctx = firm_db(request, principal), write_context(request, principal)
    changes = body.model_dump(exclude_unset=True)
    target = changes.pop("status", None)
    if target is None:
        return render_load(loads.update_load(db, ctx, load_id, changes))
    current = loads.get_load(db, load_id)
    if target != current.get("status"):
        machine.check_direct(str(current.get("status")), str(target))
    doc = loads.update_load(db, ctx, load_id, changes) if changes else current
    if target != doc.get("status"):
        doc = load_status.transition(db, ctx, load_id, str(target))
    return render_load(doc)


@router.post("/loads/{load_id}/transition", operation_id="loads_transition", summary="Move a load")
def loads_transition(load_id: RecordId, body: TransitionInput, request: Request, principal: FirmDispatcher) -> Load:
    """Move a load along the status table (audited, emits load.status_changed).

    Args:
        load_id: Load id.
        body: Target status and optional reason.
        request: Incoming request.
        principal: Dispatcher or owner.

    Returns:
        The load.

    Raises:
        RepoError: 404, 409 illegal_transition, approval_required, carrier_required or status_changed, 422.
    """
    return render_load(load_status.transition(firm_db(request, principal), write_context(request, principal),
                                              load_id, body.to, body.reason))


@router.post("/loads/{load_id}/evaluate", operation_id="loads_evaluate", summary="Evaluate a load")
def loads_evaluate(load_id: RecordId, body: EvaluateInput, request: Request, principal: FirmDispatcher) -> Load:
    """Run the economics (miles, diesel, fee, net, floor verdict) and store them on the load.

    Inputs whose service is not configured or fails are reported unknown, and the verdict is then never accept.
    An offered load moves to evaluating.

    Args:
        load_id: Load id.
        body: Options.
        request: Incoming request.
        principal: Dispatcher or owner.

    Returns:
        The load with `evaluation`.

    Raises:
        RepoError: 404, 409 load_closed.
    """
    integrations = get_context(request).integrations
    doc = load_eval.evaluate_load(firm_db(request, principal), write_context(request, principal), load_id,
                                  integrations.miles, integrations.diesel, body.mpg or DEFAULT_MPG)
    return render_load(doc)


@router.post("/loads/{load_id}/stops", status_code=201, operation_id="load_stops_create", summary="Add a stop")
def load_stops_create(load_id: RecordId, body: StopAdd, request: Request, principal: FirmDispatcher) -> Load:
    """Insert a stop (audited).

    Args:
        load_id: Load id.
        body: Stop fields and position.
        request: Incoming request.
        principal: Dispatcher or owner.

    Returns:
        The load.

    Raises:
        RepoError: 404, 409 load_closed, 422.
    """
    stop = body.model_dump(exclude_unset=True, exclude={"position", "id"})
    return render_load(load_stops.add_stop(firm_db(request, principal), write_context(request, principal), load_id,
                                           stop, body.position))


@router.patch("/loads/{load_id}/stops/{stop_id}", operation_id="load_stops_update", summary="Change a stop")
def load_stops_update(load_id: RecordId, stop_id: RecordId, body: StopPatch, request: Request,
                      principal: FirmDispatcher) -> Load:
    """Change one stop (audited).

    Args:
        load_id: Load id.
        stop_id: Stop id.
        body: Changes.
        request: Incoming request.
        principal: Dispatcher or owner.

    Returns:
        The load.

    Raises:
        RepoError: 404, 409 load_closed, 422.
    """
    return render_load(load_stops.update_stop(firm_db(request, principal), write_context(request, principal),
                                              load_id, stop_id, body.model_dump(exclude_unset=True)))


@router.delete("/loads/{load_id}/stops/{stop_id}", operation_id="load_stops_delete", summary="Remove a stop")
def load_stops_delete(load_id: RecordId, stop_id: RecordId, request: Request, principal: FirmDispatcher) -> Load:
    """Remove one stop (audited).

    Args:
        load_id: Load id.
        stop_id: Stop id.
        request: Incoming request.
        principal: Dispatcher or owner.

    Returns:
        The load.

    Raises:
        RepoError: 404, 409 load_closed.
    """
    return render_load(load_stops.delete_stop(firm_db(request, principal), write_context(request, principal),
                                              load_id, stop_id))


@router.get("/loads/{load_id}/events", operation_id="load_events_list", summary="Load timeline")
def load_events_list(load_id: RecordId, request: Request, principal: FirmViewer, limit: LimitQuery = DEFAULT_LIMIT,
                     cursor: CursorQuery = None) -> Page[LoadEvent]:
    """List a load's timeline, oldest first.

    Args:
        load_id: Load id.
        request: Incoming request.
        principal: Firm member.
        limit: Page size.
        cursor: Cursor from the previous page.

    Returns:
        One page.

    Raises:
        RepoError: 404.
        ApiError: 400 invalid_cursor.
    """
    docs = load_status.list_events(firm_db(request, principal), load_id, decode_cursor(cursor), limit)
    return page_of(docs, limit, render_event)
