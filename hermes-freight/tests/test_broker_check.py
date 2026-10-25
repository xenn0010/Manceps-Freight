"""Broker vetting: every lookup failure is unknown, never a pass."""

from __future__ import annotations

import json
import urllib.error
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from hermes_freight import broker_check, reference, store, tenant

GOOD_CARRIER = {"content": {"carrier": {"dotNumber": 777, "allowedToOperate": "Y", "legalName": "ACME LOGISTICS"}}}
GOOD_AUTHORITY = {"content": [{"carrierAuthority": {"brokerAuthorityStatus": "A"}}]}


def _rdap(days_old: int) -> dict[str, Any]:
    when = datetime.now(UTC) - timedelta(days=days_old)
    return {"events": [{"eventAction": "registration", "eventDate": when.strftime("%Y-%m-%dT%H:%M:%SZ")}]}


@pytest.fixture(autouse=True)
def _firm(as_tenant: Callable[..., None], monkeypatch: pytest.MonkeyPatch) -> None:
    as_tenant("apex-freight")
    monkeypatch.setenv(broker_check.FMCSA_KEY_ENV, "test-key")
    dns = {"MX": ["10 mx.acme.com."], "TXT": ["v=spf1 include:_spf.google.com ~all"]}
    monkeypatch.setattr(broker_check, "resolve_txt",
                        lambda name, rdtype: ["v=DMARC1; p=reject"] if name.startswith("_dmarc.") else dns[rdtype])


def _http(routes: dict[str, Any]) -> Callable[[str], Any]:
    def fake(url: str) -> Any:
        for fragment, response in routes.items():
            if fragment in url:
                if isinstance(response, Exception):
                    raise response
                return response
        raise AssertionError(f"unexpected URL {url}")

    return fake


def _run(monkeypatch: pytest.MonkeyPatch, routes: dict[str, Any], **args: str) -> dict[str, Any]:
    monkeypatch.setattr(broker_check, "http_get_json", _http(routes))
    return json.loads(broker_check.broker_check(args))


def _status(result: dict[str, Any], name: str) -> str:
    return next(c["status"] for c in result["checks"] if c["check"] == name)


def _load_bond(mc: str) -> None:
    db = tenant.shared_database(reference.DB_NAME)
    db["sync_meta"].insert_one({"_id": "broker_bonds", "complete": True, "source_updated": "2026-10-20"})
    db["broker_bonds"].insert_one({"_id": f"MC{mc}|84", "mc_number": mc, "form_name": "BMC-84 surety bond",
                                   "surety": "ACME SURETY", "cancellation_effective_date": None})


def test_clean_broker_looks_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _load_bond("123456")
    routes = {"/authority": GOOD_AUTHORITY, "docket-number/123456": {"content": [GOOD_CARRIER["content"]]},
              "rdap.org": _rdap(2000)}
    result = _run(monkeypatch, routes, mc_number="MC-123456", email="ops@acme.com")
    assert result["verdict"] == "looks_ok"
    assert result["dot_number"] == "777"
    assert _status(result, "bond") == "pass"
    assert store.collection(store.BROKER_CHECKS).count_documents({"mc_number": "123456"}) == 1


def test_bond_data_not_loaded_is_review(monkeypatch: pytest.MonkeyPatch) -> None:
    routes = {"/authority": GOOD_AUTHORITY, "docket-number/123456": {"content": [GOOD_CARRIER["content"]]}}
    result = _run(monkeypatch, routes, mc_number="123456")
    assert _status(result, "bond") == "unknown" and result["verdict"] == "review"


def test_fmcsa_outage_is_unknown_not_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(monkeypatch, {"mobile.fmcsa.dot.gov": urllib.error.URLError("down")}, dot_number="777")
    assert _status(result, "fmcsa_operating") == "unknown"
    assert _status(result, "broker_authority") == "unknown"
    assert result["verdict"] == "review"


def test_missing_key_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(broker_check.FMCSA_KEY_ENV)
    result = _run(monkeypatch, {}, dot_number="777")
    assert _status(result, "fmcsa_operating") == "unknown" and result["verdict"] == "review"


def test_not_allowed_to_operate_is_do_not_book(monkeypatch: pytest.MonkeyPatch) -> None:
    carrier = {"content": {"carrier": {"dotNumber": 777, "allowedToOperate": "N"}}}
    result = _run(monkeypatch, {"/authority": GOOD_AUTHORITY, "carriers/777": carrier}, dot_number="777")
    assert result["verdict"] == "do_not_book"


def test_inactive_broker_authority_is_do_not_book(monkeypatch: pytest.MonkeyPatch) -> None:
    authority = {"content": [{"carrierAuthority": {"brokerAuthorityStatus": "I"}}]}
    result = _run(monkeypatch, {"/authority": authority, "carriers/777": GOOD_CARRIER}, dot_number="777")
    assert result["verdict"] == "do_not_book"


def test_no_fmcsa_record_is_do_not_book(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(monkeypatch, {"docket-number/999": {"content": []}}, mc_number="999")
    assert result["verdict"] == "do_not_book"


def test_new_domain_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    routes = {"/authority": GOOD_AUTHORITY, "carriers/777": GOOD_CARRIER, "rdap.org": _rdap(20)}
    result = _run(monkeypatch, routes, dot_number="777", email="ops@acme-new.com")
    assert _status(result, "domain_age") == "fail" and result["verdict"] == "do_not_book"


def test_free_email_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    routes = {"/authority": GOOD_AUTHORITY, "carriers/777": GOOD_CARRIER}
    result = _run(monkeypatch, routes, dot_number="777", email="acmeloads@gmail.com")
    assert _status(result, "email_domain") == "warn" and result["verdict"] == "review"


def test_requires_mc_or_dot(monkeypatch: pytest.MonkeyPatch) -> None:
    assert "error" in _run(monkeypatch, {}, email="ops@acme.com")
