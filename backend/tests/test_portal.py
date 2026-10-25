"""Scoped links: exchange for a 60-minute portal token that works only on portal routes, never on firm routes."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

import jwt
from authkit import PHONE_OWNER_A, PHONE_OWNER_B, bearer, firm_db, owner_token, platform
from bson import ObjectId
from conftest import TENANT_A, TENANT_B, FakeClock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from manceps_api.auth.scoped import issue_link
from manceps_core.mongo import MongoClientT
from manceps_core.tenancy import PlatformRepo

FIRM_SCHEME = "FirmBearer"
PORTAL_SCHEME = "PortalBearer"
PUBLIC_OPERATIONS = frozenset({
    "health_get", "readiness_get", "auth_otp_start", "auth_otp_verify", "auth_magic_link_start",
    "auth_magic_link_verify", "auth_refresh", "auth_scoped_exchange", "signup_status_get",
})
PATH_PARAM = re.compile(r"\{[^}]+\}")


def _seed_carrier(mongo_client: MongoClientT, clock: FakeClock, tenant_id: str, name: str) -> str:
    """Insert a carrier the way the plugin stores them (ObjectId _id) and return a scoped link token.

    Args:
        mongo_client: In-memory client.
        clock: Fake clock.
        tenant_id: Firm id.
        name: Carrier name.

    Returns:
        The raw scoped link token.
    """
    carrier_id = ObjectId()
    firm_db(mongo_client, tenant_id)["carriers"].insert_one({"_id": carrier_id, "name": name,
                                                             "phone": "+12145550300"})
    repo = PlatformRepo(platform(mongo_client), tenant_id)
    _doc, raw = issue_link(repo, "carrier", str(carrier_id), {"kind": "user", "id": "usr_test"}, clock())
    return raw


def _exchange(client: TestClient, raw: str) -> str:
    """Exchange a link token for a portal access token.

    Args:
        client: Test client.
        raw: Link token.

    Returns:
        The portal access token.
    """
    response = client.post("/v1/auth/scoped/exchange", json={"token": raw})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["expires_in"] == 60 * 60
    return str(body["access_token"])


def _operations(app: FastAPI) -> list[tuple[str, str, str, list[str]]]:
    """List every operation with its security schemes.

    Args:
        app: The app.

    Returns:
        (method, path, operation id, scheme names) per operation.
    """
    found: list[tuple[str, str, str, list[str]]] = []
    for path, item in app.openapi()["paths"].items():
        for method, operation in item.items():
            security: list[dict[str, Any]] = operation.get("security", [])
            schemes = [name for requirement in security for name in requirement]
            found.append((method.upper(), PATH_PARAM.sub("x", path), operation["operationId"], schemes))
    return found


def test_scoped_exchange_and_aud_isolation(app: FastAPI, client: TestClient, mongo_client: MongoClientT,
                                           clock: FakeClock) -> None:
    firm_token = owner_token(client, mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    portal_token = _exchange(client, _seed_carrier(mongo_client, clock, TENANT_A, "Lone Wolf Trucking"))
    claims = jwt.decode(portal_token, options={"verify_signature": False})
    assert claims["aud"] == "portal" and claims["role"] == "carrier" and claims["tid"] == TENANT_A
    me = client.get("/v1/portal/me", headers=bearer(portal_token))
    assert me.status_code == 200
    assert me.json() == {"carrier_id": claims["sub"], "carrier_name": "Lone Wolf Trucking",
                         "firm_name": "Apex Freight"}
    checked = 0
    for method, path, operation_id, schemes in _operations(app):
        if not schemes:
            assert operation_id in PUBLIC_OPERATIONS, operation_id
            continue
        token = portal_token if FIRM_SCHEME in schemes else firm_token
        response = client.request(method, path, headers=bearer(token), json={})
        assert response.status_code == 401, (method, path, response.text)
        checked += 1
    assert checked > len(PUBLIC_OPERATIONS)


def test_portal_token_expires_and_link_revocation(client: TestClient, mongo_client: MongoClientT,
                                                  clock: FakeClock) -> None:
    owner_token(client, mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    raw = _seed_carrier(mongo_client, clock, TENANT_A, "Lone Wolf Trucking")
    token = _exchange(client, raw)
    clock.advance(timedelta(minutes=60))
    assert client.get("/v1/portal/me", headers=bearer(token)).status_code == 401
    fresh = _exchange(client, raw)
    platform(mongo_client)["scoped_links"].update_many({}, {"$set": {"revoked_at": clock()}})
    assert client.get("/v1/portal/me", headers=bearer(fresh)).status_code == 401
    revoked = client.post("/v1/auth/scoped/exchange", json={"token": raw})
    assert revoked.status_code == 401 and revoked.json()["error"]["code"] == "invalid_link"


def test_scoped_exchange_validation_and_unknown(client: TestClient) -> None:
    assert client.post("/v1/auth/scoped/exchange", json={"token": "nope"}).status_code == 422
    unknown = client.post("/v1/auth/scoped/exchange", json={"token": "mcl_" + "a" * 43})
    assert unknown.status_code == 401
    assert client.get("/v1/portal/me").status_code == 401


def test_portal_is_tenant_isolated(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    owner_token(client, mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    owner_token(client, mongo_client, clock, TENANT_B, PHONE_OWNER_B)
    token_a = _exchange(client, _seed_carrier(mongo_client, clock, TENANT_A, "Alpha Carrier"))
    token_b = _exchange(client, _seed_carrier(mongo_client, clock, TENANT_B, "Bravo Carrier"))
    assert client.get("/v1/portal/me", headers=bearer(token_a)).json()["carrier_name"] == "Alpha Carrier"
    assert client.get("/v1/portal/me", headers=bearer(token_b)).json()["firm_name"] == "Bolt Logistics"
    firm_db(mongo_client, TENANT_A)["carriers"].delete_many({})
    gone = client.get("/v1/portal/me", headers=bearer(token_a))
    assert gone.status_code == 401 and gone.json()["error"]["code"] == "link_revoked"
    assert client.get("/v1/portal/me", headers=bearer(token_b)).status_code == 200
