"""Loads routes: create, read, list, inline edits, transitions, stops and the timeline."""

from __future__ import annotations

from conftest import FakeClock
from datakit import error_code
from fastapi.testclient import TestClient
from loadkit import book, move, new_load, seed_fleet, stops

from manceps_core.mongo import MongoClientT


def test_create_load_starts_offered_with_ref_and_derived_columns(client: TestClient, mongo_client: MongoClientT,
                                                                 clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    load = new_load(client, fleet, notes="Window moved to 15:30", flag=True)
    assert load["status"] == "offered"
    assert load["ref"] == "L-2050-00001"
    assert load["lane"] == "Fresno, CA → Stockton, CA"
    assert load["rate_per_mile_cents"] == 520
    assert load["broker_mc"] == "123456"
    assert load["pickup_at"] is not None and load["delivery_at"] is not None
    assert load["notes"] == "Window moved to 15:30" and load["flag"] is True
    assert new_load(client, fleet)["ref"] == "L-2050-00002"
    got = client.get(f"/v1/loads/{load['id']}", headers=fleet.firms.headers("viewer"))
    assert got.status_code == 200 and got.json()["id"] == load["id"]


def test_create_load_validation(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    headers = fleet.firms.headers("dispatcher")
    for body in ({"rate_cents": -1}, {"notes": "x" * 1001}, {"status": "booked"}, {"loaded_miles": 0},
                 {"stops": [{"type": "pickup", "state": "California"}]}, {"carrier_id": "nope"}):
        response = client.post("/v1/loads", json=body, headers=headers)
        assert response.status_code == 422, (body, response.text)
    window = stops()
    window[0]["window_end"] = "2050-01-01T00:00:00+00:00"
    assert client.post("/v1/loads", json={"stops": window}, headers=headers).status_code == 422


def test_driver_and_truck_must_belong_to_the_loads_carrier(client: TestClient, mongo_client: MongoClientT,
                                                           clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    headers = fleet.firms.headers("owner")
    other = client.post("/v1/carriers", json={"phone": "+12145550399", "status": "active"}, headers=headers).json()
    response = client.post("/v1/loads", json={"carrier_id": other["id"], "truck_id": fleet.truck}, headers=headers)
    assert response.status_code == 422
    load = new_load(client, fleet)
    switched = client.patch(f"/v1/loads/{load['id']}", json={"carrier_id": other["id"]}, headers=headers)
    assert switched.status_code == 422, switched.text


def test_list_filters_and_auth(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    first = new_load(client, fleet)
    second = new_load(client, fleet, flag=True)
    headers = fleet.firms.headers("viewer")
    page = client.get("/v1/loads?limit=1", headers=headers).json()
    assert [item["id"] for item in page["items"]] == [second["id"]]
    rest = client.get(f"/v1/loads?limit=1&cursor={page['next_cursor']}", headers=headers).json()
    assert [item["id"] for item in rest["items"]] == [first["id"]]
    assert [i["id"] for i in client.get("/v1/loads?flag=true", headers=headers).json()["items"]] == [second["id"]]
    assert client.get(f"/v1/loads?truck_id={fleet.truck}&q=L-2050", headers=headers).json()["items"]
    assert client.get("/v1/loads").status_code == 401
    assert client.get("/v1/loads?status=nope", headers=headers).status_code == 422
    assert client.get("/v1/loads", headers=fleet.firms.headers("owner_b")).json()["items"] == []


def test_inline_edit_and_viewer_refused(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    load = new_load(client, fleet)
    path = f"/v1/loads/{load['id']}"
    edited = client.patch(path, json={"notes": "Call at 11", "flag": True, "rate_cents": 70_000},
                          headers=fleet.firms.headers("dispatcher"))
    assert edited.status_code == 200, edited.text
    assert edited.json()["rate_cents"] == 70_000 and edited.json()["flag"] is True
    assert client.patch(path, json={"notes": "x"}, headers=fleet.firms.headers("viewer")).status_code == 403
    assert client.patch(path, json={"notes": "x"}).status_code == 401
    assert client.patch(path, json={"notes": "x"}, headers=fleet.firms.headers("owner_b")).status_code == 404
    assert client.patch(path, json={}, headers=fleet.firms.headers("dispatcher")).status_code == 422


def test_patch_refuses_approval_gated_fields(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    load = new_load(client, fleet)
    path = f"/v1/loads/{load['id']}"
    headers = fleet.firms.headers("owner")
    to_booked = client.patch(path, json={"status": "booked"}, headers=headers)
    assert to_booked.status_code == 409 and error_code(to_booked) == "approval_required"
    assert to_booked.json()["error"]["details"]["approval_kind"] == "accept_rate"
    assert client.patch(path, json={"status": "evaluating"}, headers=headers).json()["status"] == "evaluating"
    to_approved = client.patch(path, json={"status": "approved"}, headers=headers)
    assert error_code(to_approved) == "approval_required"
    approval = client.post("/v1/approvals", json={"kind": "accept_rate", "subject_ref": {"type": "load", "id":
                           load["id"]}, "payload": {"rate_cents": 65_000}}, headers=headers).json()
    client.post(f"/v1/approvals/{approval['id']}/decision",
                json={"decision": "approve", "payload_hash": approval["payload_hash"]}, headers=headers)
    rate = client.patch(path, json={"rate_cents": 80_000}, headers=headers)
    assert rate.status_code == 409 and error_code(rate) == "approval_required"
    assert rate.json()["error"]["details"]["fields"] == ["rate_cents"]
    same_rate = client.patch(path, json={"rate_cents": 65_000, "notes": "ok"}, headers=headers)
    assert same_rate.status_code == 200
    cancel = client.patch(path, json={"status": "cancelled"}, headers=headers)
    assert error_code(cancel) == "approval_required"
    assert cancel.json()["error"]["details"]["approval_kind"] == "cancel_load"


def test_transitions_follow_the_table(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    load = new_load(client, fleet)
    illegal = move(client, fleet, load["id"], "delivered")
    assert illegal.status_code == 409 and error_code(illegal) == "illegal_transition"
    assert error_code(move(client, fleet, load["id"], "approved")) == "approval_required"
    assert move(client, fleet, load["id"], "nope").status_code == 422
    assert move(client, fleet, load["id"], "evaluating", role="viewer").status_code == 403
    assert move(client, fleet, load["id"], "evaluating").json()["status"] == "evaluating"
    for target in ("approved", "booked"):
        gated = move(client, fleet, load["id"], target, role="owner")
        assert gated.status_code == 409 and error_code(gated) == "approval_required"
    declined = client.post(f"/v1/loads/{load['id']}/transition", json={"to": "declined", "reason": "too cheap"},
                           headers=fleet.firms.headers("dispatcher"))
    assert declined.json()["status"] == "declined"
    closed = client.patch(f"/v1/loads/{load['id']}", json={"rate_cents": 1}, headers=fleet.firms.headers("owner"))
    assert error_code(closed) == "load_closed"
    assert client.patch(f"/v1/loads/{load['id']}", json={"notes": "lost"},
                        headers=fleet.firms.headers("owner")).status_code == 200


def test_dispatch_needs_an_approved_rate_con(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    load = new_load(client, fleet)
    book(client, fleet, load)
    assert move(client, fleet, load["id"], "ratecon_received").status_code == 200
    blocked = move(client, fleet, load["id"], "dispatched")
    assert blocked.status_code == 409 and blocked.json()["error"]["details"]["approval_kind"] == "approve_ratecon"


def test_stops_add_change_delete(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    load = new_load(client, fleet)
    headers = fleet.firms.headers("dispatcher")
    base = f"/v1/loads/{load['id']}/stops"
    added = client.post(base, json={"type": "delivery", "city": "Lodi", "state": "CA", "position": 2},
                        headers=headers)
    assert added.status_code == 201, added.text
    cities = [stop["city"] for stop in added.json()["stops"]]
    assert cities == ["Fresno", "Lodi", "Stockton"]
    lodi = added.json()["stops"][1]["id"]
    changed = client.patch(f"{base}/{lodi}", json={"city": "Galt"}, headers=headers)
    assert changed.status_code == 200 and changed.json()["stops"][1]["city"] == "Galt"
    assert client.patch(f"{base}/{lodi}", json={"state": "Cal"}, headers=headers).status_code == 422
    removed = client.delete(f"{base}/{lodi}", headers=headers)
    assert [stop["city"] for stop in removed.json()["stops"]] == ["Fresno", "Stockton"]
    assert client.delete(f"{base}/{lodi}", headers=headers).status_code == 404
    assert client.post(base, json={"type": "x"}, headers=headers).status_code == 422
    assert client.post(base, json={"type": "pickup"}, headers=fleet.firms.headers("viewer")).status_code == 403
    assert client.post(base, json={"type": "pickup"}, headers=fleet.firms.headers("owner_b")).status_code == 404


def test_timeline_records_every_change(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    load = new_load(client, fleet)
    move(client, fleet, load["id"], "evaluating")
    client.patch(f"/v1/loads/{load['id']}", json={"notes": "x"}, headers=fleet.firms.headers("dispatcher"))
    timeline = client.get(f"/v1/loads/{load['id']}/events", headers=fleet.firms.headers("viewer"))
    assert timeline.status_code == 200
    kinds = [entry["type"] for entry in timeline.json()["items"]]
    assert kinds == ["created", "status_changed", "updated"]
    assert timeline.json()["items"][1]["data"] == {"from": "offered", "to": "evaluating"}
    assert client.get(f"/v1/loads/{load['id']}/events", headers=fleet.firms.headers("owner_b")).status_code == 404


def test_kanban_board_groups_by_status(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    first = new_load(client, fleet)
    new_load(client, fleet)
    move(client, fleet, first["id"], "evaluating")
    board = client.get("/v1/loads/board", headers=fleet.firms.headers("viewer"))
    assert board.status_code == 200
    columns = {column["status"]: column for column in board.json()["columns"]}
    assert columns["offered"]["count"] == 1 and columns["evaluating"]["count"] == 1
    assert columns["evaluating"]["items"][0]["id"] == first["id"]
    assert client.get("/v1/loads/board", headers=fleet.firms.headers("owner_b")).json()["columns"][0]["count"] == 0
    assert client.get("/v1/loads/board").status_code == 401
    assert client.get("/v1/loads/board?per_status=0", headers=fleet.firms.headers("viewer")).status_code == 422
