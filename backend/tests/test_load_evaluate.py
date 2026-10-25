"""Load economics: fail-closed verdicts (properties), the HTTP lookups through fake transports, and the route."""

from __future__ import annotations

import json
from typing import Any

import httpx
from conftest import FakeClock
from fastapi.testclient import TestClient
from hypothesis import given
from hypothesis import strategies as st
from loadkit import new_load, seed_fleet

from manceps_api.integrations import freight_data
from manceps_api.settings import Settings
from manceps_core.loads.evaluate import ACCEPT, COUNTER, PASS, UNKNOWN, VERDICTS, Reading, evaluate
from manceps_core.mongo import MongoClientT

CARRIER: dict[str, Any] = {"dispatch_fee_pct": 10.0, "rate_floor_per_mile": 2.5, "equipment": ["reefer"],
                           "avoid": ["NYC"], "preferred_lanes": [{"origin": "Fresno", "destination": "Stockton"}]}
LOAD: dict[str, Any] = {"rate_cents": 65_000, "loaded_miles": 125.0, "equipment": "reefer",
                        "stops": [{"seq": 1, "type": "pickup", "city": "Fresno", "state": "CA"},
                                  {"seq": 2, "type": "delivery", "city": "Stockton", "state": "CA"}]}


def diesel(price: float | None) -> Reading:
    return Reading(price, "test" if price is not None else "unknown: test")


def test_accept_needs_every_input() -> None:
    result = evaluate(LOAD, CARRIER, None, lambda: diesel(3.8))
    assert result["verdict"] == ACCEPT
    econ = result["economics"]
    assert econ["rate_per_total_mile_cents"] == 520 and econ["dispatch_fee_cents"] == 6_500
    assert econ["fuel_cost_cents"] == 7_308 and econ["carrier_net_cents"] == 65_000 - 6_500 - 7_308
    assert result["fit"]["preferred_lane"] is True
    no_diesel = evaluate(LOAD, CARRIER, None, None)
    assert no_diesel["verdict"] == UNKNOWN and "diesel" in no_diesel["unknown"]


def test_counter_pass_and_missing_miles() -> None:
    cheap = evaluate({**LOAD, "rate_cents": 20_000}, CARRIER, None, lambda: diesel(3.8))
    assert cheap["verdict"] == COUNTER and cheap["counter_at_least_cents"] == 31_250
    flatbed = evaluate({**LOAD, "equipment": "flatbed"}, CARRIER, None, None)
    assert flatbed["verdict"] == PASS
    no_miles = evaluate({**LOAD, "loaded_miles": None}, CARRIER, None, lambda: diesel(3.8))
    assert no_miles["verdict"] == UNKNOWN and no_miles["economics"] is None
    looked_up = evaluate({**LOAD, "loaded_miles": None}, CARRIER, lambda a, b: Reading(130.0, "fake"),
                         lambda: diesel(3.8))
    assert looked_up["economics"]["loaded_miles"] == 130.0 and looked_up["sources"]["miles"] == "fake"
    assert evaluate(LOAD, None, None, lambda: diesel(3.8))["verdict"] == UNKNOWN


@given(rate=st.one_of(st.none(), st.integers(min_value=0, max_value=10**8)),
       miles=st.one_of(st.none(), st.floats(min_value=0, max_value=10_000, allow_nan=False)),
       deadhead=st.one_of(st.none(), st.floats(min_value=0, max_value=1_000, allow_nan=False)),
       fee=st.one_of(st.none(), st.floats(min_value=0.1, max_value=25)),
       floor=st.one_of(st.none(), st.floats(min_value=0.01, max_value=10**7, allow_nan=False)),
       price=st.one_of(st.none(), st.floats(min_value=0.5, max_value=20)),
       has_carrier=st.booleans())
