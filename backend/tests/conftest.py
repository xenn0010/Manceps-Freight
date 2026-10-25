"""Shared fixtures: MongoDB (in-memory, or a real server when MONGODB_TEST_URI is set), a controllable clock,
settings, and the app under test.

Real-database mode (META gate 8): with MONGODB_TEST_URI set, every test gets a client whose database names carry a
unique per-test prefix, and those databases are dropped after the test. Tests marked `mongomock_only` (they patch
mongomock internals) are deselected there; tests marked `realdb` (concurrency, TTL and unique-index behavior,
query plans) run only there.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import mongomock
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pymongo import MongoClient
from pymongo.database import Database

from manceps_api.app import create_app
from manceps_api.integrations.configured import Integrations
from manceps_api.integrations.twilio_verify import VerifyError
from manceps_api.settings import Settings
from manceps_core.indexes import ensure_platform_indexes
from manceps_core.mongo import Doc, MongoClientT, MongoDb
from manceps_core.tenancy import Principal, PrincipalKind, Role

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
PLUGIN_DIR = REPO_ROOT / "hermes-freight"
SIGNUP_API_DIR = REPO_ROOT / "signup-api"
PLUGIN_PACKAGE = "hf_probe_plugin"
START = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
TENANT_A = "apex-freight"
TENANT_B = "bolt-logistics"
TEST_KID = "k-test-1"
GOOD_CODE = "123456"
TEST_URI_VARIABLE = "MONGODB_TEST_URI"
MONGODB_TEST_URI = os.environ.get(TEST_URI_VARIABLE, "").strip()
REAL_DB = bool(MONGODB_TEST_URI)
REAL_DB_TIMEOUT_MS = 5000
PREFIX_HEX_CHARS = 10


def ed25519_pem_pair() -> tuple[str, str]:
    """Generate a fresh Ed25519 key pair for signing test tokens.

    Returns:
        (private PEM, public PEM).
    """
    private = Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode("ascii")
    public_pem = private.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode("ascii")
    return private_pem, public_pem


TEST_PRIVATE_PEM, TEST_PUBLIC_PEM = ed25519_pem_pair()
TEST_KEYS_JSON = json.dumps({TEST_KID: {"private_pem": TEST_PRIVATE_PEM, "public_pem": TEST_PUBLIC_PEM}})


class IsolatedMongoClient(MongoClient[Doc]):
    """A real MongoDB client whose database names carry a per-test prefix, so tests never see each other's data."""

    def __init__(self, uri: str, prefix: str, **kwargs: Any) -> None:
        """Connect.

        Args:
            uri: Server URI.
            prefix: Prepended to every database name, e.g. "t1a2b3c4d5e_".
            **kwargs: Extra client options (event listeners).
        """
        super().__init__(uri, tz_aware=True, serverSelectionTimeoutMS=REAL_DB_TIMEOUT_MS, **kwargs)
        self.prefix = prefix

    def __getitem__(self, name: str) -> Database[Doc]:
        """Return the prefixed database.

        Args:
            name: Database name the code under test asked for.

        Returns:
            The database named prefix + name.
        """
        return super().__getitem__(self.prefix + name)


def new_prefix() -> str:
    """Make a unique database-name prefix for one test.

    Returns:
        Prefix like "t1a2b3c4d5e_".
    """
    return f"t{uuid.uuid4().hex[:PREFIX_HEX_CHARS]}_"


