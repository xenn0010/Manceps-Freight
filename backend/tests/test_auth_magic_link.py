"""Email magic links: 503 unless enabled with SMTP, always 202 on start, hashed, 15 minutes, single use."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from authkit import NATIVE, PHONE_OWNER_A, bearer, platform, seed_firm
from conftest import TENANT_A, TEST_KEYS_JSON, TEST_KID, FakeClock, FakeMailer, FakeVerifier
from fastapi.testclient import TestClient
from pydantic import SecretStr

from manceps_api.app import create_app
from manceps_api.integrations.configured import Integrations
from manceps_api.settings import Settings
from manceps_core.mongo import MongoClientT

EMAIL = "owner@apex.test"
BASE_URL = "https://app.manceps.test"


@pytest.fixture
def mailer() -> FakeMailer:
    """Return a recording mailer.

    Returns:
        The mailer.
    """
    return FakeMailer()


@pytest.fixture
def email_client(mongo_client: MongoClientT, clock: FakeClock, mailer: FakeMailer) -> Iterator[TestClient]:
    """Build a client with email login enabled and a fake mailer.

    Args:
        mongo_client: In-memory client.
        clock: Fake clock.
        mailer: Fake mailer.

    Yields:
        The test client with its lifespan running.
    """
    settings = Settings(env="test", jwt_active_kid=TEST_KID, jwt_keys_json=SecretStr(TEST_KEYS_JSON),
                        email_login_enabled=True, smtp_host="smtp.test", mail_from="login@manceps.test",
                        public_base_url=BASE_URL)
    app = create_app(settings, mongo_client, clock=clock, integrations=Integrations(verifier=FakeVerifier(),
                                                                                    mailer=mailer))
    with TestClient(app) as client:
        yield client


def _seed_email_owner(mongo_client: MongoClientT, clock: FakeClock) -> None:
    """Seed firm A and give its owner an email address.

    Args:
        mongo_client: In-memory client.
        clock: Fake clock.
    """
    seed_firm(mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    platform(mongo_client)["users"].update_one({"phone": PHONE_OWNER_A}, {"$set": {"email": EMAIL}})


def _token_from(mailer: FakeMailer) -> str:
    """Extract the magic-link token from the last email.

    Args:
        mailer: Fake mailer.

    Returns:
        The token.
    """
    body = mailer.outbox[-1][2]
    url = next(word for word in body.split() if word.startswith(BASE_URL))
    return parse_qs(urlparse(url).query)["token"][0]


def test_magic_link_disabled_503(client: TestClient) -> None:
    start = client.post("/v1/auth/magic-link/start", json={"email": EMAIL})
    verify = client.post("/v1/auth/magic-link/verify", json={"token": "x" * 43})
    for response in (start, verify):
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "email_login_not_configured"


def test_magic_link_flow(email_client: TestClient, mongo_client: MongoClientT, clock: FakeClock,
                         mailer: FakeMailer) -> None:
    _seed_email_owner(mongo_client, clock)
    start = email_client.post("/v1/auth/magic-link/start", json={"email": "Owner@Apex.test"})
    assert start.status_code == 202
    assert mailer.outbox[-1][0] == EMAIL
    token = _token_from(mailer)
    stored = platform(mongo_client)["magic_links"].find_one({})
    assert stored is not None and token not in str(stored)
    verify = email_client.post("/v1/auth/magic-link/verify", json={"token": token}, headers=NATIVE)
    assert verify.status_code == 200
    assert verify.json()["tenant_id"] == TENANT_A
    assert email_client.get("/v1/firm", headers=bearer(verify.json()["access_token"])).status_code == 200
    again = email_client.post("/v1/auth/magic-link/verify", json={"token": token}, headers=NATIVE)
    assert again.status_code == 400
    assert again.json()["error"]["code"] == "invalid_token"


def test_magic_link_expires(email_client: TestClient, mongo_client: MongoClientT, clock: FakeClock,
                            mailer: FakeMailer) -> None:
    _seed_email_owner(mongo_client, clock)
    email_client.post("/v1/auth/magic-link/start", json={"email": EMAIL})
    clock.advance(timedelta(minutes=15))
    response = email_client.post("/v1/auth/magic-link/verify", json={"token": _token_from(mailer)})
    assert response.status_code == 400


def test_magic_link_unknown_email_is_202_without_send(email_client: TestClient, mailer: FakeMailer) -> None:
    response = email_client.post("/v1/auth/magic-link/start", json={"email": "nobody@apex.test"})
    assert response.status_code == 202
    assert response.json() == {"accepted": True}
    assert mailer.outbox == []


def test_magic_link_validation_and_limits(email_client: TestClient, mongo_client: MongoClientT,
                                          clock: FakeClock, mailer: FakeMailer) -> None:
    _seed_email_owner(mongo_client, clock)
    assert email_client.post("/v1/auth/magic-link/start", json={"email": "not-an-email"}).status_code == 422
    assert email_client.post("/v1/auth/magic-link/verify", json={"token": "short"}).status_code == 422
    for _ in range(3):
        assert email_client.post("/v1/auth/magic-link/start", json={"email": EMAIL}).status_code == 202
    assert email_client.post("/v1/auth/magic-link/start", json={"email": EMAIL}).status_code == 429
    assert len(mailer.outbox) == 3


def test_magic_link_for_disabled_user_is_401(email_client: TestClient, mongo_client: MongoClientT,
                                             clock: FakeClock, mailer: FakeMailer) -> None:
    _seed_email_owner(mongo_client, clock)
    email_client.post("/v1/auth/magic-link/start", json={"email": EMAIL})
    platform(mongo_client)["users"].update_one({"email": EMAIL}, {"$set": {"status": "disabled"}})
    response = email_client.post("/v1/auth/magic-link/verify", json={"token": _token_from(mailer)})
    assert response.status_code == 401


def test_f8_magic_link_marks_the_email_verified(email_client: TestClient, mongo_client: MongoClientT,
                                                clock: FakeClock, mailer: FakeMailer) -> None:
    _seed_email_owner(mongo_client, clock)
    users = platform(mongo_client)["users"]
    email_client.post("/v1/auth/magic-link/start", json={"email": EMAIL})
    users.update_one({"phone": PHONE_OWNER_A}, {"$set": {"email": "changed@apex.test"}})
    assert email_client.post("/v1/auth/magic-link/verify", json={"token": _token_from(mailer)}).status_code == 200
    unverified = users.find_one({"phone": PHONE_OWNER_A})
    assert unverified is not None and unverified.get("email_verified_at") is None
    users.update_one({"phone": PHONE_OWNER_A}, {"$set": {"email": EMAIL}})
    email_client.post("/v1/auth/magic-link/start", json={"email": EMAIL})
    assert email_client.post("/v1/auth/magic-link/verify", json={"token": _token_from(mailer)}).status_code == 200
    verified = users.find_one({"phone": PHONE_OWNER_A})
    assert verified is not None and verified["email_verified_at"] == clock()
