"""Approvals: create, decide (hash, expiry, roles), apply exactly once, and each Phase 1 kind."""

from __future__ import annotations

from datetime import timedelta

from authkit import firm_db
from conftest import TENANT_A, FakeClock
from datakit import error_code
from fastapi.testclient import TestClient
from loadkit import book, decide, move, new_load, propose, seed_fleet

from manceps_core.mongo import MongoClientT


def test_accept_rate_books_exactly_once_even_when_retried(client: TestClient, mongo_client: MongoClientT,
                                                          clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    load = new_load(client, fleet)
    move(client, fleet, load["id"], "evaluating")
    approval = propose(client, fleet, "accept_rate", load["id"], {"rate_cents": 70_000})
    assert approval["status"] == "pending" and approval["risk"] == "money"
    assert approval["summary"].startswith("accept rate: $700.00")
    decided = decide(client, fleet, approval)
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "applied"
    assert decided.json()["decided_by"]["kind"] == "user"
    again = decide(client, fleet, approval)
    assert again.status_code == 409 and error_code(again) == "already_decided"
    booked = client.get(f"/v1/loads/{load['id']}", headers=fleet.firms.headers("viewer")).json()
    assert booked["status"] == "booked" and booked["rate_cents"] == 70_000 and booked["booked_at"]
    moves = list(firm_db(mongo_client, TENANT_A)["load_events"].find({"type": "status_changed",
                                                                      "data.to": "booked"}))
    assert len(moves) == 1 and moves[0]["data"]["approval_id"] == approval["id"]


def test_decision_idempotency_key_replays(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    load = new_load(client, fleet)
    move(client, fleet, load["id"], "evaluating")
    approval = propose(client, fleet, "accept_rate", load["id"], {"rate_cents": 70_000})
    headers = {**fleet.firms.headers("owner"), "Idempotency-Key": "decide-0001"}
    body = {"decision": "approve", "payload_hash": approval["payload_hash"]}
    first = client.post(f"/v1/approvals/{approval['id']}/decision", json=body, headers=headers)
    second = client.post(f"/v1/approvals/{approval['id']}/decision", json=body, headers=headers)
    assert first.status_code == second.status_code == 200
    assert second.headers.get("Idempotency-Replayed") == "true"


def test_wrong_hash_expired_and_denied(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    load = new_load(client, fleet)
    move(client, fleet, load["id"], "evaluating")
    approval = propose(client, fleet, "accept_rate", load["id"], {"rate_cents": 70_000})
    wrong = decide(client, fleet, approval, payload_hash="0" * 64)
    assert wrong.status_code == 409 and error_code(wrong) == "payload_changed"
    duplicate = client.post("/v1/approvals", json={"kind": "accept_rate", "subject_ref": {"type": "load", "id":
                            load["id"]}, "payload": {"rate_cents": 1}}, headers=fleet.firms.headers("dispatcher"))
    assert error_code(duplicate) == "approval_pending"
    firm_db(mongo_client, TENANT_A)["approvals"].update_one(
        {"kind": "accept_rate"}, {"$set": {"expires_at": clock.now - timedelta(minutes=1)}})
    listed = client.get("/v1/approvals?status=expired", headers=fleet.firms.headers("viewer")).json()["items"]
    assert [item["id"] for item in listed] == [approval["id"]] and listed[0]["status"] == "expired"
    expired = decide(client, fleet, approval)
    assert expired.status_code == 409 and error_code(expired) == "approval_expired"
    fresh = propose(client, fleet, "accept_rate", load["id"], {"rate_cents": 70_000})
    denied = decide(client, fleet, fresh, decision="deny")
    assert denied.json()["status"] == "denied"
    assert client.get(f"/v1/loads/{load['id']}", headers=fleet.firms.headers("viewer")).json()["status"] == \
        "evaluating"


def test_roles_validation_and_tenancy(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    load = new_load(client, fleet)
    move(client, fleet, load["id"], "evaluating")
    approval = propose(client, fleet, "accept_rate", load["id"], {"rate_cents": 70_000})
    as_dispatcher = decide(client, fleet, approval, role="dispatcher")
    assert as_dispatcher.status_code == 403
    assert as_dispatcher.json()["error"]["details"]["required_role"] == "owner"
    assert decide(client, fleet, approval, role="viewer").status_code == 403
    assert decide(client, fleet, approval, role="owner_b").status_code == 404
    assert client.get(f"/v1/approvals/{approval['id']}", headers=fleet.firms.headers("owner_b")).status_code == 404
    assert client.get(f"/v1/approvals/{approval['id']}").status_code == 401
    headers = fleet.firms.headers("dispatcher")
    for body in ({"kind": "nope", "subject_ref": {"type": "load", "id": load["id"]}, "payload": {}},
                 {"kind": "accept_rate", "subject_ref": {"type": "load", "id": load["id"]}, "payload": {"x": 1}},
                 {"kind": "accept_rate", "subject_ref": {"type": "carrier", "id": fleet.carrier},
                  "payload": {"rate_cents": 1}},
                 {"kind": "accept_rate", "subject_ref": {"type": "load", "id": load["id"]},
                  "payload": {"rate_cents": 0}}):
        assert client.post("/v1/approvals", json=body, headers=headers).status_code == 422, body
    foreign = {"kind": "accept_rate", "subject_ref": {"type": "load", "id": load["id"]}, "payload": {"rate_cents": 5}}
    assert client.post("/v1/approvals", json=foreign, headers=fleet.firms.headers("owner_b")).status_code == 404
    assert client.post("/v1/approvals", json=foreign, headers=fleet.firms.headers("viewer")).status_code == 403
    bad = client.post(f"/v1/approvals/{approval['id']}/decision", json={"decision": "maybe", "payload_hash": "x"},
                      headers=fleet.firms.headers("owner"))
    assert bad.status_code == 422


def test_accept_rate_without_carrier_fails_closed(client: TestClient, mongo_client: MongoClientT,
                                                  clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    load = new_load(client, fleet, carrier_id=None, driver_id=None, truck_id=None)
    move(client, fleet, load["id"], "evaluating")
    approval = propose(client, fleet, "accept_rate", load["id"], {"rate_cents": 70_000})
    failed = decide(client, fleet, approval)
    assert failed.json()["status"] == "apply_failed"
    assert failed.json()["apply_result"]["error"] == "carrier_required"
    unchanged = client.get(f"/v1/loads/{load['id']}", headers=fleet.firms.headers("viewer")).json()
    assert unchanged["status"] == "evaluating" and unchanged["rate_cents"] == 65_000
    client.patch(f"/v1/loads/{load['id']}", json={"carrier_id": fleet.carrier}, headers=fleet.firms.headers("owner"))
    retried = decide(client, fleet, approval)
    assert retried.json()["status"] == "applied", retried.text
    assert client.get(f"/v1/loads/{load['id']}", headers=fleet.firms.headers("viewer")).json()["status"] == "booked"


def test_accept_rate_needs_evaluation_first(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    load = new_load(client, fleet)
    response = client.post("/v1/approvals", json={"kind": "accept_rate", "subject_ref": {"type": "load", "id":
                           load["id"]}, "payload": {"rate_cents": 1}}, headers=fleet.firms.headers("dispatcher"))
    assert response.status_code == 409 and error_code(response) == "illegal_transition"


def test_rate_amendment_after_booking(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    load = new_load(client, fleet)
    book(client, fleet, load)
    amend = propose(client, fleet, "accept_rate", load["id"], {"rate_cents": 72_500})
    assert decide(client, fleet, amend).json()["apply_result"]["amended"] is True
    after = client.get(f"/v1/loads/{load['id']}", headers=fleet.firms.headers("viewer")).json()
    assert after["status"] == "booked" and after["rate_cents"] == 72_500


def test_ratecon_then_dispatch(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    load = new_load(client, fleet)
    book(client, fleet, load)
    mismatch = client.post("/v1/approvals", json={"kind": "approve_ratecon", "subject_ref": {"type": "load", "id":
                           load["id"]}, "payload": {"rate_cents": 1}}, headers=fleet.firms.headers("dispatcher"))
    assert error_code(mismatch) == "rate_mismatch"
    ratecon = propose(client, fleet, "approve_ratecon", load["id"], {"rate_cents": 65_000, "document_ref": "doc-1"})
    assert decide(client, fleet, ratecon, role="dispatcher").status_code == 403
    assert decide(client, fleet, ratecon).json()["status"] == "applied"
    loaded = client.get(f"/v1/loads/{load['id']}", headers=fleet.firms.headers("viewer")).json()
    assert loaded["status"] == "ratecon_received" and loaded["ratecon_approved"] is True
    assert move(client, fleet, load["id"], "dispatched").json()["status"] == "dispatched"


def test_cancel_load_approval(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    load = new_load(client, fleet)
    book(client, fleet, load)
    cancel = propose(client, fleet, "cancel_load", load["id"], {"reason": "broker cancelled"})
    assert cancel["risk"] == "contract"
    assert decide(client, fleet, cancel, role="dispatcher").json()["status"] == "applied"
    loaded = client.get(f"/v1/loads/{load['id']}", headers=fleet.firms.headers("viewer")).json()
    assert loaded["status"] == "cancelled" and loaded["cancelled_reason"] == "broker cancelled"


def test_carrier_terms_change(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    blocked = client.patch(f"/v1/carriers/{fleet.carrier}", json={"dispatch_fee_pct": 8.0},
                           headers=fleet.firms.headers("dispatcher"))
    assert error_code(blocked) == "approval_required"
    terms = propose(client, fleet, "carrier_terms_change", fleet.carrier, {"changes": {"dispatch_fee_pct": 8.0}},
                    subject_type="carrier")
    assert decide(client, fleet, terms, role="dispatcher").status_code == 403
    assert decide(client, fleet, terms).json()["status"] == "applied"
    carrier = client.get(f"/v1/carriers/{fleet.carrier}", headers=fleet.firms.headers("viewer")).json()
    assert carrier["dispatch_fee_pct"] == 8.0
    audit = firm_db(mongo_client, TENANT_A)["audit"].find_one({"event": "carrier.update", "who.kind": "approval"})
    assert audit is not None and audit["who"]["id"] == terms["id"]
    for changes in ({"consent": {"sms": True}}, {"dispatch_fee_pct": 99}, {}, {"agreement_signed": None}):
        response = client.post("/v1/approvals", json={"kind": "carrier_terms_change", "subject_ref": {
            "type": "carrier", "id": fleet.carrier}, "payload": {"changes": changes}},
            headers=fleet.firms.headers("dispatcher"))
        assert response.status_code == 422, changes


def test_list_get_and_stats(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    load = new_load(client, fleet)
    move(client, fleet, load["id"], "evaluating")
    approval = propose(client, fleet, "accept_rate", load["id"], {"rate_cents": 70_000})
    headers = fleet.firms.headers("viewer")
    pending = client.get("/v1/approvals?status=pending", headers=headers).json()
    assert [item["id"] for item in pending["items"]] == [approval["id"]]
    assert client.get(f"/v1/approvals?subject_id={load['id']}&kind=accept_rate", headers=headers).json()["items"]
    assert client.get("/v1/approvals/stats", headers=headers).json() == {"pending": 1, "median_decision_seconds": None}
    clock.advance(timedelta(minutes=10))
    decide(client, fleet, approval)
    stats = client.get("/v1/approvals/stats", headers=headers).json()
    assert stats == {"pending": 0, "median_decision_seconds": 600.0}
    got = client.get(f"/v1/approvals/{approval['id']}", headers=headers).json()
    assert got["payload"] == {"rate_cents": 70_000} and got["applied_at"] is not None
    assert client.get("/v1/approvals?status=bogus", headers=headers).status_code == 422
    assert client.get("/v1/approvals", headers=fleet.firms.headers("owner_b")).json()["items"] == []
    assert client.get("/v1/approvals/stats").status_code == 401
