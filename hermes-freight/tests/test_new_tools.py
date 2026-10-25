"""Rate Con reader, weather alerts, and load evaluator."""

from __future__ import annotations

import json
import urllib.error
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from hermes_freight import carriers, loads, ratecon, weather

TERMS: dict[str, Any] = {
    "broker_name": "ACME Logistics", "broker_mc": "MC 123456", "load_number": "L1", "carrier_name": "Carlos",
    "carrier_mc": "999", "total_rate_usd": 2500.0, "linehaul_usd": 2300.0, "fuel_surcharge_usd": 200.0,
    "accessorials": [], "equipment": "Dry Van 53'", "weight_lbs": 40000, "commodity": "paper",
    "stops": [
        {"kind": "delivery", "sequence": 2, "facility": "B", "address": "", "city": "Atlanta", "state": "GA",
         "date": "2026-10-27", "time_window": "", "appointment_required": True, "reference_numbers": []},
        {"kind": "pickup", "sequence": 1, "facility": "A", "address": "", "city": "Dallas", "state": "TX",
         "date": "2026-10-25", "time_window": "08:00-12:00", "appointment_required": False, "reference_numbers": []},
    ],
    "payment_terms": "30 days", "quick_pay_terms": "", "detention_terms": "", "layover_terms": "",
    "tonu_terms": "", "tracking_requirements": "Macropoint", "fines_and_penalties": ["$250 late fee"],
    "special_requirements": [], "unreadable_fields": [],
}
AGREED = {"rate_usd": 2500, "origin": "Dallas, TX", "destination": "Atlanta, GA", "pickup_date": "2026-10-25",
          "equipment": "dry van", "broker_mc": "123456"}


