"""Every error response uses the envelope {"error": {"code", "message", "details"}}."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from manceps_api.errors import ApiError
from manceps_core.tenancy import TenantError

LEAKY_TEXT = "db password is hunter2"


class Widget(BaseModel):
    """Test body."""

    name: str = Field(min_length=2)
    count: int


def _install_probe_routes(app: FastAPI) -> None:
    """Add routes that raise each kind of error.

    Args:
        app: App under test.
    """

    @app.post("/probe/validate", operation_id="probe_validate")
    def probe_validate(body: Widget) -> dict[str, str]:
        return {"name": body.name}

    @app.get("/probe/api-error", operation_id="probe_api_error")
    def probe_api_error() -> dict[str, str]:
        raise ApiError(409, "already_decided", "this approval was already decided", {"status": "approved"})

    @app.get("/probe/crash", operation_id="probe_crash")
    def probe_crash() -> dict[str, str]:
        raise RuntimeError(LEAKY_TEXT)


def _envelope(body: Any) -> dict[str, Any]:
    """Assert the envelope shape and return the inner error.

    Args:
        body: Parsed response JSON.

    Returns:
        The inner error object.
    """
    assert set(body) == {"error"}
    error: dict[str, Any] = body["error"]
    assert set(error) == {"code", "message", "details"}
    assert isinstance(error["code"], str)
    assert isinstance(error["message"], str)
    return error


def test_error_envelope_shape(app: FastAPI) -> None:
    """404, 405, 422, ApiError and unhandled errors all use the envelope; 500 leaks nothing."""
    _install_probe_routes(app)
    with TestClient(app, raise_server_exceptions=False) as client:
        missing = client.get("/does-not-exist")
        assert missing.status_code == 404
        assert _envelope(missing.json())["code"] == "not_found"

        wrong_method = client.delete("/healthz")
        assert wrong_method.status_code == 405
        assert _envelope(wrong_method.json())["code"] == "method_not_allowed"

        invalid = client.post("/probe/validate", json={"name": "x", "count": "many", "secret": "s"})
        assert invalid.status_code == 422
        error = _envelope(invalid.json())
        assert error["code"] == "validation_error"
        fields = {tuple(item["loc"]) for item in error["details"]["errors"]}
        assert ("body", "name") in fields and ("body", "count") in fields
        assert all("input" not in item for item in error["details"]["errors"])

        conflict = client.get("/probe/api-error")
        assert conflict.status_code == 409
        assert _envelope(conflict.json()) == {
            "code": "already_decided",
            "message": "this approval was already decided",
            "details": {"status": "approved"},
        }

        crash = client.get("/probe/crash")
        assert crash.status_code == 500
        assert _envelope(crash.json())["code"] == "internal_error"
        assert LEAKY_TEXT not in crash.text


def test_malformed_json_is_validation_error(client: TestClient, app: FastAPI) -> None:
    """A body that is not JSON is a 422 envelope, not a crash."""
    _install_probe_routes(app)
    response = client.post("/probe/validate", content=b"{not json", headers={"content-type": "application/json"})
    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "validation_error"


def test_api_error_headers_pass_through(client: TestClient, app: FastAPI) -> None:
    """ApiError headers (e.g. Retry-After) reach the client."""

    @app.get("/probe/limited", operation_id="probe_limited")
    def probe_limited() -> dict[str, str]:
        raise ApiError(429, "rate_limited", "slow down", headers={"Retry-After": "30"})

    response = client.get("/probe/limited")
    assert response.status_code == 429
    assert response.headers["retry-after"] == "30"
    assert _envelope(response.json())["details"] == {}


def test_tenant_error_is_403_without_details(client: TestClient, app: FastAPI) -> None:
    """A tenancy refusal never explains which tenant was involved."""

    @app.get("/probe/tenant", operation_id="probe_tenant")
    def probe_tenant() -> dict[str, str]:
        raise TenantError("query names another tenant bolt-logistics")

    response = client.get("/probe/tenant")
    assert response.status_code == 403
    assert _envelope(response.json()) == {"code": "tenant_required", "message": "no active firm for this request",
                                          "details": {}}
    assert "bolt" not in response.text


def test_routes_must_declare_operation_ids(app: FastAPI) -> None:
    """A route without an explicit operation_id cannot be registered."""
    with pytest.raises(RuntimeError, match="operation_id"):

        @app.get("/probe/unnamed")
        def probe_unnamed() -> dict[str, str]:
            return {}
