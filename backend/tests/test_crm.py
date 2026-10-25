"""Contacts, facilities, notes on any entity, and the firm's tag vocabulary."""

from __future__ import annotations

from authkit import firm_db, one
from bson import ObjectId
from conftest import TENANT_A, FakeClock
from datakit import CARRIER, created, error_code, seed_firms
from fastapi.testclient import TestClient

from manceps_core.mongo import MongoClientT

CONTACT = {"kind": "broker_contact", "name": "Dana Rep", "company": "Acme Logistics", "title": "Carrier sales",
           "phones": ["(214) 555-0700", "214.555.0701"], "emails": ["Dana@Acme.com"], "tags": ["fast_pay"]}
FACILITY = {"name": "Acme DC 4", "address": "100 Dock Rd", "city": "Dallas", "state": "tx", "zip": "75201",
            "location": {"lat": 32.78, "lng": -96.8}, "hours": "Mon-Fri 6-14", "detention_notes": "2h free"}


def test_contacts_tags_notes(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    contact = created(client, firms.headers("dispatcher"), "/v1/contacts", CONTACT)
    assert contact["phones"] == ["+12145550700", "+12145550701"] and contact["emails"] == ["dana@acme.com"]
    assert contact["source"] == "manual" and contact["consent"] is None
    second = created(client, firms.headers("dispatcher"), "/v1/contacts",
                     {"kind": "shipper", "name": "Lee Ship", "tags": ["fast_pay", "dock_slow"]})
    viewer = firms.headers("viewer")
    assert [c["id"] for c in client.get("/v1/contacts?kind=shipper", headers=viewer).json()["items"]] == [
        second["id"]]
    assert [c["id"] for c in client.get("/v1/contacts?q=acme", headers=viewer).json()["items"]] == [contact["id"]]
    assert [c["id"] for c in client.get("/v1/contacts?phone=2145550701", headers=viewer).json()["items"]] == [
        contact["id"]]
    assert len(client.get("/v1/contacts?tag=fast_pay", headers=viewer).json()["items"]) == 2
    patched = client.patch(f"/v1/contacts/{contact['id']}", json={"tags": ["fast_pay", "vip"], "title": None},
                           headers=firms.headers("dispatcher"))
    assert patched.status_code == 200 and patched.json()["title"] is None
    carrier = created(client, firms.headers("dispatcher"), "/v1/carriers", CARRIER)
    created(client, firms.headers("dispatcher"), "/v1/brokers", {"mc_number": "123456", "tags": ["fast_pay"]})
    note = created(client, firms.headers("dispatcher"), "/v1/notes",
                   {"ref": {"type": "carrier", "id": carrier["id"]}, "text": "prefers night loads", "pinned": True})
    assert note["author"]["kind"] == "user" and note["pinned"] is True
    created(client, firms.headers("owner"), "/v1/notes", {"ref": {"type": "contact", "id": contact["id"]},
                                                           "text": "call before 9"})
    notes = client.get(f"/v1/notes?ref_type=carrier&ref_id={carrier['id']}", headers=viewer).json()["items"]
    assert [n["text"] for n in notes] == ["prefers night loads"]
    tags = {item["tag"]: item for item in client.get("/v1/tags", headers=viewer).json()["items"]}
    assert tags["fast_pay"]["count"] == 3
    assert tags["fast_pay"]["by_entity"] == {"carriers": 0, "brokers": 1, "contacts": 2}
    assert tags["team_driver"]["by_entity"]["carriers"] == 1 and "vip" in tags
    assert client.delete(f"/v1/contacts/{second['id']}", headers=firms.headers("dispatcher")).status_code == 204
    assert client.get(f"/v1/contacts/{second['id']}", headers=viewer).status_code == 404
    after = {item["tag"]: item["count"] for item in client.get("/v1/tags", headers=viewer).json()["items"]}
    assert after["fast_pay"] == 2 and "dock_slow" not in after
    events = {doc["event"] for doc in firm_db(mongo_client, TENANT_A)["audit"].find()}
    assert {"contact.create", "contact.update", "contact.delete", "note.create"} <= events


def test_contact_and_note_validation(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    for body in ({"kind": "alien", "name": "x"}, {"kind": "other"}, {**CONTACT, "phones": ["12"]},
                 {**CONTACT, "emails": ["no-at"]}, {**CONTACT, "phones": ["2145550700"] * 11},
                 {**CONTACT, "consent": {"sms": True}}):
        response = client.post("/v1/contacts", json=body, headers=firms.headers("dispatcher"))
        assert response.status_code == 422, body
    assert client.post("/v1/contacts", json=CONTACT, headers=firms.headers("viewer")).status_code == 403
    assert client.post("/v1/contacts", json=CONTACT).status_code == 401
    missing = {"ref": {"type": "carrier", "id": str(ObjectId())}, "text": "hello"}
    response = client.post("/v1/notes", json=missing, headers=firms.headers("dispatcher"))
    assert response.status_code == 404 and error_code(response) == "not_found"
    for body in ({"ref": {"type": "broker", "id": "1"}, "text": "x"}, {"ref": {"type": "carrier", "id": "x"}},
                 {"ref": {"type": "carrier", "id": str(ObjectId())}, "text": "   "}):
        assert client.post("/v1/notes", json=body, headers=firms.headers("dispatcher")).status_code == 422, body
    assert client.get("/v1/notes?ref_type=carrier", headers=firms.headers("viewer")).status_code == 422
    assert client.get(f"/v1/notes?ref_type=carrier&ref_id={ObjectId()}",
                      headers=firms.headers("viewer")).status_code == 404
    assert client.get("/v1/tags").status_code == 401


def test_facility_crud(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    contact = created(client, firms.headers("dispatcher"), "/v1/contacts", CONTACT)
    facility = created(client, firms.headers("dispatcher"), "/v1/facilities",
                       {**FACILITY, "contact_ids": [contact["id"]]})
    assert facility["state"] == "TX" and facility["location"] == {"lat": 32.78, "lng": -96.8}
    stored = one(firm_db(mongo_client, TENANT_A), "facilities", {"_id": ObjectId(facility["id"])})
    assert stored["geo"] == {"type": "Point", "coordinates": [-96.8, 32.78]}
    path = f"/v1/facilities/{facility['id']}"
    patched = client.patch(path, json={"location": None, "hours": "24/7"}, headers=firms.headers("dispatcher"))
    assert patched.status_code == 200 and patched.json()["location"] is None and patched.json()["hours"] == "24/7"
    viewer = firms.headers("viewer")
    assert [f["id"] for f in client.get("/v1/facilities?state=TX&city=dallas", headers=viewer).json()["items"]] == [
        facility["id"]]
    assert [f["id"] for f in client.get("/v1/facilities?q=dc%204", headers=viewer).json()["items"]] == [
        facility["id"]]
    for body in ({**FACILITY, "state": "Texas"}, {**FACILITY, "zip": "7520"},
                 {**FACILITY, "location": {"lat": 95, "lng": 0}}, {**FACILITY, "contact_ids": [str(ObjectId())]},
                 {**FACILITY, "contact_ids": ["bad"]}, {"city": "Dallas"}):
        response = client.post("/v1/facilities", json=body, headers=firms.headers("dispatcher"))
        assert response.status_code == 422, (body, response.text)
    assert client.delete(path, headers=viewer).status_code == 403
    assert client.delete(path, headers=firms.headers("dispatcher")).status_code == 204
    assert client.get(path, headers=viewer).status_code == 404
    assert client.get("/v1/facilities", headers=viewer).json()["items"] == []