@pytest.fixture(autouse=True)
def _firm(as_tenant: Callable[..., None], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    as_tenant("apex-freight")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


def _pdf(tmp_path: Path, name: str = "ratecon.pdf") -> Path:
    cache = tmp_path / "cache" / "documents"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / name
    path.write_bytes(b"%PDF-1.4 test")
    return path


def test_compare_matches_agreement() -> None:
    assert ratecon.compare(TERMS, AGREED) == []


def test_compare_flags_rate_and_city() -> None:
    issues = ratecon.compare(TERMS, {**AGREED, "rate_usd": 2700, "destination": "Miami, FL"})
    assert any(i.startswith("rate:") for i in issues) and any(i.startswith("destination:") for i in issues)


def test_flags_penalties_detention_tracking() -> None:
    out = ratecon.flags(TERMS)
    assert "penalty clause: $250 late fee" in out and "no detention terms stated" in out
    assert any("Macropoint" in f for f in out)


def test_path_outside_document_cache_refused(tmp_path: Path) -> None:
    outside = tmp_path / "secrets.pdf"
    outside.write_bytes(b"%PDF")
    for path in (str(outside), str(tmp_path / "cache" / "documents" / ".." / ".." / "secrets.pdf"), "/etc/passwd"):
        assert "error" in json.loads(ratecon.ratecon_read({"path": path}))


def test_non_pdf_refused(tmp_path: Path) -> None:
    (tmp_path / "cache" / "documents").mkdir(parents=True)
    env = tmp_path / "cache" / "documents" / "x.env"
    env.write_text("KEY=1")
    assert "not a PDF" in json.loads(ratecon.ratecon_read({"path": str(env)}))["error"]


class _FakeClient:
    def __init__(self, stop_reason: str = "end_turn", payload: dict[str, Any] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        content = [SimpleNamespace(type="text", text=json.dumps(payload or TERMS))]
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self._response = SimpleNamespace(stop_reason=stop_reason, content=content)

    def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self._response


def test_extract_sends_pdf_with_schema_and_fallback(tmp_path: Path) -> None:
    client = _FakeClient()
    assert ratecon.extract(_pdf(tmp_path), client)["total_rate_usd"] == 2500.0  # type: ignore[arg-type]
    call = client.calls[0]
    assert call["model"] == "claude-sonnet-5-5" and call["fallbacks"] == "default"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["messages"][0]["content"][0]["source"]["media_type"] == "application/pdf"
    assert "temperature" not in call and "tool_choice" not in call


def test_extract_refusal_raises(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="declined"):
        ratecon.extract(_pdf(tmp_path), _FakeClient(stop_reason="refusal"))  # type: ignore[arg-type]


def test_ratecon_read_verdicts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ratecon, "extract", lambda pdf, client=None: TERMS)
    path = str(_pdf(tmp_path))
    mismatch = {"path": path, "agreed": {**AGREED, "rate_usd": 2800}}
    assert json.loads(ratecon.ratecon_read(mismatch))["verdict"] == "do_not_sign"
    assert json.loads(ratecon.ratecon_read({"path": path, "agreed": AGREED}))["verdict"] == "review"


def test_weather_filters_and_sorts(monkeypatch: pytest.MonkeyPatch) -> None:
    alerts = [{"event": "Heat Advisory", "severity": "Moderate"},
              {"event": "Winter Storm Warning", "severity": "Moderate", "onset": "2"},
              {"event": "Tornado Warning", "severity": "Extreme", "onset": "1"}]
    monkeypatch.setattr(weather, "fetch_alerts", lambda states: alerts)
    result = json.loads(weather.weather_alerts({"states": ["tx", "OK"]}))
    assert result["states"] == ["OK", "TX"]
    assert [a["event"] for a in result["alerts"]] == ["Tornado Warning", "Winter Storm Warning"]


def test_weather_failure_is_unknown_not_clear(monkeypatch: pytest.MonkeyPatch) -> None:
    def down(states: list[str]) -> list[dict[str, Any]]:
        raise urllib.error.URLError("down")

    monkeypatch.setattr(weather, "fetch_alerts", down)
    result = json.loads(weather.weather_alerts({"states": ["TX"]}))
    assert result["status"] == "unknown" and "alerts" not in result


def test_weather_rejects_bad_states() -> None:
    assert "error" in json.loads(weather.weather_alerts({"states": ["Texas"]}))


@pytest.fixture
def carlos() -> str:
    carriers.carrier_upsert({"phone": "2145550199", "fields": {
        "equipment": ["dry_van"], "dispatch_fee_pct": 8, "rate_floor_per_mile": 2.0,
        "preferred_lanes": [{"origin": "Dallas", "destination": "Atlanta"}], "avoid": ["NYC"]}})
    return "2145550199"


def _offer(phone: str, **extra: Any) -> dict[str, Any]:
    return json.loads(loads.load_evaluate({"carrier_phone": phone, "origin": "Dallas, TX",
                                           "destination": "Atlanta, GA", "equipment": "dry_van", **extra}))


def test_load_accept_range_with_given_miles(carlos: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loads, "diesel_price", lambda: (4.0, "test"))
    result = _offer(carlos, rate_usd=2000, loaded_miles=800, deadhead_miles=50)
    econ = result["economics"]
    assert econ["total_miles"] == 850 and econ["dispatch_fee_usd"] == 160.0
    assert econ["fuel_cost_usd"] == round(850 / 6.5 * 4.0, 2)
    assert result["verdict"] == "accept_range" and result["fit"]["preferred_lane"] is True


def test_load_counter_below_floor(carlos: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loads, "diesel_price", lambda: (None, "unknown"))
    result = _offer(carlos, rate_usd=1500, loaded_miles=800, deadhead_miles=100)
    assert result["verdict"] == "counter" and result["counter_at_least_usd"] == 1800.0
    assert result["economics"]["fuel_cost_usd"] is None


def test_load_unknown_miles_without_ors_key(carlos: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loads, "diesel_price", lambda: (None, "unknown"))
    result = _offer(carlos, rate_usd=2000)
    assert result["verdict"] == "unknown" and "ORS_API_KEY" in result["sources"]["miles"]


def test_load_pass_on_equipment_or_avoid(carlos: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loads, "diesel_price", lambda: (None, "unknown"))
    assert _offer(carlos, rate_usd=3000, loaded_miles=800, equipment="reefer")["verdict"] == "pass"


def test_load_bad_miles_is_error_not_crash(carlos: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loads, "diesel_price", lambda: (None, "unknown"))
    assert "error" in _offer(carlos, rate_usd=2000, loaded_miles="about 800")
    assert "error" in _offer(carlos, rate_usd=2000, loaded_miles=800, deadhead_miles="some")


def test_load_rejects_unknown_carrier() -> None:
    assert "roster" in _offer("9725550100", rate_usd=2000, loaded_miles=800)["error"]


def test_route_miles_uses_ors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORS_API_KEY", "k")
    monkeypatch.setattr(loads.broker_check, "http_get_json",
                        lambda url: {"features": [{"geometry": {"coordinates": [-96.8, 32.8]}}]})
    route = {"routes": [{"summary": {"distance": 1609344}}]}
    monkeypatch.setattr(loads, "http_post_json", lambda url, body, headers: route)
    miles, source = loads.route_miles("Dallas, TX", "Atlanta, GA")
    assert miles == 1000.0 and "driving-hgv" in source


def test_route_miles_prefers_google(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "g")
    monkeypatch.setenv("ORS_API_KEY", "o")
    seen: dict[str, Any] = {}

    def fake_post(url: str, body: dict[str, Any], headers: dict[str, str]) -> Any:
        seen.update(url=url, body=body, headers=headers)
        return {"routes": [{"distanceMeters": 1260142}]}

    monkeypatch.setattr(loads, "http_post_json", fake_post)
    miles, source = loads.route_miles("Dallas, TX", "Atlanta, GA")
    assert miles == 783.0 and "Google" in source
    assert seen["body"]["origin"] == {"address": "Dallas, TX"} and seen["headers"]["X-Goog-Api-Key"] == "g"


def test_google_failure_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "g")

    def boom(url: str, body: dict[str, Any], headers: dict[str, str]) -> Any:
        raise urllib.error.URLError("denied")

    monkeypatch.setattr(loads, "http_post_json", boom)
    miles, source = loads.route_miles("Dallas, TX", "Atlanta, GA")
    assert miles is None and source.startswith("unknown")
