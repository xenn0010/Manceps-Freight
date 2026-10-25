"""ASGI middleware: request id, structlog context and a redacted access log line per request, and a request body
size limit for every route."""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

import structlog
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .errors import envelope
from .logs import redact_query_string

REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
MS_PER_SECOND = 1000
UNKNOWN_STATUS = 500
PAYLOAD_TOO_LARGE = 413
BODY_TOO_LARGE_MESSAGE = "the request body is too large"
CONTENT_LENGTH = b"content-length"

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


@dataclass(frozen=True)
class BodyLimitRule:
    """A per-route body limit replacing the default, e.g. spreadsheet uploads sized by IMPORT_MAX_BYTES."""

    method: str
    pattern: re.Pattern[str]
    limit: int


class BodyTooLarge(HTTPException):
    """The streamed body passed its limit; rendered as the 413 envelope by the app's HTTP error handler."""

    def __init__(self) -> None:
        """Create the error."""
        super().__init__(PAYLOAD_TOO_LARGE, BODY_TOO_LARGE_MESSAGE)


def _declared_length(scope: Scope) -> int | None:
    """Read the Content-Length header.

    Args:
        scope: ASGI scope.

    Returns:
        The declared length, or None when absent or malformed (the streamed byte count still applies).
    """
    for name, value in scope.get("headers", []):
        if name == CONTENT_LENGTH:
            text = value.decode("latin-1").strip()
            return int(text) if text.isdigit() else None
    return None


class BodyLimitMiddleware:
    """Pure ASGI middleware refusing request bodies over a limit with 413, before or while they stream in.

    A declared Content-Length over the limit is refused without reading the body; a chunked body is counted as it
    arrives and refused the moment it passes the limit, so no route ever buffers more than its limit.
    """

    def __init__(self, app: ASGIApp, default_limit: int, rules: Sequence[BodyLimitRule] = ()) -> None:
        """Wrap the inner app.

        Args:
            app: Inner ASGI app.
            default_limit: Bytes allowed when no rule matches.
            rules: Per-route overrides; the first matching method and path wins.

        Raises:
            ValueError: If a limit is not positive.
        """
        if default_limit <= 0 or any(rule.limit <= 0 for rule in rules):
            raise ValueError("body limits must be positive")
        self.app = app
        self.default_limit = default_limit
        self.rules = tuple(rules)

    def limit_for(self, scope: Scope) -> int:
        """Pick the limit for a request.

        Args:
            scope: ASGI scope.

        Returns:
            The matching rule's limit, else the default.
        """
        method, path = scope.get("method", ""), scope.get("path", "")
        for rule in self.rules:
            if rule.method == method and rule.pattern.fullmatch(path):
                return rule.limit
        return self.default_limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle one ASGI call.

        Args:
            scope: ASGI scope.
            receive: Receive channel.
            send: Send channel.

        Raises:
            BodyTooLarge: Only when the inner app already started its response before the limit was passed.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self.limit_for(scope)
        declared = _declared_length(scope)
        if declared is not None and declared > limit:
            await envelope(PAYLOAD_TOO_LARGE, "payload_too_large", BODY_TOO_LARGE_MESSAGE)(scope, receive, send)
            return
        received = 0
        started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise BodyTooLarge()
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except BodyTooLarge:
            if started:
                raise
            await envelope(PAYLOAD_TOO_LARGE, "payload_too_large", BODY_TOO_LARGE_MESSAGE)(scope, receive, send)
