"""Members and invitations: hashed tokens, identity match on accept, last owner protected, tenant isolation."""

from __future__ import annotations

from datetime import timedelta

from authkit import (
    PHONE_DISPATCHER_A,
    PHONE_NEW,
    PHONE_OWNER_A,
    PHONE_OWNER_B,
    add_member,
    bearer,
    firm_db,
    one,
    otp_login,
    owner_token,
    platform,
)
from bson import ObjectId
from conftest import TENANT_A, TENANT_B, FakeClock
from fastapi.testclient import TestClient

from manceps_core.mongo import MongoClientT

IDEMPOTENCY = {"Idempotency-Key": "invite-0000001"}


def _invite(client: TestClient, token: str, **body: object) -> dict[str, object]:
    """Create an invitation and expect 201.

    Args:
        client: Test client.
        token: Owner access token.
        **body: Invitation fields.

    Returns:
        The response body.
    """
    response = client.post("/v1/members/invitations", json=body, headers=bearer(token))
    assert response.status_code == 201, response.text
    return response.json()


def _user_id(mongo_client: MongoClientT, phone: str) -> str:
    """Look up a user id by phone.

    Args:
        mongo_client: In-memory client.
        phone: Phone.

    Returns:
        The user id.
    """
    return str(one(platform(mongo_client), "users", {"phone": phone})["_id"])


