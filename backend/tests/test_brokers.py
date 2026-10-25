"""Brokers: firm memory keyed by MC, notes, vetting checks that fail closed, and FMCSA reference search."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from authkit import firm_db, one
from conftest import START, TENANT_A, FakeClock, FakeVerifier
from datakit import created, error_code, seed_firms
from fastapi.testclient import TestClient

from manceps_api.app import create_app
from manceps_api.integrations.broker_lookup import BrokerLookup
from manceps_api.integrations.configured import Integrations
from manceps_api.settings import Settings
from manceps_core.brokers.check import LookupFailed, run_check
from manceps_core.brokers.reference import REFERENCE_DB
from manceps_core.mongo import MongoClientT, MongoDb

FMCSA_KEY = "test-fmcsa-key"
GOOD_CARRIER = {"content": {"carrier": {"dotNumber": 777, "allowedToOperate": "Y", "legalName": "ACME LOGISTICS"}}}
GOOD_AUTHORITY = {"content": [{"carrierAuthority": {"brokerAuthorityStatus": "A"}}]}
GOOD_DNS = {"MX": ["10 mx.acme.com."], "TXT": ["v=spf1 include:_spf.google.com ~all"]}


class FakeTransport:
    """Lookup transport double: URL fragment -> JSON (or an exception to raise), canned DNS answers."""

    def __init__(self, routes: dict[str, Any] | None = None, dns_failure: bool = False) -> None:
        """Configure responses.

        Args:
            routes: URL fragment to response or exception.
            dns_failure: Make every DNS lookup fail.
        """
        self.routes: dict[str, Any] = dict(routes or {})
        self.dns_failure = dns_failure
        self.urls: list[str] = []

    def get_json(self, url: str) -> Any:
        """Return the first matching canned response.

        Args:
            url: Requested URL.

        Returns:
            The response.

        Raises:
            LookupFailed: When the route is configured to fail.
            AssertionError: For a URL the test did not expect.
        """
        self.urls.append(url)
        for fragment, response in self.routes.items():
            if fragment in url:
                if isinstance(response, Exception):
                    raise response
                return response
        raise AssertionError(f"unexpected URL {url}")

    def resolve(self, name: str, rdtype: str) -> list[str]:
        """Return canned DNS records.

        Args:
            name: DNS name.
            rdtype: Record type.

        Returns:
            Records.

        Raises:
            LookupFailed: When DNS is configured to fail.
        """
        if self.dns_failure:
            raise LookupFailed("dns down")
        return ["v=DMARC1; p=reject"] if name.startswith("_dmarc.") else GOOD_DNS[rdtype]


class NoMxTransport(FakeTransport):
    """A transport whose domains have no DNS records at all."""

    def resolve(self, name: str, rdtype: str) -> list[str]:
        """Return no records.

        Args:
            name: DNS name.
            rdtype: Record type.

        Returns:
            An empty list.
        """
        del name, rdtype
        return []


@pytest.fixture
def transport() -> FakeTransport:
    """Return the lookup transport wired into the app.

    Returns:
        The fake transport.
    """
    return FakeTransport()


@pytest.fixture
def integrations(verifier: FakeVerifier, transport: FakeTransport) -> Integrations:
    """Wire the fake broker lookup into the app.

    Args:
        verifier: Fake verifier.
        transport: Fake lookup transport.

    Returns:
        The integrations.
    """
    return Integrations(verifier=verifier, mailer=None, broker_lookup=BrokerLookup(FMCSA_KEY, transport))


def _reference(mongo_client: MongoClientT) -> MongoDb:
    """Return the shared reference database.

    Args:
        mongo_client: In-memory client.

    Returns:
        The database.
    """
    return mongo_client[REFERENCE_DB]


def _load_reference(db: MongoDb, bond_mc: str | None = "123456") -> None:
    """Load broker census rows and, optionally, an active bond.

    Args:
        db: Reference database.
        bond_mc: MC with an active bond, or None for no bond data at all.
    """
    db["sync_meta"].insert_one({"_id": "brokers", "complete": True, "source_updated": "2026-10-20"})
    db["brokers"].insert_many([
        {"_id": "777", "dot_number": "777", "mc_numbers": ["123456"], "legal_name": "ACME LOGISTICS",
         "dba_name": None, "city": "DALLAS", "state": "TX"},
        {"_id": "888", "dot_number": "888", "mc_numbers": ["222222"], "legal_name": "ACME FREIGHT BROKERS",
         "dba_name": "ACME FB", "city": "MIAMI", "state": "FL"},
    ])
    if bond_mc is not None:
        db["sync_meta"].insert_one({"_id": "broker_bonds", "complete": True, "source_updated": "2026-10-20"})
        db["broker_bonds"].insert_one({"_id": f"MC{bond_mc}|84", "mc_number": bond_mc, "dot_number": "",
                                       "form_name": "BMC-84 surety bond", "surety": "ACME SURETY",
                                       "cancellation_effective_date": None})


def _rdap(days_old: int) -> dict[str, Any]:
    """Build an RDAP response for a domain registered some days before START.

    Args:
        days_old: Domain age.

    Returns:
        RDAP JSON.
    """
    when = START - timedelta(days=days_old)
    return {"events": [{"eventAction": "registration", "eventDate": when.strftime("%Y-%m-%dT%H:%M:%SZ")}]}


def _status(result: dict[str, Any], name: str) -> str:
    """Return one check's status.

    Args:
        result: Check result.
        name: Check name.

    Returns:
        The status.
    """
    return str(next(check["status"] for check in result["checks"] if check["check"] == name))


def test_broker_crud_and_notes(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    _load_reference(_reference(mongo_client))
    broker = created(client, firms.headers("dispatcher"), "/v1/brokers",
                     {"mc_number": "MC-123456", "tags": ["slow_pay"], "payment_terms": "net 30"})
    assert broker["mc_number"] == "123456" and broker["company"] == "ACME LOGISTICS" and broker["notes"] == []
    duplicate = client.post("/v1/brokers", json={"mc_number": "123456"}, headers=firms.headers("dispatcher"))
    assert duplicate.status_code == 409 and error_code(duplicate) == "duplicate_mc"
    unknown = created(client, firms.headers("dispatcher"), "/v1/brokers", {"mc_number": "999999"})
    assert unknown["company"] is None
    for text in ("first call went fine", "paid in 45 days"):
        clock.advance(timedelta(minutes=1))
        response = client.post("/v1/brokers/123456/notes", json={"text": text}, headers=firms.headers("dispatcher"))
        assert response.status_code == 201, response.text
    fetched = client.get("/v1/brokers/MC-123456", headers=firms.headers("viewer")).json()
    assert [note["text"] for note in fetched["notes"]] == ["paid in 45 days", "first call went fine"]
    patched = client.patch("/v1/brokers/123456", json={"tags": ["slow_pay", "good_detention"], "credit_notes": "ok"},
                           headers=firms.headers("dispatcher"))
    assert patched.status_code == 200 and patched.json()["tags"] == ["good_detention", "slow_pay"]
    assert client.get("/v1/brokers?tag=good_detention", headers=firms.headers("viewer")).json()["items"][0][
        "mc_number"] == "123456"
    assert [item["mc_number"] for item in client.get("/v1/brokers?q=acme", headers=firms.headers("viewer")).json()[
        "items"]] == ["123456"]
    for bad in ({"mc_number": "MC-"}, {"mc_number": "1", "tags": ["has space"]}, {"mc_number": "1", "extra": 1}):
        assert client.post("/v1/brokers", json=bad, headers=firms.headers("dispatcher")).status_code == 422, bad
    assert client.post("/v1/brokers/123456/notes", json={"text": "x" * 1001},
                       headers=firms.headers("dispatcher")).status_code == 422
    assert client.post("/v1/brokers/123456/notes", json={"text": "hi"}, headers=firms.headers("viewer")).status_code \
        == 403
    assert client.patch("/v1/brokers/123456", json={}, headers=firms.headers("dispatcher")).status_code == 422
    assert client.get("/v1/brokers/555", headers=firms.headers("viewer")).status_code == 404
    assert client.get("/v1/brokers").status_code == 401


def test_plugin_written_broker_is_readable(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    firm_db(mongo_client, TENANT_A)["brokers"].insert_one({
        "mc_number": "424242", "company": "Plugin Broker", "tags": ["slow_pay"], "created_at": clock(),
        "updated_at": clock(), "notes": [{"at": clock(), "text": "from the agent", "session_id": "s1"}],
    })
    body = client.get("/v1/brokers/424242", headers=firms.headers("viewer")).json()
    assert body["notes"][0]["text"] == "from the agent" and body["last_check"] is None


def test_broker_check_failure_is_unknown_not_pass(client: TestClient, mongo_client: MongoClientT, clock: FakeClock,
                                                  transport: FakeTransport) -> None:
    firms = seed_firms(client, mongo_client, clock)
    created(client, firms.headers("dispatcher"), "/v1/brokers", {"mc_number": "123456", "company": "Acme"})
    transport.routes = {"mobile.fmcsa.dot.gov": LookupFailed("HTTP 503"), "rdap.org": LookupFailed("timeout")}
    transport.dns_failure = True
    response = client.post("/v1/brokers/123456/check", json={"email": "ops@acme.com"},
                           headers=firms.headers("dispatcher"))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["verdict"] == "review"
    for name in ("fmcsa_operating", "broker_authority", "bond", "domain_age", "email_dns"):
        assert _status(result, name) == "unknown", name
    assert all(check["status"] != "pass" for check in result["checks"])
    assert FMCSA_KEY not in response.text
    db = firm_db(mongo_client, TENANT_A)
    stored = one(db, "broker_checks", {"mc_number": "123456"})
    assert stored["verdict"] == "review" and FMCSA_KEY not in str(stored)
    broker = client.get("/v1/brokers/123456", headers=firms.headers("viewer")).json()
    assert broker["last_check"]["verdict"] == "review"
    history = client.get("/v1/brokers/123456/checks", headers=firms.headers("viewer")).json()
    assert [item["verdict"] for item in history["items"]] == ["review"]
    assert client.post("/v1/brokers/123456/check", json={}, headers=firms.headers("viewer")).status_code == 403
    assert client.post("/v1/brokers/555/check", json={}, headers=firms.headers("dispatcher")).status_code == 404
    assert client.post("/v1/brokers/123456/check", json={"email": "x" * 300},
                       headers=firms.headers("dispatcher")).status_code == 422


def test_broker_check_clean_broker_looks_ok(client: TestClient, mongo_client: MongoClientT, clock: FakeClock,
                                            transport: FakeTransport) -> None:
    firms = seed_firms(client, mongo_client, clock)
    _load_reference(_reference(mongo_client))
    created(client, firms.headers("dispatcher"), "/v1/brokers", {"mc_number": "123456"})
    transport.routes = {"/authority": GOOD_AUTHORITY, "docket-number/123456": {"content": [GOOD_CARRIER["content"]]},
                        "rdap.org": _rdap(2000)}
    result = client.post("/v1/brokers/123456/check", json={"email": "ops@acme.com"},
                         headers=firms.headers("dispatcher")).json()
    assert result["verdict"] == "looks_ok" and result["dot_number"] == "777" and _status(result, "bond") == "pass"


def test_broker_check_not_configured_503(settings: Settings, mongo_client: MongoClientT, clock: FakeClock) -> None:
    app = create_app(settings, mongo_client, clock=clock, integrations=Integrations(verifier=FakeVerifier()))
    with TestClient(app) as client:
        firms = seed_firms(client, mongo_client, clock)
        created(client, firms.headers("dispatcher"), "/v1/brokers", {"mc_number": "123456"})
        response = client.post("/v1/brokers/123456/check", json={}, headers=firms.headers("dispatcher"))
    assert response.status_code == 503 and error_code(response) == "integration_not_configured"


@pytest.mark.parametrize(("routes", "args", "verdict", "check", "status"), [
    ({"/authority": GOOD_AUTHORITY, "carriers/777": {"content": {"carrier": {"dotNumber": 777,
                                                                             "allowedToOperate": "N"}}}},
     {"dot": "777"}, "do_not_book", "fmcsa_operating", "fail"),
    ({"/authority": {"content": [{"carrierAuthority": {"brokerAuthorityStatus": "I"}}]},
      "carriers/777": GOOD_CARRIER}, {"dot": "777"}, "do_not_book", "broker_authority", "fail"),
    ({"docket-number/999": {"content": []}}, {"mc": "999"}, "do_not_book", "fmcsa_operating", "fail"),
    ({"/authority": GOOD_AUTHORITY, "carriers/777": GOOD_CARRIER, "rdap.org": _rdap(20)},
     {"dot": "777", "email": "ops@acme-new.com"}, "do_not_book", "domain_age", "fail"),
    ({"/authority": GOOD_AUTHORITY, "carriers/777": GOOD_CARRIER},
     {"dot": "777", "email": "acmeloads@gmail.com"}, "review", "email_domain", "warn"),
    ({"/authority": {"content": "garbled"}, "carriers/777": GOOD_CARRIER}, {"dot": "777"}, "review",
     "broker_authority", "unknown"),
    ({"carriers/777": ["not", "a", "dict"]}, {"dot": "777"}, "review", "fmcsa_operating", "unknown"),
    ({"/authority": GOOD_AUTHORITY, "carriers/777": GOOD_CARRIER, "rdap.org": {"events": []}},
     {"dot": "777", "email": "ops@acme.com"}, "review", "domain_age", "unknown"),
])
def test_check_verdicts(mongo_client: MongoClientT, routes: dict[str, Any], args: dict[str, str], verdict: str,
                        check: str, status: str) -> None:
    db = _reference(mongo_client)
    _load_reference(db, bond_mc=None)
    result = run_check(FakeTransport(routes), FMCSA_KEY, args.get("mc", ""), args.get("dot", ""),
                       args.get("email", ""), db, START)
    assert result["verdict"] == verdict and _status(result, check) == status


def test_check_requires_identifier_and_handles_reference_states(mongo_client: MongoClientT) -> None:
    db = _reference(mongo_client)
    with pytest.raises(ValueError, match="mc_number or dot_number"):
        run_check(FakeTransport(), FMCSA_KEY, "", "", "", db, START)
    routes = {"/authority": GOOD_AUTHORITY, "carriers/777": GOOD_CARRIER}
    assert _status(run_check(FakeTransport(routes), FMCSA_KEY, "", "777", "", db, START), "bond") == "unknown"
    _load_reference(db, bond_mc="123456")
    db["broker_bonds"].insert_one({"_id": "old", "mc_number": "", "dot_number": "777", "form_name": "BMC-84",
                                   "surety": "OLD", "cancellation_effective_date": "01/01/2020"})
    assert _status(run_check(FakeTransport(routes), FMCSA_KEY, "", "777", "", db, START), "bond") == "fail"
    db["broker_bonds"].update_one({"_id": "old"}, {"$set": {"cancellation_effective_date": "garbled"}})
    assert _status(run_check(FakeTransport(routes), FMCSA_KEY, "", "777", "", db, START), "bond") == "unknown"
    db["broker_bonds"].update_one({"_id": "old"}, {"$set": {"cancellation_effective_date": "01/01/2099"}})
    assert _status(run_check(FakeTransport(routes), FMCSA_KEY, "", "777", "", db, START), "bond") == "pass"
    bad_email = run_check(FakeTransport(routes), FMCSA_KEY, "", "777", "not-an-email", db, START)
    assert _status(bad_email, "email_domain") == "unknown"
    no_mx = NoMxTransport({**routes, "rdap.org": _rdap(2000)})
    assert _status(run_check(no_mx, FMCSA_KEY, "", "777", "ops@acme.com", db, START), "email_dns") == "fail"


def test_reference_search(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    _load_reference(_reference(mongo_client))
    by_mc = client.get("/v1/reference/brokers?mc=MC-0123456", headers=firms.headers("viewer"))
    assert by_mc.status_code == 200, by_mc.text
    body = by_mc.json()
    assert body["count"] == 1 and body["items"][0]["legal_name"] == "ACME LOGISTICS"
    assert "not consent" in body["note"] and "2026-10-20" in body["source"]
    assert client.get("/v1/reference/brokers?dot=888", headers=firms.headers("viewer")).json()["items"][0][
        "state"] == "FL"
    by_name = client.get("/v1/reference/brokers?q=acme", headers=firms.headers("viewer")).json()
    assert by_name["count"] == 2
    in_state = client.get("/v1/reference/brokers?q=acme%20fb&state=fl", headers=firms.headers("viewer")).json()
    assert [item["dot_number"] for item in in_state["items"]] == ["888"]
    assert client.get("/v1/reference/brokers?q=a.*", headers=firms.headers("viewer")).json()["count"] == 0
    for bad in ("", "?q=ab", "?state=TX"):
        response = client.get(f"/v1/reference/brokers{bad}", headers=firms.headers("viewer"))
        assert response.status_code == 422, bad
    assert client.get("/v1/reference/brokers?mc=1").status_code == 401
