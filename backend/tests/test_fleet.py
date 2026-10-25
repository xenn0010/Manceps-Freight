"""Drivers and trucks: owned by a carrier of the same firm, unique phone and VIN, soft delete frees both."""

from __future__ import annotations

from authkit import firm_db, one
from bson import ObjectId
from conftest import TENANT_A, FakeClock
from datakit import CARRIER, created, error_code, seed_firms
from fastapi.testclient import TestClient

from manceps_core.mongo import MongoClientT

DRIVER_PHONE = "+12145550500"
VIN = "1FUJGLDR5CLBP8834"


def test_driver_crud(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    carrier = created(client, firms.headers("dispatcher"), "/v1/carriers", CARRIER)
    body = {"carrier_id": carrier["id"], "name": "Sam Driver", "phone": "214-555-0500", "email": "Sam@Example.com",
            "license_state": "tx"}
    driver = created(client, firms.headers("dispatcher"), "/v1/drivers", body)
    assert driver["phone"] == DRIVER_PHONE and driver["email"] == "sam@example.com"
    assert driver["license_state"] == "TX" and driver["status"] == "active" and driver["consent"] is None
    duplicate = client.post("/v1/drivers", json=body, headers=firms.headers("dispatcher"))
    assert duplicate.status_code == 409 and error_code(duplicate) == "duplicate_phone"
    path = f"/v1/drivers/{driver['id']}"
    patched = client.patch(path, json={"status": "inactive", "email": None}, headers=firms.headers("dispatcher"))
    assert patched.status_code == 200 and patched.json()["status"] == "inactive" and patched.json()["email"] is None
    listed = client.get(f"/v1/drivers?carrier_id={carrier['id']}", headers=firms.headers("viewer")).json()
    assert [item["id"] for item in listed["items"]] == [driver["id"]]
    assert client.get("/v1/drivers?status=active", headers=firms.headers("viewer")).json()["items"] == []
    assert client.delete(path, headers=firms.headers("viewer")).status_code == 403
    assert client.delete(path, headers=firms.headers("dispatcher")).status_code == 204
    assert client.get(path, headers=firms.headers("viewer")).status_code == 404
    stored = one(firm_db(mongo_client, TENANT_A), "drivers", {"_id": ObjectId(driver["id"])})
    assert stored["phone_deleted"] == DRIVER_PHONE and stored["phone"] != DRIVER_PHONE
    created(client, firms.headers("dispatcher"), "/v1/drivers", body)
    without_phone = created(client, firms.headers("dispatcher"), "/v1/drivers",
                            {"carrier_id": carrier["id"], "name": "No Phone"})
    assert without_phone["phone"] is None
    created(client, firms.headers("dispatcher"), "/v1/drivers", {"carrier_id": carrier["id"], "name": "Also none"})


def test_driver_validation(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    carrier = created(client, firms.headers("dispatcher"), "/v1/carriers", CARRIER)
    other_firm_carrier = created(client, firms.headers("owner_b"), "/v1/carriers", CARRIER)
    for body in ({"name": "No carrier"}, {"carrier_id": carrier["id"]},
                 {"carrier_id": carrier["id"], "name": "x", "phone": "1"},
                 {"carrier_id": carrier["id"], "name": "x", "license_state": "Texas"},
                 {"carrier_id": "nope", "name": "x"}, {"carrier_id": other_firm_carrier["id"], "name": "x"}):
        response = client.post("/v1/drivers", json=body, headers=firms.headers("dispatcher"))
        assert response.status_code == 422, (body, response.text)
    assert client.post("/v1/drivers", json={"carrier_id": carrier["id"], "name": "x"}).status_code == 401
    driver = created(client, firms.headers("dispatcher"), "/v1/drivers", {"carrier_id": carrier["id"], "name": "x"})
    assert client.patch(f"/v1/drivers/{driver['id']}", json={}, headers=firms.headers("dispatcher")).status_code \
        == 422
    assert client.patch(f"/v1/drivers/{driver['id']}", json={"consent": {}},
                        headers=firms.headers("dispatcher")).status_code == 422


def test_truck_crud_and_unique_vin(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    carrier = created(client, firms.headers("dispatcher"), "/v1/carriers", CARRIER)
    body = {"carrier_id": carrier["id"], "unit": "101", "equipment": "reefer", "vin": VIN.lower(),
            "plate": "ABC1234", "plate_state": "tx", "max_weight_lbs": 45000}
    truck = created(client, firms.headers("dispatcher"), "/v1/trucks", body)
    assert truck["vin"] == VIN and truck["plate_state"] == "TX" and truck["equipment"] == "reefer"
    duplicate = client.post("/v1/trucks", json={**body, "unit": "102"}, headers=firms.headers("dispatcher"))
    assert duplicate.status_code == 409 and error_code(duplicate) == "duplicate_vin"
    for bad in ({**body, "vin": "SHORT"}, {**body, "vin": "1FUJGLDR5CLBP883O"}, {**body, "equipment": "boat"},
                {**body, "max_weight_lbs": 0}, {"unit": "1"}):
        assert client.post("/v1/trucks", json=bad, headers=firms.headers("dispatcher")).status_code == 422, bad
    path = f"/v1/trucks/{truck['id']}"
    patched = client.patch(path, json={"unit": "201", "plate": None}, headers=firms.headers("dispatcher"))
    assert patched.status_code == 200 and patched.json()["unit"] == "201" and patched.json()["plate"] is None
    listed = client.get(f"/v1/trucks?carrier_id={carrier['id']}", headers=firms.headers("viewer")).json()
    assert [item["id"] for item in listed["items"]] == [truck["id"]]
    assert client.post("/v1/trucks", json=body, headers=firms.headers("viewer")).status_code == 403
    assert client.delete(path, headers=firms.headers("dispatcher")).status_code == 204
    stored = one(firm_db(mongo_client, TENANT_A), "trucks", {"_id": ObjectId(truck["id"])})
    assert "vin" not in stored and stored["vin_deleted"] == VIN
    created(client, firms.headers("dispatcher"), "/v1/trucks", body)
    assert client.get(path, headers=firms.headers("dispatcher")).status_code == 404
