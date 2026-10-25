"""Refresh rotation and reuse detection, logout, logout-all, session listing and revocation, switching firms."""

from __future__ import annotations

from datetime import timedelta

from authkit import (
    NATIVE,
    PHONE_DISPATCHER_A,
    PHONE_NEW,
    PHONE_OWNER_A,
    PHONE_OWNER_B,
    add_member,
    bearer,
    one,
    otp_login,
    platform,
    seed_firm,
)
from conftest import GOOD_CODE, TENANT_A, TENANT_B, FakeClock
from fastapi.testclient import TestClient

from manceps_core.mongo import MongoClientT
from manceps_core.tenancy import TenantDb
from manceps_worker.runner import run_once


def _refresh(client: TestClient, token: str) -> dict[str, object]:
    """Exchange a refresh token as a native client and expect success.

    Args:
        client: Test client.
        token: Refresh token.

    Returns:
        The token response body.
    """
    response = client.post("/v1/auth/refresh", json={"refresh_token": token}, headers=NATIVE)
    assert response.status_code == 200, response.text
    return response.json()


def test_refresh_rotation(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    seed_firm(mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    login = otp_login(client, PHONE_OWNER_A)
    clock.advance(timedelta(minutes=20))
    rotated = _refresh(client, str(login["refresh_token"]))
    assert rotated["refresh_token"] != login["refresh_token"]
    assert rotated["tenant_id"] == TENANT_A
    assert client.get("/v1/firm", headers=bearer(str(rotated["access_token"]))).status_code == 200
    old = platform(mongo_client)["sessions"].find_one({"_id": login["session_id"]})
    assert old is not None and old["rotated_to"] == rotated["session_id"]
    assert old["family_id"] == one(platform(mongo_client), "sessions", {"_id": rotated["session_id"]})["family_id"]
    stored = platform(mongo_client)["sessions"].find_one({"_id": rotated["session_id"]})
    assert stored is not None and str(rotated["refresh_token"]) not in str(stored)


def test_refresh_reuse_revokes_family(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    seed_firm(mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    login = otp_login(client, PHONE_OWNER_A)
    rotated = _refresh(client, str(login["refresh_token"]))
    reuse = client.post("/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}, headers=NATIVE)
    assert reuse.status_code == 401
    assert reuse.json()["error"]["code"] == "refresh_reuse"
    after = client.post("/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]}, headers=NATIVE)
    assert after.status_code == 401
    assert client.get("/v1/firm", headers=bearer(str(rotated["access_token"]))).status_code == 401


def test_refresh_failures(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    seed_firm(mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    login = otp_login(client, PHONE_OWNER_A)
    assert client.post("/v1/auth/refresh", headers=NATIVE).status_code == 401
    unknown = client.post("/v1/auth/refresh", json={"refresh_token": "x" * 43}, headers=NATIVE)
    assert unknown.json()["error"]["code"] == "invalid_refresh"
    assert client.post("/v1/auth/refresh", json={"refresh_token": 5}).status_code == 422
    clock.advance(timedelta(days=31))
    expired = client.post("/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}, headers=NATIVE)
    assert expired.status_code == 401


def test_refresh_from_cookie(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    seed_firm(mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    login = client.post("/v1/auth/otp/verify", json={"phone": PHONE_OWNER_A, "code": GOOD_CODE})
    raw = login.headers["set-cookie"].split(";")[0].split("=", 1)[1]
    response = client.post("/v1/auth/refresh", headers={"Cookie": f"mc_refresh={raw}"})
    assert response.status_code == 200
    assert response.json()["refresh_token"] is None
    assert response.headers["set-cookie"].startswith("mc_refresh=")


def test_logout_revokes_session(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    seed_firm(mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    login = otp_login(client, PHONE_OWNER_A)
    other = otp_login(client, PHONE_OWNER_A)
    response = client.post("/v1/auth/logout", headers=bearer(str(login["access_token"])))
    assert response.status_code == 204
    assert "mc_refresh=" in response.headers["set-cookie"]
    assert client.get("/v1/me", headers=bearer(str(login["access_token"]))).status_code == 401
    assert client.post("/v1/auth/refresh", json={"refresh_token": login["refresh_token"]},
                       headers=NATIVE).status_code == 401
    assert client.get("/v1/me", headers=bearer(str(other["access_token"]))).status_code == 200
    assert client.post("/v1/auth/logout").status_code == 401


def test_logout_all_bites_next_request(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    seed_firm(mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    first = otp_login(client, PHONE_OWNER_A)
    second = otp_login(client, PHONE_OWNER_A)
    assert client.post("/v1/auth/logout-all", headers=bearer(str(first["access_token"]))).status_code == 204
    for login in (first, second):
        assert client.get("/v1/firm", headers=bearer(str(login["access_token"]))).status_code == 401
        assert client.post("/v1/auth/refresh", json={"refresh_token": login["refresh_token"]},
                           headers=NATIVE).status_code == 401
    assert one(platform(mongo_client), "users", {"phone": PHONE_OWNER_A})["token_epoch"] == 1
    fresh = otp_login(client, PHONE_OWNER_A)
    assert client.get("/v1/firm", headers=bearer(str(fresh["access_token"]))).status_code == 200
    assert client.post("/v1/auth/logout-all").status_code == 401


def test_sessions_list_and_delete(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    seed_firm(mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    first = otp_login(client, PHONE_OWNER_A)
    second = otp_login(client, PHONE_OWNER_A)
    rotated = _refresh(client, str(second["refresh_token"]))
    listing = client.get("/v1/sessions", headers=bearer(str(first["access_token"])))
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert {item["id"] for item in items} == {first["session_id"], rotated["session_id"]}
    current = [item for item in items if item["current"]]
    assert [item["id"] for item in current] == [first["session_id"]]
    deleted = client.delete(f"/v1/sessions/{rotated['session_id']}", headers=bearer(str(first["access_token"])))
    assert deleted.status_code == 204
    assert client.get("/v1/me", headers=bearer(str(rotated["access_token"]))).status_code == 401
    assert client.delete("/v1/sessions/ses_missing", headers=bearer(str(first["access_token"]))).status_code == 404
    assert client.get("/v1/sessions").status_code == 401
    assert client.delete("/v1/sessions/" + "x" * 200, headers=bearer(str(first["access_token"]))).status_code == 422


def test_sessions_of_other_user_are_404(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    seed_firm(mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    seed_firm(mongo_client, clock, TENANT_B, PHONE_OWNER_B)
    alice = otp_login(client, PHONE_OWNER_A)
    bob = otp_login(client, PHONE_OWNER_B)
    response = client.delete(f"/v1/sessions/{bob['session_id']}", headers=bearer(str(alice["access_token"])))
    assert response.status_code == 404
    listing = client.get("/v1/sessions", headers=bearer(str(alice["access_token"]))).json()["items"]
    assert bob["session_id"] not in {item["id"] for item in listing}
    assert client.get("/v1/me", headers=bearer(str(bob["access_token"]))).status_code == 200


def test_signup_to_active_firm_via_switch(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    login = otp_login(client, PHONE_NEW, firm_name="Lone Star Dispatch", accept_terms=True)
    token = str(login["access_token"])
    assert client.get("/v1/firm/provisioning", headers=bearer(token)).json()["status"] == "pending"
    early = client.post("/v1/auth/switch-firm", json={}, headers=bearer(token))
    assert early.status_code == 409 and early.json()["error"]["code"] == "firm_provisioning"
    platform(mongo_client)["signups"].update_one({"_id": login["signup_token"]},
                                                 {"$set": {"status": "ready", "tenant_id": "lone-star-dispatch"}})
    assert client.get("/v1/firm/provisioning", headers=bearer(token)).json()["status"] == "provisioning"
    assert run_once(platform(mongo_client), TenantDb(mongo_client), clock) == 1
    status = client.get("/v1/firm/provisioning", headers=bearer(token)).json()
    assert status == {"status": "ready", "tenant_id": "lone-star-dispatch", "message": None}
    switched = client.post("/v1/auth/switch-firm", json={}, headers=bearer(token))
    assert switched.status_code == 200
    body = switched.json()
    assert body["tenant_id"] == "lone-star-dispatch" and body["role"] == "owner" and body["state"] == "active"
    firm = client.get("/v1/firm", headers=bearer(body["access_token"]))
    assert firm.status_code == 200 and firm.json()["name"] == "Lone Star Dispatch"
    refreshed = _refresh(client, str(login["refresh_token"]))
    assert refreshed["tenant_id"] == "lone-star-dispatch"


def test_switch_between_firms(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    seed_firm(mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    seed_firm(mongo_client, clock, TENANT_B, PHONE_OWNER_B)
    add_member(mongo_client, clock, TENANT_B, PHONE_DISPATCHER_A, "dispatcher")
    login = otp_login(client, PHONE_DISPATCHER_A)
    token = str(login["access_token"])
    assert login["tenant_id"] == TENANT_B
    denied = client.post("/v1/auth/switch-firm", json={"tenant_id": TENANT_A}, headers=bearer(token))
    assert denied.status_code == 404
    assert client.post("/v1/auth/switch-firm", json={"tenant_id": "Bad Id"}, headers=bearer(token)).status_code == 422
    assert client.post("/v1/auth/switch-firm", json={"tenant_id": TENANT_B}).status_code == 401
    same = client.post("/v1/auth/switch-firm", json={"tenant_id": TENANT_B}, headers=bearer(token))
    assert same.status_code == 200 and same.json()["role"] == "dispatcher"


def test_provisioning_without_signup(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    seed_firm(mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    token = str(otp_login(client, PHONE_OWNER_A)["access_token"])
    platform(mongo_client)["signups"].delete_many({})
    assert client.get("/v1/firm/provisioning", headers=bearer(token)).json()["status"] == "none"
    assert client.get("/v1/firm/provisioning").status_code == 401
