"""Carriers: plugin-compatible fields, unique normalized phone, sensitive terms, audited owner edits, soft delete."""

from __future__ import annotations

from typing import Any

from authkit import PHONE_OWNER_A, bearer, firm_db, one, platform
from bson import ObjectId
from conftest import TENANT_A, FakeClock, plugin_module
from datakit import CARRIER, CARRIER_PHONE, CARRIER_PHONE_2, created, error_code, seed_firms
from fastapi.testclient import TestClient

from manceps_core.hashing import sha256_hex
from manceps_core.mongo import MongoClientT
from manceps_core.phones import normalize_phone
from manceps_core.repo import carriers as core_carriers
from manceps_core.repo import consent as core_consent
from manceps_core.repo import fields as core_fields

SENSITIVE_PATCHES: tuple[dict[str, Any], ...] = (
    {"dispatch_fee_pct": 10}, {"rate_floor_per_mile": 2.1}, {"agreement_signed": True},
    {"consent": {"sms": True, "method": "verbal"}},
)


def test_constants_match_plugin() -> None:
    carriers, brokers, policy = plugin_module("carriers"), plugin_module("brokers"), plugin_module("policy")
    assert core_carriers.EQUIPMENT_TYPES == carriers.EQUIPMENT_TYPES
    assert core_carriers.MAX_FEE_PCT == carriers.MAX_FEE_PCT
    assert core_consent.CONSENT_CHANNELS == carriers.CONSENT_CHANNELS
    assert core_fields.TAG_PATTERN.pattern == brokers.TAG_PATTERN.pattern
    assert core_fields.MAX_TAGS == brokers.MAX_TAGS
    assert core_fields.MAX_NOTE_CHARS == brokers.MAX_NOTE_CHARS
    assert core_carriers.SENSITIVE_CARRIER_FIELDS == policy.SENSITIVE_CARRIER_FIELDS
    for raw in ("(214) 555-0199", "+1 214 555 0199", "12145550199"):
        assert normalize_phone(raw) == carriers.normalize_phone(raw)