def test_invitation_flow(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    owner = owner_token(client, mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    add_member(mongo_client, clock, TENANT_B, PHONE_NEW, "viewer")
    invitation = _invite(client, owner, phone="(214) 555-0199", role="dispatcher")
    assert str(invitation["token"]).startswith("mci_") and invitation["status"] == "pending"
    stored = platform(mongo_client)["invitations"].find_one({"_id": ObjectId(str(invitation["id"]))})
    assert stored is not None and str(invitation["token"]) not in str(stored) and stored["phone"] == PHONE_NEW
    listed = client.get("/v1/members/invitations", headers=bearer(owner)).json()["items"]
    assert [item["id"] for item in listed] == [invitation["id"]] and "token" not in listed[0]
    invitee = otp_login(client, PHONE_NEW)["access_token"]
    accepted = client.post("/v1/invitations/accept", json={"token": invitation["token"]}, headers=bearer(invitee))
    assert accepted.status_code == 200
    assert accepted.json() == {"tenant_id": TENANT_A, "role": "dispatcher"}
    again = client.post("/v1/invitations/accept", json={"token": invitation["token"]}, headers=bearer(invitee))
    assert again.status_code == 404
    switched = client.post("/v1/auth/switch-firm", json={"tenant_id": TENANT_A}, headers=bearer(invitee)).json()
    members = client.get("/v1/members", headers=bearer(switched["access_token"])).json()["items"]
    assert {(item["phone"], item["role"]) for item in members} == {(PHONE_OWNER_A, "owner"), (PHONE_NEW, "dispatcher")}
    events = {doc["event"] for doc in firm_db(mongo_client, TENANT_A)["audit"].find()}
    assert {"invitation.create", "invitation.accept"} <= events


def test_invitation_identity_must_match(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    owner = owner_token(client, mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    add_member(mongo_client, clock, TENANT_B, PHONE_DISPATCHER_A, "viewer")
    invitation = _invite(client, owner, email="Someone@Else.test", role="viewer")
    stranger = otp_login(client, PHONE_DISPATCHER_A)["access_token"]
    response = client.post("/v1/invitations/accept", json={"token": invitation["token"]}, headers=bearer(stranger))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "invitation_mismatch"
    assert client.post("/v1/invitations/accept", json={"token": invitation["token"]}).status_code == 401
    assert client.post("/v1/invitations/accept", json={"token": "x"}, headers=bearer(stranger)).status_code == 422


def test_invitation_expiry_and_existing_member(client: TestClient, mongo_client: MongoClientT,
                                               clock: FakeClock) -> None:
    owner = owner_token(client, mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    own = _invite(client, owner, phone=PHONE_OWNER_A, role="viewer")
    conflict = client.post("/v1/invitations/accept", json={"token": own["token"]}, headers=bearer(owner))
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "already_member"
    add_member(mongo_client, clock, TENANT_B, PHONE_NEW, "viewer")
    later = _invite(client, owner, phone=PHONE_NEW, role="viewer")
    clock.advance(timedelta(days=7, seconds=1))
    invitee = otp_login(client, PHONE_NEW)["access_token"]
    expired = client.post("/v1/invitations/accept", json={"token": later["token"]}, headers=bearer(invitee))
    assert expired.status_code == 404


def test_invitation_validation_idempotency_and_revoke(client: TestClient, mongo_client: MongoClientT,
                                                      clock: FakeClock) -> None:
    owner = owner_token(client, mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    other = owner_token(client, mongo_client, clock, TENANT_B, PHONE_OWNER_B)
    for body in ({"role": "viewer"}, {"phone": "123", "role": "viewer"}, {"phone": PHONE_NEW, "role": "carrier"},
                 {"email": "bad", "role": "viewer"}):
        assert client.post("/v1/members/invitations", json=body, headers=bearer(owner)).status_code == 422, body
    first = client.post("/v1/members/invitations", json={"phone": PHONE_NEW, "role": "viewer"},
                        headers={**bearer(owner), **IDEMPOTENCY})
    replay = client.post("/v1/members/invitations", json={"phone": PHONE_NEW, "role": "viewer"},
                         headers={**bearer(owner), **IDEMPOTENCY})
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["id"] == first.json()["id"] and replay.json()["token"] is None
    assert first.json()["token"] and platform(mongo_client)["invitations"].count_documents({}) == 1
    stored = platform(mongo_client)["idempotency_keys"].find_one({})
    assert stored is not None and first.json()["token"] not in str(stored)
    invitation_id = first.json()["id"]
    assert client.delete(f"/v1/members/invitations/{invitation_id}", headers=bearer(other)).status_code == 404
    assert client.delete(f"/v1/members/invitations/{invitation_id}").status_code == 401
    assert client.delete(f"/v1/members/invitations/{invitation_id}", headers=bearer(owner)).status_code == 204
    assert client.delete(f"/v1/members/invitations/{invitation_id}", headers=bearer(owner)).status_code == 404
    assert client.get("/v1/members/invitations", headers=bearer(owner)).json()["items"] == []
    assert client.get("/v1/members/invitations", headers=bearer(other)).json()["items"] == []
    assert client.post("/v1/members/invitations", json={"phone": PHONE_NEW, "role": "viewer"}).status_code == 401


def test_member_role_change_and_removal(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    owner = owner_token(client, mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    other = owner_token(client, mongo_client, clock, TENANT_B, PHONE_OWNER_B)
    member = add_member(mongo_client, clock, TENANT_A, PHONE_DISPATCHER_A, "dispatcher")
    assert client.patch(f"/v1/members/{member}", json={"role": "viewer"}, headers=bearer(other)).status_code == 404
    assert client.delete(f"/v1/members/{member}", headers=bearer(other)).status_code == 404
    assert client.patch(f"/v1/members/{member}", json={"role": "viewer"}).status_code == 401
    assert client.patch(f"/v1/members/{member}", json={"role": "boss"}, headers=bearer(owner)).status_code == 422
    changed = client.patch(f"/v1/members/{member}", json={"role": "viewer"}, headers=bearer(owner))
    assert changed.status_code == 200 and changed.json()["role"] == "viewer"
    assert client.delete(f"/v1/members/{member}", headers=bearer(owner)).status_code == 204
    assert client.delete(f"/v1/members/{member}", headers=bearer(owner)).status_code == 404
    events = [doc["event"] for doc in firm_db(mongo_client, TENANT_A)["audit"].find()]
    assert "member.update" in events and "member.remove" in events
    assert firm_db(mongo_client, TENANT_B)["audit"].count_documents({"event": "member.update"}) == 0


def test_last_owner_cannot_be_removed(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    owner = owner_token(client, mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    owner_id = _user_id(mongo_client, PHONE_OWNER_A)
    for method, body in (("PATCH", {"role": "dispatcher"}), ("DELETE", None)):
        response = client.request(method, f"/v1/members/{owner_id}", json=body, headers=bearer(owner))
        assert response.status_code == 409, method
        assert response.json()["error"]["code"] == "last_owner"
    second = add_member(mongo_client, clock, TENANT_A, PHONE_DISPATCHER_A, "owner")
    assert client.patch(f"/v1/members/{owner_id}", json={"role": "dispatcher"}, headers=bearer(owner)).status_code \
        == 200
    second_token = otp_login(client, PHONE_DISPATCHER_A)["access_token"]
    assert client.delete(f"/v1/members/{second}", headers=bearer(second_token)).status_code == 409
