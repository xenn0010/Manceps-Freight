"""Fixtures: an in-memory platform database and a scriptable phone verifier."""

from __future__ import annotations

from collections.abc import Callable

import mongomock
import pytest
from fastapi.testclient import TestClient
from pymongo.database import Database

from signup_api import store
from signup_api.app import create_app
from signup_api.verify import VerifyError


class FakeVerifier:
    """Stands in for Twilio Verify: records sends, approves one known code."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.checked: list[tuple[str, str]] = []
        self.good_code = "123456"
        self.down = False

    def send(self, phone: str) -> None:
        if self.down:
            raise VerifyError("twilio unreachable")
        self.sent.append(phone)

    def check(self, phone: str, code: str) -> bool:
        if self.down:
            raise VerifyError("twilio unreachable")
        self.checked.append((phone, code))
        return code == self.good_code


@pytest.fixture
def db() -> Database:
    database = mongomock.MongoClient(tz_aware=True)[store.PLATFORM_DB]
    store.ensure_indexes(database)
    return database


@pytest.fixture
def verifier() -> FakeVerifier:
    return FakeVerifier()


@pytest.fixture
def make_client(db: Database, verifier: FakeVerifier) -> Callable[..., TestClient]:
    def make(with_verifier: bool = True, trust_proxy: bool = False) -> TestClient:
        return TestClient(create_app(db, verifier if with_verifier else None, trust_proxy=trust_proxy))

    return make


@pytest.fixture
def client(make_client: Callable[..., TestClient]) -> TestClient:
    return make_client()
