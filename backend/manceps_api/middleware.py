"""Request context middleware: request id, structlog context, and a redacted access log line per request."""

from __future__ import annotations

import re
import time
import uuid

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .logs import redact_query_string

REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
MS_PER_SECOND = 1000
UNKNOWN_STATUS = 500

log = structlog.get_logger(__name__)


def _incoming_request_id(scope: Scope) -> str | None:
    """Return a well-formed caller-supplied request id.

    Args:
        scope: ASGI scope.

    Returns:
        The id, or None when absent or malformed (never trusted for log injection).
    """
    wanted = REQUEST_ID_HEADER.lower().encode("latin-1")
    for name, value in scope.get("headers", []):
        if name == wanted:
            candidate = value.decode("latin-1")
            return candidate if REQUEST_ID_PATTERN.fullmatch(candidate) else None
    return None


class RequestContextMiddleware:
    """Pure ASGI middleware (safe for streaming responses) that binds request_id and logs each request."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap the inner app.

        Args:
            app: Inner ASGI app.
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle one ASGI call.

        Args:
            scope: ASGI scope.
            receive: Receive channel.
            send: Send channel.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = _incoming_request_id(scope) or uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id, tenant_id=None)
        scope.setdefault("state", {})["request_id"] = request_id
        status = UNKNOWN_STATUS

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message).append(REQUEST_ID_HEADER, request_id)
            await send(message)

        started = time.perf_counter()
        try:
            await self.app(scope, receive, send_with_id)
        finally:
            log.info(
                "http.request",
                method=scope.get("method"),
                path=scope.get("path"),
                query=redact_query_string(scope.get("query_string", b"").decode("latin-1")),
                status=status,
                duration_ms=round((time.perf_counter() - started) * MS_PER_SECOND, 2),
            )
