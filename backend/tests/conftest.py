"""Shared fixtures: in-memory MongoDB, a controllable clock, settings, and the app under test."""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import cast

import mongomock
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from manceps_api.app import create_app
from manceps_api.integrations.configured import Integrations
from manceps_api.integrations.twilio_verify import VerifyError
from manceps_api.settings import Settings
from manceps_core.indexes import ensure_platform_indexes
from manceps_core.mongo import MongoClientT, MongoDb
from manceps_core.tenancy import Principal, PrincipalKind, Role

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
PLUGIN_DIR = REPO_ROOT / "hermes-freight"
SIGNUP_API_DIR = REPO_ROOT / "signup-api"
START = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
TENANT_A = "apex-freight"
TENANT_B = "bolt-logistics"
TEST_KID = "k-test-1"
GOOD_CODE = "123456"


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
def mongo_client() -> MongoClientT:
    """Return a fresh in-memory MongoDB client.

    Returns:
        The mongomock client.
    """
    return cast(MongoClientT, mongomock.MongoClient(tz_aware=True))


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
