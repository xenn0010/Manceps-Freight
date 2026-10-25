"""Liveness and readiness probes (public)."""

from __future__ import annotations

from typing import Literal

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel
from pymongo.errors import PyMongoError

from .context import get_context
from .errors import ApiError, ErrorEnvelope

log = structlog.get_logger(__name__)
router = APIRouter(tags=["meta"])


class Health(BaseModel):
    """Probe result."""

    status: Literal["ok"]


@router.get("/healthz", operation_id="health_get", summary="Liveness probe")
def health_get() -> Health:
    """Report that the process is serving requests; never touches the database.

    Returns:
        {"status": "ok"}.
    """
    return Health(status="ok")


@router.get(
    "/readyz",
    operation_id="readiness_get",
    summary="Readiness probe",
    responses={503: {"model": ErrorEnvelope, "description": "Database unavailable"}},
)
def readiness_get(request: Request) -> Health:
    """Report readiness: the database answers a ping and the platform indexes exist.

    Args:
        request: Incoming request.

    Returns:
        {"status": "ok"}.

    Raises:
        ApiError: 503 database_unavailable when the database is unreachable or indexes are missing.
    """
    context = get_context(request)
    try:
        context.client.admin.command("ping")
    except PyMongoError as exc:
        log.warning("readiness.ping_failed", error_type=type(exc).__name__)
        raise ApiError(503, "database_unavailable", "the database is unavailable") from exc
    if not context.ensure_indexes():
        raise ApiError(503, "database_unavailable", "the database is unavailable")
    return Health(status="ok")
