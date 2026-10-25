"""Liveness, readiness, OpenAPI conventions and app wiring."""

from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock.collection import Collection as MockCollection
from mongomock.database import Database as MockDatabase
from pymongo.errors import ServerSelectionTimeoutError

from manceps_api import serve
from manceps_api.app import create_app, create_app_from_env
from manceps_api.settings import Settings, load_settings
from manceps_core.mongo import MongoClientT

OPERATION_ID = re.compile(r"^[a-z]+(_[a-z]+)+$")
LOCAL_FRONTEND = "http://localhost:3000"


def _fail(*_args: Any, **_kwargs: Any) -> Any:
    """Simulate an unreachable database.

    Args:
        *_args: Ignored.
        **_kwargs: Ignored.

    Raises:
        ServerSelectionTimeoutError: Always.
    """
    raise ServerSelectionTimeoutError("no servers")


def test_healthz(client: TestClient) -> None:
    """Liveness never touches the database."""
    response = client.get("/healthz")
    assert (response.status_code, response.json()) == (200, {"status": "ok"})


def test_readyz_ok_and_creates_platform_indexes(client: TestClient, mongo_client: MongoClientT) -> None:
    """Readiness pings the database; startup created the platform indexes."""
    response = client.get("/readyz")
    assert (response.status_code, response.json()) == (200, {"status": "ok"})
    assert "tenant_id_1_user_id_1_key_1_route_1" in mongo_client["platform"]["idempotency_keys"].index_information()


@pytest.mark.mongomock_only
def test_readyz_503_when_database_down(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """A database outage is 503 database_unavailable in the envelope."""
    monkeypatch.setattr(MockDatabase, "command", _fail)
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"


@pytest.mark.mongomock_only
def test_startup_survives_database_down_then_recovers(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """If indexes cannot be created at startup the app is not ready; readiness retries them later."""
    monkeypatch.setattr(MockCollection, "create_index", _fail)
    with TestClient(app) as client:
        assert client.get("/readyz").status_code == 503
        monkeypatch.undo()
        assert client.get("/readyz").status_code == 200


def test_operation_ids_are_stable_snake_case(app: FastAPI) -> None:
    """Every operation has a unique <resource>_<verb> id and 4xx responses document the envelope."""
    schema = app.openapi()
    ids = [op["operationId"] for path in schema["paths"].values() for op in path.values()]
    assert ids and len(ids) == len(set(ids))
    assert all(OPERATION_ID.match(op_id) for op_id in ids), ids
    assert schema["paths"]["/readyz"]["get"]["responses"]["503"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorEnvelope"
    }
    assert schema["info"]["title"] == "Manceps API"


def test_openapi_served_under_v1(client: TestClient) -> None:
    """The schema is public at /v1/openapi.json."""
    assert client.get("/v1/openapi.json").json()["openapi"].startswith("3.")


def test_cors_allows_configured_origin(mongo_client: MongoClientT) -> None:
    """Configured origins get CORS headers; others do not."""
    app = create_app(Settings(cors_origins=["https://app.manceps.test"]), mongo_client)
    with TestClient(app) as client:
        allowed = client.get("/healthz", headers={"Origin": "https://app.manceps.test"})
        denied = client.get("/healthz", headers={"Origin": "https://evil.test"})
    assert allowed.headers["access-control-allow-origin"] == "https://app.manceps.test"
    assert "access-control-allow-origin" not in denied.headers


def test_cors_preflight_for_local_frontend(monkeypatch: pytest.MonkeyPatch, mongo_client: MongoClientT) -> None:
    """CORS_ORIGINS=http://localhost:3000 answers credentialed preflights for the headers the web client sends."""
    monkeypatch.setenv("CORS_ORIGINS", LOCAL_FRONTEND)
    app = create_app(load_settings(), mongo_client)
    request_headers = "authorization,content-type,idempotency-key"
    with TestClient(app) as client:
        preflight = client.options("/v1/auth/otp/start", headers={
            "Origin": LOCAL_FRONTEND, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": request_headers,
        })
        foreign = client.options("/v1/auth/otp/start", headers={
            "Origin": "http://localhost:3001", "Access-Control-Request-Method": "POST",
        })
        simple = client.get("/healthz", headers={"Origin": LOCAL_FRONTEND})
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == LOCAL_FRONTEND
    assert preflight.headers["access-control-allow-credentials"] == "true"
    assert "POST" in preflight.headers["access-control-allow-methods"]
    allowed = {name.strip().lower() for name in preflight.headers["access-control-allow-headers"].split(",")}
    assert set(request_headers.split(",")) <= allowed
    assert foreign.status_code == 400
    assert "access-control-allow-origin" not in foreign.headers
    assert simple.headers["access-control-allow-origin"] == LOCAL_FRONTEND
    assert simple.headers["access-control-allow-credentials"] == "true"
    assert "x-request-id" in simple.headers["access-control-expose-headers"].lower()


def test_create_app_from_env_requires_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without MONGODB_URI the service refuses to build (fail closed)."""
    with pytest.raises(RuntimeError, match="MONGODB_URI"):
        create_app_from_env()
    monkeypatch.setenv("MONGODB_URI", "mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=1")
    app = create_app_from_env()
    try:
        assert app.title == "Manceps API"
        assert app.state.context.settings.mongodb_uri is not None
    finally:
        app.state.context.client.close()


def test_serve_disables_raw_access_log(monkeypatch: pytest.MonkeyPatch) -> None:
    """The server runs without uvicorn's access log, which would print raw query strings."""
    seen: dict[str, Any] = {}

    def fake_run(target: str, **kwargs: Any) -> None:
        seen["target"] = target
        seen.update(kwargs)

    monkeypatch.setattr(serve.uvicorn, "run", fake_run)
    monkeypatch.setenv("API_PORT", "8123")
    serve.main()
    assert seen["target"] == "manceps_api.app:create_app_from_env"
    assert seen["factory"] is True
    assert seen["access_log"] is False
    assert seen["port"] == 8123
