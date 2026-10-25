"""Loads import: the dispatch sheet's columns, times in the firm's timezone, references by unit and phone, matching
by ref or broker ref, approval-gated updates refused, never a booked load from a file, and undo."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from conftest import FakeClock
from fastapi.testclient import TestClient
from importkit import committed, csv_bytes, fixture_bytes, uploaded
from loadkit import Fleet, book, seed_fleet

from manceps_core.mongo import MongoClientT

HEADER = ("Load", "Truck", "Lane", "Pickup", "Delivery", "Miles", "Rate", "Broker", "Broker MC", "Broker Ref",
          "Arjun's notes")
ROWS: list[list[Any]] = [
    ["", "102", "Fresno, CA → Stockton, CA", "2050-11-01 12:30", "2050-11-01 15:30", "125", "$650", "Valley Logistics",
     "MC-123456", "VL-30981", "Window moved to 15:30"],
    ["", "102", "Stockton, CA -> Sacramento, CA", "11/02/2050 6:00 AM", "", "48", "380", "Valley Logistics",
     "123456", "VL-30422", ""],
    ["", "999", "Oakland, CA → Reno, NV", "", "", "218", "1640", "Sierra", "", "", "unknown truck"],
    ["", "102", "Oakland Reno", "", "", "10", "10", "Sierra", "", "", "no arrow"],
    ["", "102", "Fresno, CA → LA, CA", "", "", "220", "-5", "Westline", "", "", "negative rate"],
]


def _loads(client: TestClient, fleet: Fleet) -> list[dict[str, Any]]:
    return client.get("/v1/loads?limit=200", headers=fleet.firms.headers("viewer")).json()["items"]


def test_loads_sheet_import(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    headers = fleet.firms.headers("dispatcher")
    content = csv_bytes(HEADER, ROWS)
    doc = uploaded(client, headers, "loads", "loads.csv", content)
    assert doc["status"] == "mapped", doc
    mapping = doc["mapping"]
    assert mapping["Truck"] == "truck_unit" and mapping["Rate"] == "rate_cents" and mapping["Lane"] == "lane"
    assert doc["stats"]["valid"] == 2 and doc["stats"]["invalid"] == 3
    final = committed(client, mongo_client, clock, headers, doc["id"])
    assert final["status"] == "committed" and final["stats"]["created"] == 2
    created = sorted(_loads(client, fleet), key=lambda load: load["broker_ref"])
    assert [load["broker_ref"] for load in created] == ["VL-30422", "VL-30981"]
    first = created[1]
    assert first["status"] == "offered" and first["source"] == "import"
    assert first["truck_id"] == fleet.truck and first["carrier_id"] == fleet.carrier
    assert first["rate_cents"] == 65_000 and first["rate_per_mile_cents"] == 520
    assert first["lane"] == "Fresno, CA → Stockton, CA" and first["notes"] == "Window moved to 15:30"
    pickup = datetime(2050, 11, 1, 12, 30, tzinfo=ZoneInfo("America/Chicago"))
    assert datetime.fromisoformat(first["pickup_at"]) == pickup
    again = client.post("/v1/imports", data={"entity": "loads"}, files={"file": ("loads.csv", content, "text/csv")},
                        headers=headers)
    assert again.status_code == 200 and again.headers.get("Idempotency-Replayed") == "true"


def test_reimport_matches_by_broker_ref_and_respects_approvals(client: TestClient, mongo_client: MongoClientT,
                                                                clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    headers = fleet.firms.headers("dispatcher")
    first = uploaded(client, headers, "loads", "a.csv", csv_bytes(HEADER, ROWS[:2]))
    committed(client, mongo_client, clock, headers, first["id"])
    loads = {load["broker_ref"]: load for load in _loads(client, fleet)}
    book(client, fleet, loads["VL-30981"], 65_000)
    changed = [[*ROWS[0][:6], "$700", *ROWS[0][7:10], "new note"], [*ROWS[1][:10], "call first"]]
    second = uploaded(client, headers, "loads", "b.csv", csv_bytes(HEADER, changed))
    assert second["stats"]["existing"] == 2 and second["stats"]["new"] == 0
    final = committed(client, mongo_client, clock, headers, second["id"])
    assert final["stats"]["updated"] == 1 and final["stats"]["rejected"] == 1
    after = {load["broker_ref"]: load for load in _loads(client, fleet)}
    assert after["VL-30981"]["rate_cents"] == 65_000 and after["VL-30981"]["status"] == "booked"
    assert after["VL-30422"]["notes"] == "call first"
    report = client.get(f"/v1/imports/{second['id']}/report", headers=headers).json()["items"]
    assert [row["reason"] for row in report if row["outcome"] == "rejected"] == ["approval_required"]


def test_status_is_never_importable(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    headers = fleet.firms.headers("dispatcher")
    doc = uploaded(client, headers, "loads", "s.csv", csv_bytes(("Lane", "Status"), [["A, TX → B, TX", "Booked"]]))
    assert doc["mapping"]["Status"] is None
    refused = client.put(f"/v1/imports/{doc['id']}/mapping", json={"mapping": {"Lane": "lane", "Status": "status"}},
                         headers=headers)
    assert refused.status_code == 422, refused.text
    final = committed(client, mongo_client, clock, headers, doc["id"])
    assert [load["status"] for load in _loads(client, fleet)] == ["offered"] and final["stats"]["created"] == 1


def test_loads_workbook_with_serial_dates_and_undo(client: TestClient, mongo_client: MongoClientT,
                                                   clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    headers = fleet.firms.headers("owner")
    doc = uploaded(client, headers, "loads", "loads.xlsx", fixture_bytes("loads.xlsx"))
    columns: dict[str, str | None] = doc["mapping"]
    assert columns["Load #"] == "ref" and columns["Rate"] == "rate_cents" and columns["Delivery Date"] == "delivery_at"
    mapping = {column: field for column, field in columns.items() if field != "driver_phone"}
    second_pickup = next(column for column, field in columns.items() if column != "Pickup" and "Pickup" in column)
    mapping[second_pickup] = "origin"
    remapped = client.put(f"/v1/imports/{doc['id']}/mapping", json={"mapping": mapping}, headers=headers)
    assert remapped.status_code == 200, remapped.text
    assert remapped.json()["stats"]["valid"] == 3
    final = committed(client, mongo_client, clock, headers, doc["id"])
    assert final["stats"]["created"] == 3
    rates = sorted(load["rate_cents"] for load in _loads(client, fleet))
    assert rates == [187_550, 250_000, 310_000]
    dallas = next(load for load in _loads(client, fleet) if load["rate_cents"] == 250_000)
    assert dallas["stops"][0]["city"] == "Dallas" and dallas["stops"][0]["state"] == "TX"
    undone = client.post(f"/v1/imports/{doc['id']}/undo", headers=headers)
    assert undone.status_code == 200, undone.text
    assert undone.json()["status"] == "undone" and _loads(client, fleet) == []
