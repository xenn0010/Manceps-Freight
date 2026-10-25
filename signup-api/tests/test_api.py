"""Signup API: verify the phone, queue one firm per phone, never skip verification."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from conftest import FakeVerifier
from fastapi.testclient import TestClient
from pymongo.database import Database

from signup_api import store

PHONE = "(240) 555-0100"
E164 = "+12405550100"
FORM: dict[str, Any] = {"phone": PHONE, "firm_name": "Apex Freight", "accept_terms": True}


def _verify(client: TestClient, code: str = "123456", **extra: Any) -> Any:
    return client.post("/signup/verify", json={**FORM, "code": code, **extra})


def test_start_sends_code_to_normalized_phone(client: TestClient, verifier: FakeVerifier) -> None:
    response = client.post("/signup/start", json=FORM)
    assert response.status_code == 200 and response.json() == {"sent": True}
    assert verifier.sent == [E164]


@pytest.mark.parametrize("change", [
    {"phone": "555-0100"}, {"phone": "+44 20 7946 0958"}, {"firm_name": " "}, {"firm_name": "x" * 61},
    {"accept_terms": False},
])
def test_start_rejects_bad_input(client: TestClient, verifier: FakeVerifier, change: dict[str, Any]) -> None:
    assert client.post("/signup/start", json={**FORM, **change}).status_code == 422
    assert verifier.sent == []


def test_no_verifier_means_no_signup(make_client: Callable[..., TestClient]) -> None:
    client = make_client(with_verifier=False)
    assert client.post("/signup/start", json=FORM).status_code == 503
    assert _verify(client).status_code == 503


def test_verifier_outage_is_bad_gateway(client: TestClient, verifier: FakeVerifier) -> None:
    verifier.down = True
    assert client.post("/signup/start", json=FORM).status_code == 502
    assert _verify(client).status_code == 502


def test_wrong_code_queues_nothing(client: TestClient, db: Database) -> None:
    response = _verify(client, code="000000")
    assert response.status_code == 400
    assert db[store.SIGNUPS].count_documents({}) == 0


def test_right_code_queues_pending_signup(client: TestClient, db: Database) -> None:
    response = _verify(client)
    assert response.status_code == 202
    token = response.json()["token"]
    doc = db[store.SIGNUPS].find_one({"_id": token})
    assert doc is not None
    assert doc["phone"] == E164 and doc["firm_name"] == "Apex Freight" and doc["status"] == "pending"
    assert doc["attempts"] == 0 and doc["terms_version"] == store.TERMS_VERSION
    assert len(token) >= 32


def test_one_firm_per_phone(client: TestClient, verifier: FakeVerifier) -> None:
    assert _verify(client).status_code == 202
    assert client.post("/signup/start", json=FORM).status_code == 409
    assert _verify(client).status_code == 409
    assert verifier.sent == []


def test_failed_signup_can_retry(client: TestClient, db: Database) -> None:
    token = _verify(client).json()["token"]
    db[store.SIGNUPS].update_one({"_id": token}, {"$set": {"status": "failed", "error": "atlas down"}})
    assert client.post("/signup/start", json=FORM).status_code == 200
    retry = _verify(client)
    assert retry.status_code == 202 and retry.json()["token"] != token
    assert db[store.SIGNUPS].count_documents({}) == 1


def test_start_rate_limited_per_phone(client: TestClient, verifier: FakeVerifier) -> None:
    codes = [client.post("/signup/start", json=FORM).status_code for _ in range(store.START_PER_PHONE + 1)]
    assert codes[:-1] == [200] * store.START_PER_PHONE and codes[-1] == 429
    assert len(verifier.sent) == store.START_PER_PHONE


def test_start_rate_limited_per_ip(client: TestClient) -> None:
    codes = [client.post("/signup/start", json={**FORM, "phone": f"240555{i:04d}"}).status_code
             for i in range(store.START_PER_IP + 1)]
    assert codes[-1] == 429


def test_proxy_header_only_trusted_when_enabled(make_client: Callable[..., TestClient]) -> None:
    spoofing = make_client()
    for i in range(store.START_PER_IP):
        spoofing.post("/signup/start", json={**FORM, "phone": f"240555{i:04d}"},
                      headers={"x-forwarded-for": f"10.0.0.{i}"})
    assert spoofing.post("/signup/start", json={**FORM, "phone": "2405559999"},
                         headers={"x-forwarded-for": "10.9.9.9"}).status_code == 429


def test_verify_rate_limited_per_phone(client: TestClient, verifier: FakeVerifier) -> None:
    for _ in range(store.VERIFY_PER_PHONE):
        assert _verify(client, code="000000").status_code == 400
    assert _verify(client).status_code == 429
    assert len(verifier.checked) == store.VERIFY_PER_PHONE


def test_status_reports_progress_without_phone(client: TestClient, db: Database) -> None:
    token = _verify(client).json()["token"]
    pending = client.get(f"/signup/status/{token}").json()
    assert pending["status"] == "pending" and "phone" not in pending
    db[store.SIGNUPS].update_one({"_id": token}, {"$set": {"status": "ready", "tenant_id": "apex-freight"}})
    assert client.get(f"/signup/status/{token}").json() == {"status": "ready", "tenant_id": "apex-freight"}


def test_failed_status_hides_internal_error(client: TestClient, db: Database) -> None:
    token = _verify(client).json()["token"]
    db[store.SIGNUPS].update_one({"_id": token}, {"$set": {"status": "failed", "error": "mongodb://secret@host"}})
    body = client.get(f"/signup/status/{token}").json()
    assert body["status"] == "failed" and "secret" not in str(body)


def test_unknown_token_is_404(client: TestClient) -> None:
    assert client.get("/signup/status/nope").status_code == 404
