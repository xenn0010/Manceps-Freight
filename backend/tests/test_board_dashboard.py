"""The truck board and the weekly dashboard read models."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from authkit import firm_db
from bson import ObjectId
from conftest import TENANT_A, FakeClock
from datakit import created
from fastapi.testclient import TestClient
from hypothesis import given
from hypothesis import strategies as st
from loadkit import book, move, new_load, propose, seed_fleet

from manceps_core.loads import board, dashboard, machine
from manceps_core.mongo import MongoClientT


def _rows(client: TestClient, headers: dict[str, str]) -> dict[str, dict[str, object]]:
    response = client.get("/v1/board", headers=headers)
    assert response.status_code == 200, response.text
    return {str(row["unit"]): row for row in response.json()["items"]}


def test_board_rows_follow_the_load(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    viewer = fleet.firms.headers("viewer")
    row = _rows(client, viewer)["102"]
    assert row["status"] == "open" and row["tone"] == "amber" and row["load"] is None
    assert row["driver"] == {"id": fleet.driver, "name": "Ben Ortiz", "phone": "+15595550177"}
    assert row["home_base"] == "Dallas, TX"
    assert row["position"] is None and row["hos"] is None and row["duty"] is None
    load = new_load(client, fleet)
    assert _rows(client, viewer)["102"]["status"] == "offered"
    move(client, fleet, load["id"], "evaluating")
    propose(client, fleet, "accept_rate", load["id"], {"rate_cents": 65_000})
    row = _rows(client, viewer)["102"]
    assert row["status"] == "needs_approval" and row["tone"] == "amber"
    assert row["load"]["ref"] == load["ref"] and row["load"]["lane"] == "Fresno, CA → Stockton, CA"  # pyright: ignore[reportIndexIssue]
    assert str(row["next"]).startswith("Pickup Fresno, CA · ")


def test_board_in_motion_load_wins(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    moving = new_load(client, fleet)
    book(client, fleet, moving)
    db = firm_db(mongo_client, TENANT_A)
    db["loads"].update_one({"ref": moving["ref"]}, {"$set": {"status": "in_transit"}})
    clock.advance(timedelta(minutes=1))
    new_load(client, fleet)
    row = _rows(client, fleet.firms.headers("viewer"))["102"]
    assert row["status"] == "in_transit" and row["tone"] == "green"
    assert row["now"] == "In transit · Fresno, CA → Stockton, CA"
    assert str(row["next"]).startswith("Delivery Stockton, CA")


def test_board_hides_inactive_trucks_and_other_firms(client: TestClient, mongo_client: MongoClientT,
                                                     clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    headers = fleet.firms.headers("owner")
    paused = created(client, headers, "/v1/carriers", {"phone": "+12145550388", "status": "paused"})
    created(client, headers, "/v1/trucks", {"carrier_id": paused["id"], "unit": "900"})
    assert set(_rows(client, fleet.firms.headers("viewer"))) == {"102"}
    assert client.get("/v1/board", headers=fleet.firms.headers("owner_b")).json()["items"] == []
    assert client.get("/v1/board").status_code == 401
    assert client.get("/v1/board?limit=0", headers=headers).status_code == 422


def test_board_status_mapping_is_total() -> None:
    for status in machine.STATUSES:
        result = board.board_status({"status": status}, False)
        assert result in board.BOARD_STATUSES
        assert board.TONES[result] in {"grey", "amber", "green"}
    assert board.board_status(None, True) == "open"
    assert board.board_status({"status": "in_transit"}, True) == "in_transit"


def test_dashboard_summary(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    first = new_load(client, fleet)
    book(client, fleet, first, 65_000)
    second = new_load(client, fleet, loaded_miles=382, rate_cents=224_000)
    book(client, fleet, second, 224_000)
    db = firm_db(mongo_client, TENANT_A)
    last_week = clock.now - timedelta(days=7)
    db["loads"].update_one({"_id": ObjectId(second["id"])}, {"$set": {"booked_at": last_week}})
    new_load(client, fleet)
    viewer = fleet.firms.headers("viewer")
    summary = client.get("/v1/dashboard/summary", headers=viewer)
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["timezone"] == "America/Chicago" and body["week_start"] == "2050-10-24"
    assert body["this_week"]["revenue_cents"] == 65_000 and body["this_week"]["loads_booked"] == 1
    assert body["last_week"]["revenue_cents"] == 224_000
    assert body["revenue_change_cents"] == 65_000 - 224_000
    assert body["avg_rate_per_mile_cents"] == 520
    assert [day["revenue_cents"] for day in body["this_week"]["days"]] == [0, 65_000, 0, 0, 0, 0, 0]
    earlier = client.get("/v1/dashboard/summary?week_start=2050-10-17", headers=viewer).json()
    assert earlier["this_week"]["revenue_cents"] == 224_000
    tuesday = client.get("/v1/dashboard/summary?week_start=2050-10-18", headers=viewer)
    assert tuesday.status_code == 422
    assert client.get("/v1/dashboard/summary?week_start=nope", headers=viewer).status_code == 422
    assert client.get("/v1/dashboard/summary").status_code == 401
    assert client.get("/v1/dashboard/summary", headers=fleet.firms.headers("owner_b")).json()["this_week"][
        "revenue_cents"] == 0


@given(st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2100, 1, 1), timezones=st.just(UTC)),
       st.sampled_from(["America/Chicago", "America/Los_Angeles", "Pacific/Honolulu", "UTC"]))
def test_week_start_is_a_local_monday_holding_the_moment(moment: datetime, zone_name: str) -> None:
    zone = ZoneInfo(zone_name)
    start = dashboard.week_start_of(moment, zone)
    assert start.weekday() == 0
    assert 0 <= (moment.astimezone(zone).date() - start).days < 7
    assert isinstance(start, date)
