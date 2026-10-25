"""Tenant isolation: one firm can never read or write another firm's data."""

from __future__ import annotations

import json
from collections.abc import Callable

import mongomock
import pytest
from hermes_freight import brokers, carriers, tenant

CARLOS = {"phone": "214-555-0199", "fields": {"name": "Carlos", "equipment": ["dry_van"]}}


def test_firms_on_shared_cluster_do_not_see_each_other(as_tenant: Callable[..., None]) -> None:
    as_tenant("apex-freight")
    assert "carrier" in json.loads(carriers.carrier_upsert(CARLOS))
    brokers.broker_remember({"mc_number": "123456", "note": "slow pay", "tags": ["slow_pay"]})

    as_tenant("blue-line")
    assert json.loads(carriers.carrier_get({"phone": "2145550199"}))["found"] is False
    assert json.loads(carriers.carrier_list({}))["carriers"] == []
    assert json.loads(brokers.broker_recall({"mc_number": "123456"}))["known"] is False

    as_tenant("apex-freight")
    assert json.loads(carriers.carrier_get({"phone": "2145550199"}))["found"] is True


def test_each_firm_gets_its_own_database(
    as_tenant: Callable[..., None], mongo: dict[str, mongomock.MongoClient]
) -> None:
    as_tenant("apex-freight")
    carriers.carrier_upsert(CARLOS)
    as_tenant("blue-line")
    carriers.carrier_upsert({**CARLOS, "fields": {"name": "Other Carlos"}})

    names = set(next(iter(mongo.values())).list_database_names())
    assert {"firm_apex_freight", "firm_blue_line"} <= names


def test_missing_tenant_fails_closed() -> None:
    result = json.loads(carriers.carrier_list({}))
    assert "error" in result and tenant.TENANT_ENV in result["error"]
    assert carriers.consented("2145550199", "sms") is False


def test_missing_uri_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(tenant.TENANT_ENV, "apex-freight")
    with pytest.raises(tenant.TenantError, match=tenant.URI_ENV):
        tenant.current()


@pytest.mark.parametrize("bad", ["", "A", "ab", "Apex", "apex_freight", "1apex", "apex-", "x" * 40, "../admin"])
def test_invalid_tenant_ids_rejected(bad: str) -> None:
    with pytest.raises(tenant.TenantError):
        tenant.validate_tenant_id(bad)


def test_tool_arguments_cannot_select_a_tenant(as_tenant: Callable[..., None]) -> None:
    as_tenant("apex-freight")
    result = json.loads(carriers.carrier_upsert({**CARLOS, "fields": {"name": "x", "tenant_id": "blue-line"}}))
    assert "unknown fields" in result["error"]


def test_separate_uris_use_separate_clients(
    as_tenant: Callable[..., None], mongo: dict[str, mongomock.MongoClient]
) -> None:
    as_tenant("apex-freight", "mongodb://apex-user@cluster.test")
    carriers.carrier_upsert(CARLOS)
    as_tenant("blue-line", "mongodb://blue-user@cluster.test")
    assert json.loads(carriers.carrier_get({"phone": "2145550199"}))["found"] is False
    assert len(mongo) == 2
