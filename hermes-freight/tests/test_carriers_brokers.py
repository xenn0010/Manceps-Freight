"""Carrier roster and broker memory behavior within one firm."""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest
from hermes_freight import brokers, carriers, store


@pytest.fixture(autouse=True)
def _firm(as_tenant: Callable[..., None]) -> None:
    as_tenant("apex-freight")


@pytest.mark.parametrize("raw", ["214-555-0199", "(214) 555 0199", "+1 214 555 0199", "12145550199"])
def test_normalize_phone(raw: str) -> None:
    assert carriers.normalize_phone(raw) == "+12145550199"


@pytest.mark.parametrize("raw", ["", "555-0199", "+44 20 7946 0958"])
def test_normalize_phone_rejects(raw: str) -> None:
    with pytest.raises(ValueError):
        carriers.normalize_phone(raw)


def test_upsert_updates_instead_of_duplicating() -> None:
    carriers.carrier_upsert({"phone": "2145550199", "fields": {"name": "Carlos", "dispatch_fee_pct": 8}})
    carriers.carrier_upsert({"phone": "214-555-0199", "fields": {"home_base": "Dallas, TX"}})
    listed = json.loads(carriers.carrier_list({}))["carriers"]
    assert len(listed) == 1
    assert listed[0]["dispatch_fee_pct"] == 8 and listed[0]["home_base"] == "Dallas, TX"
    assert store.collection(store.AUDIT).count_documents({"event": "carrier.upsert"}) == 2


@pytest.mark.parametrize(
    "fields, message",
    [
        ({"equipment": ["spaceship"]}, "unknown equipment"),
        ({"dispatch_fee_pct": 40}, "dispatch_fee_pct"),
        ({"rate_floor_per_mile": 0}, "rate_floor_per_mile"),
        ({"consent": {"sms": True}}, "consent.method"),
    ],
)
def test_upsert_validation(fields: dict[str, object], message: str) -> None:
    result = json.loads(carriers.carrier_upsert({"phone": "2145550199", "fields": fields}))
    assert message in result["error"]


def test_consent_is_per_channel() -> None:
    carriers.carrier_upsert({"phone": "2145550199",
                             "fields": {"consent": {"sms": True, "method": "signed agreement 2026-10-24"}}})
    assert carriers.consented("214-555-0199", "sms") is True
    assert carriers.consented("214-555-0199", "voice") is False
    assert carriers.consented("972-555-0100", "sms") is False


def test_broker_memory_round_trip() -> None:
    brokers.broker_remember({"mc_number": "MC-123456", "note": "paid in 45 days", "tags": ["slow_pay"]})
    brokers.broker_remember({"mc_number": "123456", "note": "paid detention", "tags": ["pays_detention"],
                             "company": "ACME Logistics"})
    recall = json.loads(brokers.broker_recall({"mc_number": "123456"}))
    assert recall["known"] is True
    assert recall["broker"]["company"] == "ACME Logistics"
    assert sorted(recall["broker"]["tags"]) == ["pays_detention", "slow_pay"]
    assert recall["broker"]["notes"][0]["text"] == "paid detention"


@pytest.mark.parametrize(
    "args, message",
    [
        ({"note": "x"}, "mc_number"),
        ({"mc_number": "1", "note": ""}, "note is required"),
        ({"mc_number": "1", "note": "x", "tags": ["Slow Pay"]}, "snake_case"),
    ],
)
def test_broker_remember_validation(args: dict[str, object], message: str) -> None:
    assert message in json.loads(brokers.broker_remember(args))["error"]
