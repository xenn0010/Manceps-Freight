"""Error envelope `{"error": {"code", "message", "details"}}` and the handlers that enforce it everywhere."""

from __future__ import annotations

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, TypeVar

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from manceps_core.repo.errors import Conflict, Invalid, NotFound, RepoError
from manceps_core.tenancy import TenantError

log = structlog.get_logger(__name__)

STATUS_CODES: Mapping[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limited",
    503: "service_unavailable",
}
INTERNAL_MESSAGE = "internal server error"
VALIDATION_MESSAGE = "request validation failed"
TENANT_MESSAGE = "no active firm for this request"
VALIDATION_ERROR_KEYS = ("loc", "msg", "type")
REPLAY_HEADER = "Idempotency-Replayed"
REPO_STATUS: tuple[tuple[type[RepoError], int], ...] = ((NotFound, 404), (Conflict, 409), (Invalid, 422))
REPO_DEFAULT_STATUS = 400

ExcT = TypeVar("ExcT", bound=Exception)


class ErrorBody(BaseModel):
    """The inner error object."""

    code: str = Field(description="Stable machine-readable code, e.g. not_found or approval_required.")
    message: str = Field(description="Human-readable explanation, safe to show.")
    details: dict[str, Any] = Field(default_factory=dict[str, Any], description="Structured extra information.")


class ErrorEnvelope(BaseModel):
    """Every non-2xx response body."""

    error: ErrorBody


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    "4XX": {"model": ErrorEnvelope, "description": "Client error"},
    "5XX": {"model": ErrorEnvelope, "description": "Server error"},
}


class ApiError(Exception):
    """An error with a stable code, rendered as the envelope."""

    def __init__(self, status_code: int, code: str, message: str, details: Mapping[str, Any] | None = None,
                 headers: Mapping[str, str] | None = None) -> None:
        """Create the error.

        Args:
            status_code: HTTP status.
            code: Stable error code.
            message: Human-readable message (no secrets).
            details: Extra structured information.
            headers: Extra response headers, e.g. Retry-After.
        """
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details: dict[str, Any] = dict(details or {})
        self.headers: dict[str, str] | None = dict(headers) if headers else None


class ReplayResponse(Exception):
    """Short-circuits a request with a previously stored response (idempotent replay)."""

    def __init__(self, status_code: int, body: Any) -> None:
        """Carry the stored response.

        Args:
            status_code: Stored HTTP status.
            body: Stored JSON body.
        """
        super().__init__("idempotent replay")
        self.status_code = status_code
        self.body = body


def envelope(status_code: int, code: str, message: str, details: Mapping[str, Any] | None = None,
             headers: Mapping[str, str] | None = None) -> JSONResponse:
    """Build an envelope response.

    Args:
        status_code: HTTP status.
        code: Stable error code.
        message: Human-readable message.
        details: Extra information.
        headers: Extra headers.

    Returns:
        The JSON response.
    """
    body = ErrorEnvelope(error=ErrorBody(code=code, message=message, details=dict(details or {})))
    return JSONResponse(body.model_dump(mode="json"), status_code=status_code, headers=dict(headers or {}))


def _narrow(exc: Exception, kind: type[ExcT]) -> ExcT:
    """Narrow a handler's exception to the type it was registered for.

    Args:
        exc: Exception passed by the framework.
        kind: Expected type.

    Returns:
        The same exception, typed.

    Raises:
        TypeError: If the handler was registered for the wrong type.
    """
    if not isinstance(exc, kind):
        raise TypeError(f"handler for {kind.__name__} received {type(exc).__name__}")
    return exc


def _code_for(status_code: int) -> str:
    """Map an HTTP status to a default error code.

    Args:
        status_code: HTTP status.

    Returns:
        The code.
    """
    return STATUS_CODES.get(status_code, f"http_{status_code}")


async def _api_error(_request: Request, exc: Exception) -> JSONResponse:
    """Render ApiError.

    Args:
        _request: Request.
        exc: The ApiError.

    Returns:
        Envelope response.
    """
    error = _narrow(exc, ApiError)
    return envelope(error.status_code, error.code, error.message, error.details, error.headers)


async def _http_error(_request: Request, exc: Exception) -> JSONResponse:
    """Render framework HTTP errors (404 route, 405 method, ...).

    Args:
        _request: Request.
        exc: The HTTPException.

    Returns:
        Envelope response.
    """
    error = _narrow(exc, StarletteHTTPException)
    message = str(error.detail or HTTPStatus(error.status_code).phrase)
    return envelope(error.status_code, _code_for(error.status_code), message, None, error.headers)


async def _validation_error(_request: Request, exc: Exception) -> JSONResponse:
    """Render request validation errors without echoing submitted values.

    Args:
        _request: Request.
        exc: The RequestValidationError.

    Returns:
        422 envelope listing loc, msg and type per error.
    """
    error = _narrow(exc, RequestValidationError)
    errors = [{key: item.get(key) for key in VALIDATION_ERROR_KEYS} for item in error.errors()]
    return envelope(422, "validation_error", VALIDATION_MESSAGE, {"errors": errors})


async def _repo_error(_request: Request, exc: Exception) -> JSONResponse:
    """Render a repository refusal: not found 404, conflict 409, invalid 422.

    Args:
        _request: Request.
        exc: The RepoError.

    Returns:
        Envelope response.
    """
    error = _narrow(exc, RepoError)
    status = next((code for kind, code in REPO_STATUS if isinstance(error, kind)), REPO_DEFAULT_STATUS)
    return envelope(status, error.code, error.message, error.details)


async def _tenant_error(_request: Request, exc: Exception) -> JSONResponse:
    """Render a tenancy refusal as 403 without details.

    Args:
        _request: Request.
        exc: The TenantError.

    Returns:
        403 envelope.
    """
    log.warning("tenant.refused", reason=str(exc))
    return envelope(403, "tenant_required", TENANT_MESSAGE)


async def _replay(_request: Request, exc: Exception) -> JSONResponse:
    """Return a stored idempotent response.

    Args:
        _request: Request.
        exc: The ReplayResponse.

    Returns:
        The stored response with Idempotency-Replayed: true.
    """
    replay = _narrow(exc, ReplayResponse)
    return JSONResponse(replay.body, status_code=replay.status_code, headers={REPLAY_HEADER: "true"})


async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:
    """Log an unexpected exception and return a generic 500.

    Args:
        _request: Request.
        exc: The exception.

    Returns:
        500 envelope that reveals nothing about the failure.
    """
    log.error("request.unhandled_exception", exc_info=exc)
    return envelope(500, "internal_error", INTERNAL_MESSAGE)


def install_error_handlers(app: FastAPI) -> None:
    """Register every exception handler so all errors share the envelope.

    Args:
        app: The application.
    """
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(TenantError, _tenant_error)
    app.add_exception_handler(RepoError, _repo_error)
    app.add_exception_handler(ReplayResponse, _replay)
    app.add_exception_handler(Exception, _unhandled)
