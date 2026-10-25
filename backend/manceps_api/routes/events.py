"""Firm events: the live Server-Sent Events stream and a catch-up list for clients that cannot stream.

Stream frames: `id: <seq>`, `event: <type>` (approval.created, approval.decided, approval.applied,
approval.apply_failed, approval.expired, load.created, load.updated, load.status_changed, import.progress),
`data: {seq, type, ref, data, at}`. `: keepalive` comments are sent while idle. The server ends a stream after
SSE_MAX_STREAM_SECONDS, and sends `event: reset` when the client falls too far behind; in both cases the client
reconnects with `Last-Event-ID` (EventSource does this by itself) and nothing is lost.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Header, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from manceps_core.events import EVENTS

from ..auth.principal import FirmViewer, StreamViewer
from ..context import firm_db, get_context
from ..errors import ApiError
from ..pagination import DEFAULT_LIMIT, LimitQuery
from ..sse import EventHub, Subscription, TooManyStreams, stream_record

router = APIRouter(prefix="/v1", tags=["events"])

RETRY_MS = 3000
LAST_EVENT_ID_MAX = 20
KEEPALIVE = ": keepalive\n\n"
RESET = "event: reset\ndata: {}\n\n"
EVENT_STREAM = "text/event-stream"
NO_BUFFERING = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class Event(BaseModel):
    """One firm event."""

    seq: int
    type: str
    ref: dict[str, Any] | None
    data: dict[str, Any]
    at: datetime


class EventPage(BaseModel):
    """Events after a sequence number; pass next_after back as `after` until it is null."""

    items: list[Event]
    next_after: int | None


def _last_seq(raw: str | None) -> int | None:
    """Parse a Last-Event-ID header.

    Args:
        raw: Header value.

    Returns:
        The sequence number, or None when absent.

    Raises:
        ApiError: 400 invalid_last_event_id.
    """
    if raw is None or raw == "":
        return None
    if not raw.isdigit():
        raise ApiError(400, "invalid_last_event_id", "Last-Event-ID must be an event sequence number")
    return int(raw)


def frame(event: dict[str, Any]) -> str:
    """Render one SSE frame.

    Args:
        event: Stored event.

    Returns:
        The frame text.
    """
    record = stream_record(event)
    data = json.dumps(jsonable_encoder(record), separators=(",", ":"))
    return f"id: {record['seq']}\nevent: {record['type']}\ndata: {data}\n\n"


async def _frames(hub: EventHub, sub: Subscription, keepalive: float, lifetime: float) -> AsyncIterator[str]:
    """Yield frames for one subscription until its lifetime ends, it overflows, or the client leaves.

    Args:
        hub: Event hub.
        sub: Subscription.
        keepalive: Seconds between keepalive comments while idle.
        lifetime: Seconds before the server ends the stream.

    Yields:
        SSE text.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + lifetime
    try:
        yield f"retry: {RETRY_MS}\n\n"
        while True:
            if sub.reset:
                yield RESET
                return
            remaining = deadline - loop.time()
            if remaining <= 0:
                return
            try:
                event = await asyncio.wait_for(sub.queue.get(), timeout=min(keepalive, remaining))
            except TimeoutError:
                yield KEEPALIVE
                continue
            yield frame(event)
    finally:
        hub.unsubscribe(sub)


@router.get("/events/stream", operation_id="events_stream", summary="Live firm events (SSE)",
            response_class=StreamingResponse,
            responses={200: {"content": {EVENT_STREAM: {"schema": {"type": "string"}}},
                             "description": "text/event-stream of firm events."}})
async def events_stream(request: Request, principal: StreamViewer,
                        last_event_id: Annotated[str | None, Header(max_length=LAST_EVENT_ID_MAX)] = None,
                        ) -> StreamingResponse:
    """Stream the firm's events. Auth: bearer header, or `?access_token=` for EventSource (this route only).

    Args:
        request: Incoming request.
        principal: Firm member.
        last_event_id: Resume after this sequence number (EventSource sends it on reconnect).

    Returns:
        The event stream.

    Raises:
        ApiError: 400 invalid_last_event_id, 429 too_many_streams, 503 events_unavailable.
    """
    context = get_context(request)
    hub = context.event_hub
    if hub is None:
        raise ApiError(503, "events_unavailable", "live events are not available on this server")
    try:
        sub = await hub.subscribe(principal, _last_seq(last_event_id))
    except TooManyStreams as exc:
        raise ApiError(429, "too_many_streams", "close another tab or device to open a new live stream",
                       headers={"Retry-After": str(int(context.settings.sse_max_stream_seconds))}) from exc
    await hub.tick(str(principal.tenant_id))
    settings = context.settings
    return StreamingResponse(_frames(hub, sub, settings.sse_keepalive_seconds, settings.sse_max_stream_seconds),
                             media_type=EVENT_STREAM, headers=NO_BUFFERING)


@router.get("/events", operation_id="events_list", summary="Firm events after a sequence number")
def events_list(request: Request, principal: FirmViewer, after: Annotated[int, Query(ge=0)] = 0,
                limit: LimitQuery = DEFAULT_LIMIT) -> EventPage:
    """List events with seq > after, oldest first (catch-up for clients that cannot use SSE).

    Args:
        request: Incoming request.
        principal: Firm member.
        after: Last sequence number seen.
        limit: Page size.

    Returns:
        One page.
    """
    found = list(firm_db(request, principal)[EVENTS].find({"seq": {"$gt": after}}, {"_id": 0},
                                                          limit=limit + 1).sort([("seq", 1)]))
    items = [Event.model_validate(stream_record(event)) for event in found[:limit]]
    return EventPage(items=items, next_after=items[-1].seq if len(found) > limit else None)
