"""Every WP1.3 data route: another firm's ids are 404, viewers cannot write, and anonymous callers get 401."""

from __future__ import annotations

from typing import Any

from conftest import FakeClock
from datakit import CARRIER, Firms, created, seed_firms
from fastapi.testclient import TestClient

from manceps_core.mongo import MongoClientT

Call = tuple[str, str, dict[str, Any] | None]


def _seed(client: TestClient, firms: Firms) -> dict[str, str]:
    """Create one of every entity in firm A.

    Args:
        client: Test client.
        firms: Tokens.

    Returns:
        Entity name to id (brokers by MC, links by link id).
    """
    headers = firms.headers("dispatcher")
    carrier = created(client, headers, "/v1/carriers", CARRIER)["id"]
    return {
        "carrier": carrier,
        "driver": created(client, headers, "/v1/drivers", {"carrier_id": carrier, "name": "D"})["id"],
        "truck": created(client, headers, "/v1/trucks", {"carrier_id": carrier, "unit": "1"})["id"],
        "broker": created(client, headers, "/v1/brokers", {"mc_number": "123456"})["mc_number"],
        "contact": created(client, headers, "/v1/contacts", {"kind": "other", "name": "C"})["id"],
        "facility": created(client, headers, "/v1/facilities", {"name": "F"})["id"],
        "link": created(client, headers, f"/v1/carriers/{carrier}/links", {})["id"],
    }


def _id_routes(ids: dict[str, str]) -> list[Call]:
    """Every data route that names a firm-A resource.

    Args:
        ids: Seeded ids.

    Returns:
        (method, path, body) per route.
    """
    carrier = f"/v1/carriers/{ids['carrier']}"
    broker = f"/v1/brokers/{ids['broker']}"
    calls: list[Call] = [
        ("GET", carrier, None), ("PATCH", carrier, {"name": "x"}), ("DELETE", carrier, None),
        ("POST", f"{carrier}/consent", {"channel": "sms", "method": "verbal"}),
        ("DELETE", f"{carrier}/consent/sms", None), ("POST", f"{carrier}/links", {}),
        ("DELETE", f"{carrier}/links/{ids['link']}", None),
        ("GET", broker, None), ("PATCH", broker, {"company": "x"}), ("POST", f"{broker}/notes", {"text": "x"}),
        ("POST", f"{broker}/check", {}), ("GET", f"{broker}/checks", None),
        ("GET", f"/v1/notes?ref_type=carrier&ref_id={ids['carrier']}", None),
        ("POST", "/v1/notes", {"ref": {"type": "carrier", "id": ids["carrier"]}, "text": "x"}),
        ("POST", "/v1/drivers", {"carrier_id": ids["carrier"], "name": "x"}),
        ("POST", "/v1/trucks", {"carrier_id": ids["carrier"], "unit": "2"}),
    ]
    for kind, collection in (("driver", "drivers"), ("truck", "trucks"), ("contact", "contacts"),
                             ("facility", "facilities")):
        path = f"/v1/{collection}/{ids[kind]}"
        calls += [("GET", path, None), ("PATCH", path, {"name": "x"} if kind != "truck" else {"unit": "x"}),
                  ("DELETE", path, None)]
    return calls


WRITE_ROUTES: tuple[Call, ...] = (
    ("POST", "/v1/carriers", CARRIER), ("POST", "/v1/drivers", {}), ("POST", "/v1/trucks", {}),
    ("POST", "/v1/brokers", {"mc_number": "1"}), ("POST", "/v1/contacts", {}), ("POST", "/v1/facilities", {}),
    ("POST", "/v1/notes", {}),
)
CROSS_REFERENCE_422 = frozenset({("POST", "/v1/drivers"), ("POST", "/v1/trucks")})
READ_ROUTES = ("/v1/carriers", "/v1/drivers", "/v1/trucks", "/v1/brokers", "/v1/contacts", "/v1/facilities",
               "/v1/tags", "/v1/reference/brokers?mc=1")


def test_wrong_tenant_matrix_data_routes(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    ids = _seed(client, firms)
    for method, path, body in _id_routes(ids):
        foreign = client.request(method, path, json=body, headers=firms.headers("owner_b"))
        expected = 422 if (method, path) in CROSS_REFERENCE_422 else 404
        assert foreign.status_code == expected, (method, path, foreign.text)
    for path in READ_ROUTES[:-2]:
        assert client.get(path, headers=firms.headers("owner_b")).json()["items"] == [], path
    assert client.get("/v1/tags", headers=firms.headers("owner_b")).json()["items"] == []
    assert client.get(f"/v1/carriers/{ids['carrier']}", headers=firms.headers("viewer")).status_code == 200


def test_data_routes_roles_and_auth(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    ids = _seed(client, firms)
    writes = [call for call in _id_routes(ids) if call[0] != "GET"] + list(WRITE_ROUTES)
    for method, path, body in writes:
        response = client.request(method, path, json=body, headers=firms.headers("viewer"))
        assert response.status_code == 403, (method, path, response.text)
        assert client.request(method, path, json=body).status_code == 401, (method, path)
    for path in READ_ROUTES:
        assert client.get(path, headers=firms.headers("viewer")).status_code == 200, path
        assert client.get(path).status_code == 401, path
    for method, path, body in _id_routes(ids):
        if method == "GET":
            assert client.request(method, path, json=body).status_code == 401, path
