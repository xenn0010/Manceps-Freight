"""Tenant resolution: one Hermes profile is one dispatch firm with its own database.

The tenant id and connection string come only from the active profile's secrets
(Hermes `.env`, resolved through the profile-scoped secret lookup). Tool arguments
never select a tenant, so the model cannot address another firm's data. A missing
tenant id is an error, never a silent default.
"""

from __future__ import annotations

import os
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pymongo
from pymongo.database import Database

TENANT_ENV = "FREIGHT_TENANT_ID"
URI_ENV = "MONGODB_URI"
DB_PREFIX = "firm_"
TENANT_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,30}[a-z0-9]$")
SERVER_SELECTION_TIMEOUT_MS = 10000

ClientFactory = Callable[[str], pymongo.MongoClient]


class TenantError(RuntimeError):
    """The active profile has no valid tenant configuration."""


@dataclass(frozen=True)
class Tenant:
    """A dispatch firm bound to the active Hermes profile."""

    tenant_id: str
    uri: str

    @property
    def db_name(self) -> str:
        """Return the firm's database name."""
        return database_name(self.tenant_id)


def validate_tenant_id(tenant_id: str) -> str:
    """Check a tenant id is a safe lowercase slug.

    Args:
        tenant_id: Proposed id, e.g. "apex-freight".

    Returns:
        The id unchanged.

    Raises:
        TenantError: If the id is not 3 to 32 chars of [a-z0-9-] starting with a letter.
    """
    if not TENANT_PATTERN.fullmatch(tenant_id or ""):
        raise TenantError(f"invalid tenant id {tenant_id!r}: use 3-32 chars, a-z 0-9 '-', start with a letter")
    return tenant_id


def database_name(tenant_id: str) -> str:
    """Map a tenant id to its MongoDB database name.

    Args:
        tenant_id: Valid tenant id.

    Returns:
        Database name such as "firm_apex_freight".
    """
    return DB_PREFIX + validate_tenant_id(tenant_id).replace("-", "_")


def secret(name: str) -> str | None:
    """Read a secret from the active profile's scope.

    Args:
        name: Environment variable name.

    Returns:
        The value, or None when unset.
    """
    try:
        from agent.secret_scope import get_secret  # pyright: ignore[reportMissingImports]  # provided by Hermes
    except ImportError:
        return os.environ.get(name)
    return get_secret(name)


def hermes_home() -> Path:
    """Return the active profile's Hermes home directory.

    Returns:
        The profile home (context-local under a multiplexed gateway).
    """
    try:
        from hermes_constants import get_hermes_home  # pyright: ignore[reportMissingImports]  # provided by Hermes
    except ImportError:
        return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    return get_hermes_home()


def current() -> Tenant:
    """Resolve the tenant bound to the active profile.

    Returns:
        The tenant.

    Raises:
        TenantError: If the tenant id or URI is missing or invalid.
    """
    tenant_id = (secret(TENANT_ENV) or "").strip()
    if not tenant_id:
        raise TenantError(f"{TENANT_ENV} is not set for this profile; provision the firm first")
    uri = (secret(URI_ENV) or "").strip()
    if not uri:
        raise TenantError(f"{URI_ENV} is not set for this profile")
    return Tenant(validate_tenant_id(tenant_id), uri)


def _default_factory(uri: str) -> pymongo.MongoClient:
    """Build a real client for a connection string.

    Args:
        uri: MongoDB connection string.

    Returns:
        A lazily connecting client.
    """
    return pymongo.MongoClient(uri, serverSelectionTimeoutMS=SERVER_SELECTION_TIMEOUT_MS, tz_aware=True)


_lock = threading.Lock()
_clients: dict[str, pymongo.MongoClient] = {}
_initialized: set[tuple[str, str]] = set()
_factory: ClientFactory = _default_factory


def set_client_factory(factory: ClientFactory | None) -> None:
    """Replace how clients are built and drop cached ones (tests, tooling).

    Args:
        factory: Callable taking a URI, or None to restore the real driver.
    """
    global _factory
    with _lock:
        _factory = factory or _default_factory
        _clients.clear()
        _initialized.clear()


def _client_for(uri: str) -> pymongo.MongoClient:
    """Return the cached client for a connection string, creating it once.

    Args:
        uri: MongoDB connection string.

    Returns:
        The client.
    """
    with _lock:
        client = _clients.get(uri)
        if client is None:
            client = _factory(uri)
            _clients[uri] = client
        return client


def shared_database(name: str) -> Database:
    """Return a shared, read-only reference database through the tenant's own connection.

    The firm's database user must be granted read on it; tools never write to it.

    Args:
        name: Database name, e.g. "freight_reference".

    Returns:
        The database handle.

    Raises:
        TenantError: If the profile has no tenant.
    """
    return _client_for(current().uri)[name]


def database(on_first_use: Callable[[Database], None]) -> Database:
    """Return the active tenant's database, one cached client per connection string.

    Args:
        on_first_use: Called once per (uri, database) pair, e.g. to create indexes.

    Returns:
        The tenant database.

    Raises:
        TenantError: If the profile has no tenant.
    """
    tenant = current()
    client = _client_for(tenant.uri)
    with _lock:
        key = (tenant.uri, tenant.db_name)
        first = key not in _initialized
    db = client[tenant.db_name]
    if first:
        on_first_use(db)
        with _lock:
            _initialized.add(key)
    return db
