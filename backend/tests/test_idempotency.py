"""Idempotency-Key: replay on same body, 409 on a different body, scoped per tenant, released on failure.

No `from __future__ import annotations` here: the test routes close over local dependencies in Annotated[...] hints.
"""

from datetime import timedelta
from typing import Annotated, Any

import pytest
from conftest import START, TENANT_A, TENANT_B, FakeClock, make_principal
from fastapi import Depends, FastAPI, Header
from fastapi.testclient import TestClient
from pydantic import BaseModel

from manceps_api.errors import ApiError
from manceps_api.idempotency import IDEMPOTENCY_TTL, IdempotencyGuard, idempotency_dependency
from manceps_core.hashing import sha256_hex
from manceps_core.mongo import MongoClientT
from manceps_core.tenancy import PlatformRepo, Principal

KEY = "create-thing-0001"
TENANT_HEADER = "X-Test-Tenant"


class Thing(BaseModel):
    """Test body."""

    name: str


class Calls:
    """Counts how often the handler really ran."""

    def __init__(self) -> None:
        """Start at zero."""
        self.count = 0
        self.fail_next = False


def fake_principal(x_test_tenant: Annotated[str, Header()] = TENANT_A) -> Principal:
    """Stand in for the auth dependency (WP1.2) in these tests.

    Args:
        x_test_tenant: Tenant chosen by the test.

    Returns:
        A principal for that tenant.
    """
    return make_principal(x_test_tenant)


@pytest.fixture
def calls(app: FastAPI) -> Calls:
    """Mount idempotent test routes on the app.

    Args:
        app: App under test.

    Returns:
        The call counter.
    """
    counter = Calls()
    optional = idempotency_dependency(fake_principal)
    required = idempotency_dependency(fake_principal, required=True)

    @app.post("/v1/things", status_code=201, operation_id="things_create")
    def things_create(body: Thing, guard: Annotated[IdempotencyGuard, Depends(optional)]) -> dict[str, object]:
        if counter.fail_next:
            counter.fail_next = False
            raise ApiError(400, "temporary_failure", "try again")
        counter.count += 1
        result: dict[str, object] = {"id": counter.count, "name": body.name}
        guard.save(201, result)
        return result

    @app.post("/v1/payments", status_code=201, operation_id="payments_create")
    def payments_create(body: Thing, guard: Annotated[IdempotencyGuard, Depends(required)]) -> dict[str, object]:
        result: dict[str, object] = {"paid": body.name}
        guard.save(201, result)
        return result

    return counter


def _post(client: TestClient, body: dict[str, str], key: str | None = KEY, tenant: str = TENANT_A,
          path: str = "/v1/things") -> tuple[int, dict[str, Any], dict[str, str]]:
    """POST with optional idempotency key.

    Args:
        client: Test client.
        body: JSON body.
        key: Idempotency key or None.
        tenant: Tenant for the fake principal.
        path: Route.

    Returns:
        Status, JSON body and headers.
    """
    headers = {TENANT_HEADER: tenant}
    if key is not None:
        headers["Idempotency-Key"] = key
    response = client.post(path, json=body, headers=headers)
    return response.status_code, response.json(), dict(response.headers)


def test_idempotency_replay_and_conflict(client: TestClient, calls: Calls) -> None:
    """Same key and body replays the stored response; a different body is 409 idempotency_conflict."""
    status, body, headers = _post(client, {"name": "first"})
    assert (status, body) == (201, {"id": 1, "name": "first"})
    assert "idempotency-replayed" not in headers

    status, body, headers = _post(client, {"name": "first"})
    assert (status, body) == (201, {"id": 1, "name": "first"})
    assert headers["idempotency-replayed"] == "true"
    assert calls.count == 1

    status, body, _ = _post(client, {"name": "second"})
    assert status == 409
    assert body["error"] == {"code": "idempotency_conflict",
                             "message": "this Idempotency-Key was used with a different request body",
                             "details": {}}
    assert calls.count == 1