def test_carrier_crud_and_unique_phone(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    carrier = created(client, firms.headers("dispatcher"), "/v1/carriers", CARRIER)
    assert carrier["phone"] == CARRIER_PHONE and carrier["mc_number"] == "0654321"
    assert carrier["status"] == "onboarding" and carrier["consent"] is None and carrier["tags"] == ["team_driver"]
    assert one(firm_db(mongo_client, TENANT_A), "carriers", {"_id": ObjectId(carrier["id"])})["phone"] == CARRIER_PHONE
    path = f"/v1/carriers/{carrier['id']}"
    assert client.get(path, headers=firms.headers("viewer")).json()["name"] == "Lone Wolf"
    duplicate = client.post("/v1/carriers", json={**CARRIER, "phone": "+1 214 555 0300"},
                            headers=firms.headers("dispatcher"))
    assert duplicate.status_code == 409 and error_code(duplicate) == "duplicate_phone"
    second = created(client, firms.headers("dispatcher"), "/v1/carriers", {"phone": CARRIER_PHONE_2, "name": "B"})
    clash = client.patch(f"/v1/carriers/{second['id']}", json={"phone": CARRIER_PHONE},
                         headers=firms.headers("dispatcher"))
    assert clash.status_code == 409 and error_code(clash) == "duplicate_phone"
    patched = client.patch(path, json={"name": "Lone Wolf II", "status": "active", "home_base": None},
                           headers=firms.headers("dispatcher"))
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "Lone Wolf II" and patched.json()["home_base"] is None
    listed = client.get("/v1/carriers?equipment=reefer", headers=firms.headers("viewer")).json()
    assert [item["id"] for item in listed["items"]] == [carrier["id"]] and listed["next_cursor"] is None
    page = client.get("/v1/carriers?limit=1", headers=firms.headers("viewer")).json()
    rest = client.get(f"/v1/carriers?limit=1&cursor={page['next_cursor']}", headers=firms.headers("viewer")).json()
    assert [page["items"][0]["id"], rest["items"][0]["id"]] == [carrier["id"], second["id"]]
    assert client.get("/v1/carriers?status=active&q=wolf", headers=firms.headers("viewer")).json()["items"][0][
        "id"] == carrier["id"]
    assert client.get("/v1/carriers?tag=team_driver", headers=firms.headers("viewer")).json()["items"][0][
        "id"] == carrier["id"]
    events = [doc["event"] for doc in firm_db(mongo_client, TENANT_A)["audit"].find({"ref.type": "carrier"})]
    assert events.count("carrier.create") == 2 and "carrier.update" in events


def test_carrier_validation_auth_and_roles(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    invalid: tuple[dict[str, Any], ...] = (
        {"name": "No phone"}, {"phone": "123"}, {**CARRIER, "equipment": ["spaceship"]},
        {**CARRIER, "tags": ["Bad Tag"]}, {**CARRIER, "status": "retired"}, {**CARRIER, "tenant_id": "bolt"},
        {**CARRIER, "email": "nope"}, {**CARRIER, "mc_number": "MC-"}, {**CARRIER, "name": "x" * 201},
    )
    for body in invalid:
        response = client.post("/v1/carriers", json=body, headers=firms.headers("owner"))
        assert response.status_code == 422, (body, response.text)
        assert error_code(response) == "validation_error"
    over_fee = client.post("/v1/carriers", json={**CARRIER, "dispatch_fee_pct": 30}, headers=firms.headers("owner"))
    assert over_fee.status_code == 422
    assert client.post("/v1/carriers", json=CARRIER).status_code == 401
    assert client.get("/v1/carriers").status_code == 401
    viewer = client.post("/v1/carriers", json=CARRIER, headers=firms.headers("viewer"))
    assert viewer.status_code == 403 and error_code(viewer) == "forbidden"
    carrier = created(client, firms.headers("owner"), "/v1/carriers", CARRIER)
    path = f"/v1/carriers/{carrier['id']}"
    assert client.patch(path, json={}, headers=firms.headers("owner")).status_code == 422
    assert client.patch(path, json={"phone": None}, headers=firms.headers("owner")).status_code == 422
    assert client.patch(path, json={"name": "x"}, headers=firms.headers("viewer")).status_code == 403
    assert client.get("/v1/carriers/not-an-id", headers=firms.headers("owner")).status_code == 404
    assert client.get(f"/v1/carriers/{ObjectId()}", headers=firms.headers("owner")).status_code == 404
    assert client.get("/v1/carriers?cursor=!!", headers=firms.headers("owner")).status_code == 400


def test_carrier_create_idempotent(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    headers = {**firms.headers("dispatcher"), "Idempotency-Key": "carrier-create-01"}
    first = client.post("/v1/carriers", json=CARRIER, headers=headers)
    replay = client.post("/v1/carriers", json=CARRIER, headers=headers)
    assert first.status_code == replay.status_code == 201
    assert replay.headers["Idempotency-Replayed"] == "true" and replay.json()["id"] == first.json()["id"]
    assert firm_db(mongo_client, TENANT_A)["carriers"].count_documents({}) == 1


def test_plugin_written_carrier_is_readable(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    plugin_id = ObjectId()
    firm_db(mongo_client, TENANT_A)["carriers"].insert_one({
        "_id": plugin_id, "phone": CARRIER_PHONE, "name": "Agent Added", "equipment": ["flatbed"],
        "dispatch_fee_pct": 8.0, "consent": {"sms": True, "voice": False, "whatsapp": False, "method": "signed",
                                             "recorded_at": clock()},
        "created_at": clock(), "updated_at": clock(),
    })
    response = client.get(f"/v1/carriers/{plugin_id}", headers=firms.headers("viewer"))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "onboarding" and body["dispatch_fee_pct"] == 8.0 and body["consent"]["sms"] is True


def test_sensitive_field_requires_approval_for_dispatcher(client: TestClient, mongo_client: MongoClientT,
                                                          clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    carrier = created(client, firms.headers("dispatcher"), "/v1/carriers", CARRIER)
    path = f"/v1/carriers/{carrier['id']}"
    before = one(firm_db(mongo_client, TENANT_A), "carriers", {"_id": ObjectId(carrier["id"])})
    for body in SENSITIVE_PATCHES:
        response = client.patch(path, json={**body, "name": "Changed"}, headers=firms.headers("dispatcher"))
        assert response.status_code == 409, (body, response.text)
        error = response.json()["error"]
        assert error["code"] == "approval_required"
        assert error["details"]["approval_kind"] == "carrier_terms_change"
        assert error["details"]["fields"] == sorted(body)
    assert one(firm_db(mongo_client, TENANT_A), "carriers", {"_id": ObjectId(carrier["id"])}) == before
    on_create = client.post("/v1/carriers", json={"phone": CARRIER_PHONE_2, "dispatch_fee_pct": 10},
                            headers=firms.headers("dispatcher"))
    assert on_create.status_code == 409 and error_code(on_create) == "approval_required"


def test_owner_direct_edit_audited(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    carrier = created(client, firms.headers("owner"), "/v1/carriers", {**CARRIER, "dispatch_fee_pct": 8})
    db = firm_db(mongo_client, TENANT_A)
    before = one(db, "carriers", {"_id": ObjectId(carrier["id"])})
    response = client.patch(f"/v1/carriers/{carrier['id']}", json={"dispatch_fee_pct": 10,
                                                                  "rate_floor_per_mile": 2.25},
                            headers=firms.headers("owner"))
    assert response.status_code == 200, response.text
    assert response.json()["dispatch_fee_pct"] == 10 and response.json()["rate_floor_per_mile"] == 2.25
    after = one(db, "carriers", {"_id": ObjectId(carrier["id"])})
    record = one(db, "audit", {"event": "carrier.update"})
    owner_id = str(one(platform(mongo_client), "users", {"phone": PHONE_OWNER_A})["_id"])
    assert record["before_hash"] == sha256_hex(before) and record["after_hash"] == sha256_hex(after)
    assert record["who"] == {"kind": "user", "id": owner_id} and record["request_id"] and record["session_id"]
    assert record["ref"] == {"type": "carrier", "id": carrier["id"]}
    consent = client.patch(f"/v1/carriers/{carrier['id']}", json={"consent": {"sms": True, "method": "verbal"}},
                           headers=firms.headers("owner"))
    assert consent.status_code == 422 and error_code(consent) == "use_consent_endpoint"


def test_soft_delete_phone_reuse(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    first = created(client, firms.headers("owner"), "/v1/carriers", CARRIER)
    second = created(client, firms.headers("owner"), "/v1/carriers", {"phone": CARRIER_PHONE_2, "name": "Two"})
    assert client.delete(f"/v1/carriers/{first['id']}", headers=firms.headers("dispatcher")).status_code == 403
    for carrier in (first, second):
        assert client.delete(f"/v1/carriers/{carrier['id']}", headers=firms.headers("owner")).status_code == 204
    db = firm_db(mongo_client, TENANT_A)
    stored = one(db, "carriers", {"_id": ObjectId(first["id"])})
    assert stored["phone"] == f"{core_carriers.DELETED_PHONE_PREFIX}{first['id']}"
    assert stored["phone_deleted"] == CARRIER_PHONE and stored["deleted_at"] == clock()
    assert stored["status"] == "offboarded"
    assert client.get(f"/v1/carriers/{first['id']}", headers=firms.headers("owner")).status_code == 404
    assert client.delete(f"/v1/carriers/{first['id']}", headers=firms.headers("owner")).status_code == 404
    assert client.get("/v1/carriers", headers=firms.headers("owner")).json()["items"] == []
    again = created(client, firms.headers("owner"), "/v1/carriers", CARRIER)
    assert again["id"] != first["id"] and again["phone"] == CARRIER_PHONE and again["consent"] is None
    plugin_module("store").ensure_indexes(db)
    assert db["carriers"].count_documents({}) == 3


def test_carrier_with_open_loads_cannot_be_deleted(client: TestClient, mongo_client: MongoClientT,
                                                   clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    carrier = created(client, firms.headers("owner"), "/v1/carriers", CARRIER)
    loads = firm_db(mongo_client, TENANT_A)["loads"]
    loads.insert_one({"ref": "L-2026-00001", "status": "dispatched", "carrier_id": carrier["id"]})
    blocked = client.delete(f"/v1/carriers/{carrier['id']}", headers=firms.headers("owner"))
    assert blocked.status_code == 409 and error_code(blocked) == "carrier_has_open_loads"
    loads.update_many({}, {"$set": {"status": "paid"}})
    assert client.delete(f"/v1/carriers/{carrier['id']}", headers=bearer(firms.owner)).status_code == 204
