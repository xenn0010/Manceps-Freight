"""Test fixtures: load the plugin as a package and back it with an in-memory MongoDB."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType

import mongomock
import pytest

PLUGIN_DIR = Path(__file__).resolve().parent.parent
PACKAGE = "hermes_freight"
SHARED_URI = "mongodb://shared-cluster.test"


def _load_package() -> ModuleType:
    """Import the plugin directory as the `hermes_freight` package.

    Returns:
        The imported package.
    """
    if PACKAGE in sys.modules:
        return sys.modules[PACKAGE]
    spec = importlib.util.spec_from_file_location(
        PACKAGE, PLUGIN_DIR / "__init__.py", submodule_search_locations=[str(PLUGIN_DIR)]
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = module
    spec.loader.exec_module(module)
    return module


freight = _load_package()

from hermes_freight import tenant  # noqa: E402


@pytest.fixture(autouse=True)
def mongo(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, mongomock.MongoClient]]:
    """Give every URI its own in-memory server and clear tenant env between tests.

    Yields:
        Mapping of URI to its mongomock client.
    """
    servers: dict[str, mongomock.MongoClient] = {}

    def factory(uri: str) -> mongomock.MongoClient:
        return servers.setdefault(uri, mongomock.MongoClient(tz_aware=True))

    tenant.set_client_factory(factory)
    for name in (tenant.TENANT_ENV, tenant.URI_ENV, "FREIGHT_DISPATCHER_PHONE", "FMCSA_WEBKEY",
                 "GOOGLE_MAPS_API_KEY", "ORS_API_KEY", "EIA_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    yield servers
    tenant.set_client_factory(None)


@pytest.fixture
def as_tenant(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Switch the active profile's tenant, as a Hermes profile .env would.

    Returns:
        Function taking a tenant id and optional URI.
    """

    def switch(tenant_id: str, uri: str = SHARED_URI) -> None:
        monkeypatch.setenv(tenant.TENANT_ENV, tenant_id)
        monkeypatch.setenv(tenant.URI_ENV, uri)

    return switch