def test_verdict_is_fail_closed(rate: int | None, miles: float | None, deadhead: float | None, fee: float | None,
                                floor: float | None, price: float | None, has_carrier: bool) -> None:
    load = {**LOAD, "rate_cents": rate, "loaded_miles": miles, "deadhead_miles": deadhead}
    carrier = {**CARRIER, "dispatch_fee_pct": fee, "rate_floor_per_mile": floor} if has_carrier else None
    result = evaluate(load, carrier, None, lambda: diesel(price))
    assert result["verdict"] in VERDICTS
    if result["verdict"] == ACCEPT:
        assert result["unknown"] == [] and result["economics"]["carrier_net_cents"] is not None
    econ = result["economics"]
    if econ is not None:
        assert isinstance(econ["dispatch_fee_cents"], int | None)
        assert econ["fuel_cost_cents"] is None or econ["fuel_cost_cents"] >= 0


def _transport(handler: Any) -> freight_data.JsonClient:
    return freight_data.JsonClient(transport=httpx.MockTransport(handler), sleep=lambda _seconds: None)


def _empty(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={})


def _forbidden(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(403)


def test_google_ors_and_eia_clients() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "routes.googleapis.com":
            assert request.headers["X-Goog-Api-Key"] == "g-key"
            return httpx.Response(200, json={"routes": [{"distanceMeters": 201168}]})
        if "geocode" in request.url.path:
            return httpx.Response(200, json={"features": [{"geometry": {"coordinates": [-119.7, 36.7]}}]})
        if "directions" in request.url.path:
            assert json.loads(request.content)["coordinates"]
            return httpx.Response(200, json={"routes": [{"summary": {"distance": 160934.4}}]})
        return httpx.Response(200, json={"response": {"data": [{"value": "3.799", "period": "2026-10-20"}]}})

    client = _transport(handler)
    assert freight_data.google_miles(client, "g-key")("Fresno, CA", "Stockton, CA").value == 125.0
    assert freight_data.ors_miles(client, "o-key")("Fresno, CA", "Stockton, CA").value == 100.0
    reading = freight_data.eia_diesel(client, "e-key")()
    assert reading.value == 3.799 and "2026-10-20" in reading.source


def test_failures_become_unknown_without_leaking_keys() -> None:
    calls: list[str] = []

    def failing(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(503)

    reading = freight_data.eia_diesel(_transport(failing), "secret-key")()
    assert reading.value is None and "secret-key" not in reading.source and "HTTP 503" in reading.source
    assert len(calls) == freight_data.MAX_RETRIES + 1
    bad = freight_data.google_miles(_transport(_empty), "k")("a", "b")
    assert bad.value is None and bad.source.startswith("unknown")
    refused = freight_data.ors_miles(_transport(_forbidden), "o-key")("a", "b")
    assert refused.value is None and "o-key" not in refused.source


def test_lookups_from_settings() -> None:
    assert freight_data.miles_from_settings(Settings(env="test")) is None
    assert freight_data.diesel_from_settings(Settings(env="test")) is None
    assert freight_data.miles_from_settings(Settings(env="test", ors_api_key="o")) is not None  # pyright: ignore[reportArgumentType]
    assert freight_data.miles_from_settings(Settings(env="test", google_maps_api_key="g")) is not None  # pyright: ignore[reportArgumentType]
    assert freight_data.diesel_from_settings(Settings(env="test", eia_api_key="e")) is not None  # pyright: ignore[reportArgumentType]


def test_evaluate_route_without_keys_is_unknown(client: TestClient, mongo_client: MongoClientT,
                                                clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    load = new_load(client, fleet)
    path = f"/v1/loads/{load['id']}/evaluate"
    response = client.post(path, json={}, headers=fleet.firms.headers("dispatcher"))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "evaluating"
    assert body["evaluation"]["verdict"] == "unknown" and "diesel" in body["evaluation"]["unknown"]
    assert client.post(path, json={"mpg": 99}, headers=fleet.firms.headers("dispatcher")).status_code == 422
    assert client.post(path, json={}, headers=fleet.firms.headers("viewer")).status_code == 403
    assert client.post(path, json={}).status_code == 401
    assert client.post(path, json={}, headers=fleet.firms.headers("owner_b")).status_code == 404
