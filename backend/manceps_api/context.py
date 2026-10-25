"""Per-application context (settings, database handles, clock) stored on app.state and read by dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog
from fastapi import Request
from pymongo.errors import PyMongoError

from manceps_core.brokers.reference import REFERENCE_DB
from manceps_core.clock import Clock
from manceps_core.indexes import ensure_platform_indexes
from manceps_core.mongo import MongoClientT, MongoDb
from manceps_core.tenancy import Principal, TenantDb

from .auth.tokens import TokenService
from .exports.store import ExportStore
from .integrations.configured import Integrations
from .settings import Settings

log = structlog.get_logger(__name__)


@dataclass
class AppContext:
    """Everything a request handler needs from the process."""

    settings: Settings
    client: MongoClientT
    platform_db: MongoDb
    tenant_db: TenantDb
    clock: Clock
    integrations: Integrations = field(default_factory=Integrations)
    tokens: TokenService | None = None
    export_store: ExportStore | None = None
    indexes_ready: bool = False

    def ensure_indexes(self) -> bool:
        """Create platform indexes once; a failure leaves the app not ready instead of crashing it.

        Returns:
            True when the platform indexes exist.
        """
        if self.indexes_ready:
            return True
        try:
            ensure_platform_indexes(self.platform_db)
        except PyMongoError as exc:
            log.error("platform.indexes_failed", error_type=type(exc).__name__)
            return False
        self.indexes_ready = True
        return True

    def reference_db(self) -> MongoDb:
        """Return the shared, read-only FMCSA reference database.

        Returns:
            The `freight_reference` database.
        """
        return self.client[REFERENCE_DB]


def get_context(request: Request) -> AppContext:
    """Return the application context for a request.

    Args:
        request: Incoming request.

    Returns:
        The context.

    Raises:
        RuntimeError: If the app was not built by create_app.
    """
    context = getattr(request.app.state, "context", None)
    if not isinstance(context, AppContext):
        raise RuntimeError("application context is missing; build the app with create_app")
    return context


def firm_db(request: Request, principal: Principal) -> MongoDb:
    """Return the caller's firm database (the tenant comes only from the principal).

    Args:
        request: Incoming request.
        principal: Firm principal.

    Returns:
        The `firm_<tenant>` database.

    Raises:
        TenantError: If the principal has no firm.
    """
    return get_context(request).tenant_db.for_principal(principal)
