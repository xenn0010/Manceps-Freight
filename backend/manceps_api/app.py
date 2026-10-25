"""Application factory: wires settings, database, middleware, error handlers and routers."""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from pymongo import MongoClient

from manceps_core.clock import Clock, utc_now
from manceps_core.mongo import Doc, MongoClientT
from manceps_core.tenancy import TenantDb

from . import health
from .auth.tokens import TokenService
from .context import AppContext
from .errors import ERROR_RESPONSES, REPLAY_HEADER, install_error_handlers
from .integrations.configured import Integrations
from .logs import configure_logging
from .middleware import REQUEST_ID_HEADER, BodyLimitMiddleware, BodyLimitRule, RequestContextMiddleware
from .routes import ROUTERS
from .settings import Settings, load_settings

API_TITLE = "Manceps API"
API_VERSION = "0.1.0"
OPENAPI_URL = "/v1/openapi.json"
SERVER_SELECTION_TIMEOUT_MS = 10_000
IMPORT_UPLOAD_PATH = re.compile(r"/v1/imports")
MULTIPART_OVERHEAD_BYTES = 64 * 1024

log = structlog.get_logger(__name__)


def _require_operation_id(route: APIRoute) -> str:
    """Refuse routes without an explicit, stable operation id.

    Args:
        route: Route being registered.

    Returns:
        Never returns.

    Raises:
        RuntimeError: Always; set operation_id="<resource>_<verb>" on the route.
    """
    raise RuntimeError(f"route {route.path} needs an explicit operation_id (<resource>_<verb>)")


def body_limit_rules(settings: Settings) -> tuple[BodyLimitRule, ...]:
    """Per-route request body limits that replace MAX_BODY_BYTES.

    The import upload (`POST /v1/imports`, WP1.4) carries a spreadsheet or vCard of up to IMPORT_MAX_BYTES plus its
    multipart framing; the route itself still enforces IMPORT_MAX_BYTES on the file while streaming it.

    Args:
        settings: Validated settings.

    Returns:
        The rules.
    """
    return (BodyLimitRule("POST", IMPORT_UPLOAD_PATH, settings.import_max_bytes + MULTIPART_OVERHEAD_BYTES),)


def create_app(settings: Settings, client: MongoClientT, clock: Clock = utc_now, owns_client: bool = False,
               integrations: Integrations | None = None) -> FastAPI:
    """Build the API application.

    Args:
        settings: Validated settings.
        client: MongoDB client for the platform and firm databases.
        clock: Time source.
        owns_client: Close the client on shutdown.
        integrations: External-service clients; built from settings when None.

    Returns:
        The FastAPI application.

    Raises:
        ValueError: If the configured JWT keys are malformed.
    """
    context = AppContext(
        settings, client, client[settings.platform_db], TenantDb(client), clock,
        integrations=integrations if integrations is not None else Integrations.from_settings(settings),
        tokens=TokenService.from_settings(settings, clock),
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
        context.ensure_indexes()
        try:
            yield
        finally:
            if owns_client:
                client.close()

    app = FastAPI(
        title=API_TITLE, version=API_VERSION, openapi_url=OPENAPI_URL, docs_url=None, redoc_url=None,
        lifespan=lifespan, responses=ERROR_RESPONSES, generate_unique_id_function=_require_operation_id,
    )
    app.state.context = context
    install_error_handlers(app)
    app.add_middleware(BodyLimitMiddleware, default_limit=settings.max_body_bytes, rules=body_limit_rules(settings))
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"],
            allow_headers=["*"], expose_headers=[REQUEST_ID_HEADER, REPLAY_HEADER],
        )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health.router)
    for router in ROUTERS:
        app.include_router(router)
    return app


def create_app_from_env() -> FastAPI:
    """Build the application from environment settings (the uvicorn factory).

    Returns:
        The FastAPI application.

    Raises:
        RuntimeError: If MONGODB_URI is not set.
        pydantic.ValidationError: If settings are invalid.
    """
    settings = load_settings()
    if settings.mongodb_uri is None:
        raise RuntimeError("MONGODB_URI is not set")
    configure_logging(settings.log_level)
    client: MongoClientT = MongoClient[Doc](
        settings.mongodb_uri.get_secret_value(), serverSelectionTimeoutMS=SERVER_SELECTION_TIMEOUT_MS, tz_aware=True,
    )
    log.info("app.configured", env=settings.env)
    return create_app(settings, client, owns_client=True)
