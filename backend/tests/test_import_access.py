"""Every import and export route: anonymous 401, viewer 403 on writes, another firm's ids 404, bad input 422."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx2
import pytest
from conftest import FakeClock
from datakit import Firms, error_code, seed_firms
from fastapi.testclient import TestClient
from importkit import fixture_bytes, upload, uploaded

from manceps_core.mongo import MongoClientT

Call = tuple[str, str, dict[str, Any] | None]
MISSING_ID = "0123456789abcdef01234567"


@pytest.fixture
def clock() -> FakeClock:
    """A fake clock at the real current time, so the export TTL (applied against the real clock) keeps the rows.

    Returns:
        The clock.
    """
    return FakeClock(datetime.now(UTC).replace(microsecond=0))


def _seed(client: TestClient, firms: Firms) -> dict[str, str]:
    """Create an import and an export in firm A.

    Args:
        client: Test client.
        firms: Tokens.

    Returns:
        {"import": id, "export": id}.
    """
    headers = firms.headers("dispatcher")
    imported = uploaded(client, headers, "carriers", "carriers.csv", fixture_bytes("carriers.csv"))
    exported = client.post("/v1/exports", json={"entity": "carriers", "format": "csv"}, headers=headers)
    assert exported.status_code == 202, exported.text
    return {"import": imported["id"], "export": exported.json()["id"]}


def _id_calls(ids: dict[str, str]) -> list[Call]:
    """Routes naming a firm-A import or export.

    Args:
        ids: Seeded ids.

    Returns:
        (method, path, body).
    """
    base = f"/v1/imports/{ids['import']}"
    return [("GET", base, None), ("PUT", f"{base}/mapping", {"mapping": {"Phone": "phone"}}),
            ("GET", f"{base}/preview", None), ("GET", f"{base}/report", None),
            ("POST", f"{base}/commit", {"duplicate_strategy": "skip"}), ("POST", f"{base}/undo", None),
            ("GET", f"/v1/exports/{ids['export']}", None), ("GET", f"/v1/exports/{ids['export']}/download", None)]


def _send(client: TestClient, call: Call, headers: dict[str, str] | None) -> httpx2.Response:
    """Send one call.

    Args:
        client: Test client.
        call: (method, path, body).
        headers: Auth headers or None.

    Returns:
        The response.
    """
    method, path, body = call
    return client.request(method, path, json=body, headers=headers or {})


def test_wrong_tenant_gets_404_on_every_id_route(client: TestClient, mongo_client: MongoClientT,
                                                 clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    ids = _seed(client, firms)
    for call in _id_calls(ids):
        response = _send(client, call, firms.headers("owner_b"))
        assert response.status_code == 404, (call, response.text)
    for call in _id_calls({"import": MISSING_ID, "export": MISSING_ID}) + _id_calls({"import": "x", "export": "y"}):
        assert _send(client, call, firms.headers("owner")).status_code == 404, call


def test_viewer_cannot_write_and_anonymous_is_401(client: TestClient, mongo_client: MongoClientT,
                                                  clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    ids = _seed(client, firms)
    writes = [call for call in _id_calls(ids) if call[0] != "GET"]
    writes.append(("POST", "/v1/exports", {"entity": "carriers", "format": "csv"}))
    for call in writes:
        assert _send(client, call, firms.headers("viewer")).status_code == 403, call
        assert _send(client, call, None).status_code == 401, call
    viewer_upload = upload(client, firms.headers("viewer"), "carriers", "c.csv", fixture_bytes("carriers.csv"))
    assert viewer_upload.status_code == 403
    assert upload(client, {}, "carriers", "c.csv", fixture_bytes("carriers.csv")).status_code == 401
    for call in [call for call in _id_calls(ids) if call[0] == "GET"] + [("GET", "/v1/imports", None)]:
        assert _send(client, call, None).status_code == 401, call
        assert _send(client, call, firms.headers("viewer")).status_code in (200, 409), call


def test_validation_errors_on_every_body_route(client: TestClient, mongo_client: MongoClientT,
                                               clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    ids = _seed(client, firms)
    owner = firms.headers("owner")
    base = f"/v1/imports/{ids['import']}"
    bad_calls: list[Call] = [
        ("PUT", f"{base}/mapping", {"mapping": {"Phone": 5}}), ("PUT", f"{base}/mapping", {}),
        ("POST", f"{base}/commit", {"duplicate_strategy": "overwrite"}),
        ("POST", "/v1/exports", {"entity": "loads", "format": "csv"}),
        ("POST", "/v1/exports", {"entity": "carriers", "format": "pdf"}),
        ("POST", "/v1/exports", {"entity": "carriers", "format": "csv", "filters": {"state": "TX"}}),
        ("POST", "/v1/exports", {"entity": "carriers", "format": "csv", "tenant_id": "bolt-logistics"}),
    ]
    for call in bad_calls:
        response = _send(client, call, owner)
        assert response.status_code == 422, (call, response.text)
        assert "error" in response.json()
    assert client.get(f"{base}/preview?duplicate_strategy=replace", headers=owner).status_code == 422
    assert client.get(f"{base}/report?format=pdf", headers=owner).status_code == 422
    assert error_code(client.get(f"{base}/report?cursor=not-a-cursor", headers=owner)) == "invalid_cursor"