def test_idempotency_is_scoped_per_tenant(client: TestClient, calls: Calls) -> None:
    """Two firms using the same key never see each other's stored response."""
    assert _post(client, {"name": "a"}, tenant=TENANT_A)[1] == {"id": 1, "name": "a"}
    assert _post(client, {"name": "a"}, tenant=TENANT_B)[1] == {"id": 2, "name": "a"}
    assert calls.count == 2


def test_idempotency_released_when_handler_fails(client: TestClient, calls: Calls) -> None:
    """A failed attempt does not burn the key; the retry runs the handler."""
    calls.fail_next = True
    status, body, _ = _post(client, {"name": "x"})
    assert status == 400 and body["error"]["code"] == "temporary_failure"
    status, body, headers = _post(client, {"name": "x"})
    assert (status, body) == (201, {"id": 1, "name": "x"})
    assert "idempotency-replayed" not in headers


def test_idempotency_without_key_runs_every_time(client: TestClient, calls: Calls) -> None:
    """The header is optional on ordinary creates."""
    _post(client, {"name": "x"}, key=None)
    _post(client, {"name": "x"}, key=None)
    assert calls.count == 2


def test_idempotency_required_and_validated(client: TestClient, calls: Calls) -> None:
    """Payment-like routes demand a key; malformed keys are rejected."""
    status, body, _ = _post(client, {"name": "x"}, key=None, path="/v1/payments")
    assert status == 400 and body["error"]["code"] == "idempotency_key_required"
    status, body, _ = _post(client, {"name": "x"}, key="short")
    assert status == 400 and body["error"]["code"] == "invalid_idempotency_key"
    assert _post(client, {"name": "x"}, key=KEY, path="/v1/payments")[0] == 201
    assert calls.count == 0


def test_idempotency_in_progress_is_409(client: TestClient, calls: Calls, mongo_client: MongoClientT,
                                        clock: FakeClock) -> None:
    """A key whose first request is still running cannot be used concurrently."""
    mongo_client["platform"]["idempotency_keys"].insert_one({
        "tenant_id": TENANT_A, "key": KEY, "route": "POST /v1/things",
        "body_hash": sha256_hex({"name": "x"}), "status": "in_progress", "created_at": clock(),
    })
    status, body, _ = _post(client, {"name": "x"})
    assert status == 409
    assert body["error"]["code"] == "idempotency_in_progress"
    assert calls.count == 0


def test_idempotency_expired_key_runs_again(client: TestClient, calls: Calls, clock: FakeClock) -> None:
    """After the 24 h window a key is fresh again even before the TTL monitor deletes the row."""
    _post(client, {"name": "x"})
    clock.advance(IDEMPOTENCY_TTL + timedelta(seconds=1))
    status, body, headers = _post(client, {"name": "changed"})
    assert (status, body) == (201, {"id": 2, "name": "changed"})
    assert "idempotency-replayed" not in headers


def test_idempotency_concurrent_claim_resolves_to_winner(client: TestClient, calls: Calls, mongo_client: MongoClientT,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    """If another request claims the key between our read and insert, we answer from its record."""
    collection = mongo_client["platform"]["idempotency_keys"]
    original_find_one = PlatformRepo.find_one
    state = {"first": True}

    def racing_find_one(self: PlatformRepo, name: str, query: Any) -> Any:
        if name == "idempotency_keys" and state["first"]:
            state["first"] = False
            collection.insert_one({"tenant_id": TENANT_A, "key": KEY, "route": "POST /v1/things",
                                   "body_hash": sha256_hex({"name": "x"}), "status": "done",
                                   "response": {"status_code": 201, "body": {"id": 99, "name": "x"}},
                                   "created_at": START})
            return None
        return original_find_one(self, name, query)

    monkeypatch.setattr(PlatformRepo, "find_one", racing_find_one)
    status, body, headers = _post(client, {"name": "x"})
    assert (status, body, headers["idempotency-replayed"]) == (201, {"id": 99, "name": "x"}, "true")
    assert calls.count == 0
