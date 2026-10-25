"""Firm, me, integrations and audit routes: roles, validation, auth and tenant isolation."""

from __future__ import annotations

from authkit import (
    PHONE_DISPATCHER_A,
    PHONE_OWNER_A,
    PHONE_OWNER_B,
    PHONE_VIEWER_A,
    bearer,
    firm_db,
    member_token,
    one,
    owner_token,
    platform,
)
from conftest import TENANT_A, TENANT_B, FakeClock
from fastapi.testclient import TestClient

from manceps_core.mongo import MongoClientT

FIRM_PATCH = {"name": "Apex Freight Co", "timezone": "America/New_York"}


def _tokens(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> dict[str, str]:
    """Seed firm A with an owner, dispatcher and viewer, and firm B with an owner.

    Args:
        client: Test client.
        mongo_client: In-memory client.
        clock: Fake clock.

    Returns:
        Role name to access token ("owner_b" for firm B).
    """
    return {
        "owner": owner_token(client, mongo_client, clock, TENANT_A, PHONE_OWNER_A),
        "dispatcher": member_token(client, mongo_client, clock, TENANT_A, PHONE_DISPATCHER_A, "dispatcher"),
        "viewer": member_token(client, mongo_client, clock, TENANT_A, PHONE_VIEWER_A, "viewer"),
        "owner_b": owner_token(client, mongo_client, clock, TENANT_B, PHONE_OWNER_B),
    }


def test_roles_matrix(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    tokens = _tokens(client, mongo_client, clock)
    owner_only = [
        ("PATCH", "/v1/firm", FIRM_PATCH),
        ("POST", "/v1/members/invitations", {"phone": "+12145550177", "role": "viewer"}),
        ("GET", "/v1/members/invitations", None),
        ("DELETE", "/v1/members/invitations/inv_x", None),
        ("PATCH", "/v1/members/usr_x", {"role": "viewer"}),
        ("DELETE", "/v1/members/usr_x", None),
        ("GET", "/v1/audit", None),
    ]
    readable = ["/v1/firm", "/v1/members", "/v1/integrations"]
    for role in ("dispatcher", "viewer"):
        for method, path, body in owner_only:
            response = client.request(method, path, json=body, headers=bearer(tokens[role]))
            assert response.status_code == 403, (role, method, path)
            assert response.json()["error"]["code"] == "forbidden"
        for path in readable:
            assert client.get(path, headers=bearer(tokens[role])).status_code == 200, (role, path)
    assert client.patch("/v1/firm", json=FIRM_PATCH, headers=bearer(tokens["owner"])).status_code == 200


def test_firm_get_and_patch(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    tokens = _tokens(client, mongo_client, clock)
    firm = client.get("/v1/firm", headers=bearer(tokens["owner"])).json()
    assert firm["id"] == TENANT_A and firm["status"] == "active" and firm["plan"] == "trial"
    patched = client.patch("/v1/firm", json=FIRM_PATCH, headers=bearer(tokens["owner"]))
    assert patched.status_code == 200
    assert patched.json()["name"] == "Apex Freight Co" and patched.json()["timezone"] == "America/New_York"
    audit = firm_db(mongo_client, TENANT_A)["audit"].find_one({"event": "firm.update"})
    assert audit is not None and audit["before_hash"] != audit["after_hash"] and audit["request_id"]
    other = client.get("/v1/firm", headers=bearer(tokens["owner_b"])).json()
    assert other["id"] == TENANT_B and other["name"] != "Apex Freight Co"


def test_firm_patch_validation_and_auth(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    tokens = _tokens(client, mongo_client, clock)
    for body in ({"timezone": "Mars/Olympus"}, {"name": "x"}, {"tenant_id": TENANT_B}, {}):
        assert client.patch("/v1/firm", json=body, headers=bearer(tokens["owner"])).status_code == 422, body
    assert client.patch("/v1/firm", json=FIRM_PATCH).status_code == 401
    assert client.get("/v1/firm").status_code == 401
    assert one(platform(mongo_client), "firms", {"_id": TENANT_B})["name"] != "Apex Freight Co"


def test_suspended_firm_rejected(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    tokens = _tokens(client, mongo_client, clock)
    platform(mongo_client)["firms"].update_one({"_id": TENANT_A}, {"$set": {"status": "suspended"}})
    response = client.get("/v1/firm", headers=bearer(tokens["owner"]))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "firm_suspended"
    assert client.get("/v1/firm", headers=bearer(tokens["owner_b"])).status_code == 200


def test_removed_member_loses_access_immediately(client: TestClient, mongo_client: MongoClientT,
                                                 clock: FakeClock) -> None:
    tokens = _tokens(client, mongo_client, clock)
    platform(mongo_client)["memberships"].delete_many({"tenant_id": TENANT_A, "role": "viewer"})
    response = client.get("/v1/firm", headers=bearer(tokens["viewer"]))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_a_member"


def test_me_get_and_patch(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    tokens = _tokens(client, mongo_client, clock)
    me = client.get("/v1/me", headers=bearer(tokens["dispatcher"])).json()
    assert me["user"]["phone"] == PHONE_DISPATCHER_A
    assert me["current"] == {"tenant_id": TENANT_A, "role": "dispatcher"}
    assert [(item["tenant_id"], item["role"]) for item in me["memberships"]] == [(TENANT_A, "dispatcher")]
    assert me["memberships"][0]["firm_name"] == "Apex Freight"
    patched = client.patch("/v1/me", json={"name": "Dana Dispatch", "email": "Dana@Apex.test"},
                           headers=bearer(tokens["dispatcher"]))
    assert patched.status_code == 200
    assert patched.json()["user"]["email"] == "dana@apex.test" and patched.json()["user"]["name"] == "Dana Dispatch"
    taken = client.patch("/v1/me", json={"email": "dana@apex.test"}, headers=bearer(tokens["owner_b"]))
    assert taken.status_code == 409 and taken.json()["error"]["code"] == "email_taken"
    for body in ({"email": "nope"}, {"name": ""}, {"phone": "+12145550000"}):
        assert client.patch("/v1/me", json=body, headers=bearer(tokens["viewer"])).status_code == 422, body
    assert client.patch("/v1/me", json={"name": "X Y"}).status_code == 401
    other = client.get("/v1/me", headers=bearer(tokens["owner_b"])).json()
    assert other["user"]["name"] is None and other["current"]["tenant_id"] == TENANT_B


def test_integrations_status(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    tokens = _tokens(client, mongo_client, clock)
    response = client.get("/v1/integrations", headers=bearer(tokens["viewer"]))
    assert response.status_code == 200
    statuses = {item["name"]: item["status"] for item in response.json()["items"]}
    assert statuses == {"twilio_verify": "ready", "smtp": "not_configured", "fmcsa": "not_configured",
                        "eia": "not_configured", "google_routes": "not_configured", "ors": "not_configured"}
    assert client.get("/v1/integrations").status_code == 401


def test_audit_list_paginates_and_is_tenant_scoped(client: TestClient, mongo_client: MongoClientT,
                                                    clock: FakeClock) -> None:
    tokens = _tokens(client, mongo_client, clock)
    for index in range(3):
        body = {"name": f"Apex Freight {index}", "timezone": "America/Chicago"}
        assert client.patch("/v1/firm", json=body, headers=bearer(tokens["owner"])).status_code == 200
    first = client.get("/v1/audit", params={"limit": 2}, headers=bearer(tokens["owner"])).json()
    assert [item["event"] for item in first["items"]] == ["firm.update", "firm.update"]
    assert first["next_cursor"]
    rest = client.get("/v1/audit", params={"limit": 2, "cursor": first["next_cursor"]},
                      headers=bearer(tokens["owner"])).json()
    events = [item["event"] for item in rest["items"]]
    assert events == ["firm.update", "firm.activated"] and rest["next_cursor"] is None
    other = client.get("/v1/audit", headers=bearer(tokens["owner_b"])).json()
    assert [item["event"] for item in other["items"]] == ["firm.activated"]
    assert client.get("/v1/audit", params={"limit": 0}, headers=bearer(tokens["owner"])).status_code == 422
    bad_cursor = client.get("/v1/audit", params={"cursor": "!!"}, headers=bearer(tokens["owner"]))
    assert bad_cursor.status_code == 400 and bad_cursor.json()["error"]["code"] == "invalid_cursor"
    assert client.get("/v1/audit").status_code == 401
