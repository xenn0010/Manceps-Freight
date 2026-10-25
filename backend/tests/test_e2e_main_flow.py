"""End to end through the HTTP API: sign up, activate, build a fleet, take a load from offer to booked through the
owner's approval, and see it on the board, the dashboard, the timeline and the event feed."""

from __future__ import annotations

from authkit import PHONE_NEW, bearer, otp_login, platform
from conftest import TENANT_A, FakeClock
from datakit import created
from fastapi.testclient import TestClient
from loadkit import stops

from manceps_core.mongo import MongoClientT
from manceps_core.tenancy import TenantDb
from manceps_worker.firm_activate import firm_activate


def _signup_and_activate(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> dict[str, str]:
    signed = otp_login(client, PHONE_NEW, firm_name="Apex Freight", accept_terms=True)
    assert signed["state"] == "provisioning"
    db = platform(mongo_client)
    db["signups"].update_one({"phone": PHONE_NEW}, {"$set": {"status": "ready", "tenant_id": TENANT_A}})
    signup = db["signups"].find_one({"phone": PHONE_NEW})
    assert signup is not None and firm_activate(db, TenantDb(mongo_client), signup, clock) is True
    switched = client.post("/v1/auth/switch-firm", json={}, headers=bearer(signed["access_token"]))
    assert switched.status_code == 200, switched.text
    return bearer(switched.json()["access_token"])


def test_e2e_main_flow(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    owner = _signup_and_activate(client, mongo_client, clock)
    assert client.get("/v1/firm", headers=owner).json()["timezone"] == "America/Chicago"
    carrier = created(client, owner, "/v1/carriers", {"phone": "(415) 555-0142", "name": "Ava Reed", "status":
                      "active", "dispatch_fee_pct": 8.0, "rate_floor_per_mile": 2.0, "equipment": ["dry_van"]})
    driver = created(client, owner, "/v1/drivers", {"carrier_id": carrier["id"], "name": "Ava Reed"})
    truck = created(client, owner, "/v1/trucks", {"carrier_id": carrier["id"], "unit": "101", "driver_id":
                    driver["id"], "equipment": "dry_van"})
    load = created(client, owner, "/v1/loads", {
        "carrier_id": carrier["id"], "truck_id": truck["id"], "driver_id": driver["id"], "broker_name": "Granite Lane",
        "broker_ref": "GL-55120", "stops": stops(("Commerce", "CA"), ("San Francisco", "CA")), "loaded_miles": 382,
        "rate_cents": 205_000, "equipment": "dry_van", "notes": "Negotiated up from $2,050"})
    evaluated = client.post(f"/v1/loads/{load['id']}/evaluate", json={}, headers=owner).json()
    assert evaluated["status"] == "evaluating" and evaluated["evaluation"]["verdict"] == "unknown"
    approval = created(client, owner, "/v1/approvals", {"kind": "accept_rate", "subject_ref": {
        "type": "load", "id": load["id"]}, "payload": {"rate_cents": 224_000}})
    card = client.get("/v1/approvals?status=pending", headers=owner).json()["items"]
    assert [item["id"] for item in card] == [approval["id"]] and card[0]["always_human"] is True
    assert client.get("/v1/board", headers=owner).json()["items"][0]["status"] == "needs_approval"
    decided = client.post(f"/v1/approvals/{approval['id']}/decision",
                          json={"decision": "approve", "payload_hash": approval["payload_hash"]}, headers=owner)
    assert decided.json()["status"] == "applied", decided.text
    booked = client.get(f"/v1/loads/{load['id']}", headers=owner).json()
    assert booked["status"] == "booked" and booked["rate_cents"] == 224_000 and booked["rate_per_mile_cents"] == 586
    row = client.get("/v1/board", headers=owner).json()["items"][0]
    assert row["status"] == "booked" and row["tone"] == "green" and row["load"]["ref"] == booked["ref"]
    summary = client.get("/v1/dashboard/summary", headers=owner).json()
    assert summary["this_week"]["revenue_cents"] == 224_000 and summary["this_week"]["loads_booked"] == 1
    timeline = [entry["type"] for entry in client.get(f"/v1/loads/{load['id']}/events", headers=owner).json()["items"]]
    assert timeline == ["created", "status_changed", "evaluated", "rate_accepted", "status_changed",
                        "status_changed"]
    feed = [item["type"] for item in client.get("/v1/events?after=0&limit=200", headers=owner).json()["items"]]
    for expected in ("load.created", "load.status_changed", "approval.created", "approval.decided",
                     "approval.applied"):
        assert expected in feed, expected