def drop_prefixed(prefix: str) -> None:
    """Drop every database a test created on the real server.

    Args:
        prefix: The test's database-name prefix.
    """
    with MongoClient[Doc](MONGODB_TEST_URI, serverSelectionTimeoutMS=REAL_DB_TIMEOUT_MS) as plain:
        for name in plain.list_database_names():
            if name.startswith(prefix):
                plain.drop_database(name)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Deselect tests that cannot run on the current database backend.

    Args:
        config: Pytest config.
        items: Collected tests (edited in place).
    """
    unwanted = "mongomock_only" if REAL_DB else "realdb"
    dropped = [item for item in items if item.get_closest_marker(unwanted) is not None]
    if dropped:
        config.hook.pytest_deselected(items=dropped)
        items[:] = [item for item in items if item.get_closest_marker(unwanted) is None]


class FakeVerifier:
    """Phone verifier double: GOOD_CODE is approved for every phone."""

    def __init__(self) -> None:
        """Start with no sends and no failure."""
        self.sent: list[str] = []
        self.checked: list[tuple[str, str]] = []
        self.fail = False

    def send(self, phone: str) -> None:
        """Record a send.

        Args:
            phone: E.164 number.

        Raises:
            VerifyError: When the test switched on failure.
        """
        if self.fail:
            raise VerifyError("verifier down")
        self.sent.append(phone)

    def check(self, phone: str, code: str) -> bool:
        """Approve only GOOD_CODE.

        Args:
            phone: E.164 number.
            code: Code typed.

        Returns:
            True for GOOD_CODE.

        Raises:
            VerifyError: When the test switched on failure.
        """
        if self.fail:
            raise VerifyError("verifier down")
        self.checked.append((phone, code))
        return code == GOOD_CODE


class FakeMailer:
    """Mailer double that records messages."""

    def __init__(self) -> None:
        """Start with an empty outbox."""
        self.outbox: list[tuple[str, str, str]] = []

    def send(self, to: str, subject: str, body: str) -> None:
        """Record a message.

        Args:
            to: Recipient.
            subject: Subject.
            body: Plain-text body.
        """
        self.outbox.append((to, subject, body))


class FakeClock:
    """A clock tests move by hand."""

    def __init__(self, start: datetime) -> None:
        """Start the clock.

        Args:
            start: Initial timezone-aware UTC time.
        """
        self.now = start

    def __call__(self) -> datetime:
        """Return the current fake time.

        Returns:
            The fake now.
        """
        return self.now

    def advance(self, delta: timedelta) -> None:
        """Move the clock forward.

        Args:
            delta: How far to move.
        """
        self.now += delta


def load_module(name: str, path: Path) -> ModuleType:
    """Import a single file as a module under a private name.

    Args:
        name: Module name to register.
        path: File path.

    Returns:
        The imported module.

    Raises:
        ImportError: If the file cannot be loaded.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def plugin_module(name: str) -> ModuleType:
    """Import one hermes-freight module through a synthetic package so the plugin's __init__ (Hermes deps) never runs.

    Args:
        name: Module name inside the plugin, e.g. "store" or "carriers".

    Returns:
        The plugin module.
    """
    if PLUGIN_PACKAGE not in sys.modules:
        package = ModuleType(PLUGIN_PACKAGE)
        package.__path__ = [str(PLUGIN_DIR)]
        sys.modules[PLUGIN_PACKAGE] = package
    return importlib.import_module(f"{PLUGIN_PACKAGE}.{name}")


def make_principal(
    tenant_id: str | None = TENANT_A,
    role: Role = "owner",
    user_id: str = "user-1",
    kind: PrincipalKind = "user",
) -> Principal:
    """Build a principal for tests.

    Args:
        tenant_id: Firm id, or None while provisioning.
        role: Role in the firm.
        user_id: User id.
        kind: Principal kind.

    Returns:
        The principal.
    """
    return Principal(user_id=user_id, tenant_id=tenant_id, role=role, session_id="session-1", kind=kind)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every settings variable from the environment so tests never see real config.

    Args:
        monkeypatch: Pytest monkeypatch.
    """
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


@pytest.fixture
def mongo_client() -> Iterator[MongoClientT]:
    """Return a fresh, empty MongoDB: in memory, or isolated databases on the real server in real-database mode.

    Yields:
        The client.
    """
    if not REAL_DB:
        yield cast(MongoClientT, mongomock.MongoClient(tz_aware=True))
        return
    prefix = new_prefix()
    client = IsolatedMongoClient(MONGODB_TEST_URI, prefix)
    try:
        yield client
    finally:
        client.close()
        drop_prefixed(prefix)


@pytest.fixture
def platform_db(mongo_client: MongoClientT) -> MongoDb:
    """Return the platform database with its indexes.

    Args:
        mongo_client: In-memory client.

    Returns:
        The platform database.
    """
    db = mongo_client["platform"]
    ensure_platform_indexes(db)
    return db


@pytest.fixture
def clock() -> FakeClock:
    """Return a fake clock starting at a fixed time.

    Returns:
        The clock.
    """
    return FakeClock(START)


@pytest.fixture
def settings() -> Settings:
    """Return test settings with JWT keys but no vendor credentials.

    Returns:
        The settings.
    """
    return Settings(env="test", jwt_active_kid=TEST_KID, jwt_keys_json=SecretStr(TEST_KEYS_JSON))


@pytest.fixture
def verifier() -> FakeVerifier:
    """Return the fake phone verifier wired into the app.

    Returns:
        The verifier.
    """
    return FakeVerifier()


@pytest.fixture
def integrations(verifier: FakeVerifier) -> Integrations:
    """Return the integrations wired into the app (fake verifier, no mailer).

    Args:
        verifier: Fake verifier.

    Returns:
        The integrations.
    """
    return Integrations(verifier=verifier, mailer=None)


@pytest.fixture
def app(settings: Settings, mongo_client: MongoClientT, clock: FakeClock, integrations: Integrations) -> FastAPI:
    """Build the application against the in-memory database.

    Args:
        settings: Test settings.
        mongo_client: In-memory client.
        clock: Fake clock.
        integrations: Fake integrations.

    Returns:
        The app.
    """
    return create_app(settings, mongo_client, clock=clock, integrations=integrations)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Run the app's lifespan and yield an HTTP test client.

    Args:
        app: The app.

    Yields:
        The client.
    """
    with TestClient(app) as test_client:
        yield test_client
