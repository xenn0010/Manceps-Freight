"""Regression tests for the WP1.1-1.3 review findings on firm data: consent, broker vetting, numbers, portal links."""

from __future__ import annotations

from typing import Any

import pytest
from authkit import bearer, firm_db, one, platform
from bson import ObjectId
from conftest import START, TENANT_A, FakeClock
from datakit import CARRIER, CARRIER_PHONE, created, error_code, seed_firms
from fastapi.testclient import TestClient
from test_brokers import FMCSA_KEY, GOOD_AUTHORITY, GOOD_CARRIER, FakeTransport, _rdap  # pyright: ignore[reportPrivateUsage]

from manceps_core.brokers.check import LookupFailed, run_check
from manceps_core.brokers.reference import REFERENCE_DB
from manceps_core.indexes import ensure_firm_indexes
from manceps_core.mongo import Doc, MongoClientT, MongoDb
from manceps_core.repo import brokers, carriers, consent, contacts
from manceps_core.repo.errors import Invalid
from manceps_core.repo.store import WriteContext, insert

NEW_PHONE = "+14695550111"
METHOD = "signed dispatch agreement 2026-10-24"
OWNER_CTX = WriteContext(who={"kind": "user", "id": "usr_test"})
SHELL_MC = "999999"
REAL_DOT = "777"


def _grant(client: TestClient, headers: dict[str, str], path: str, channel: str) -> Any:
    """Record a consent grant through the API.

    Args:
        client: Test client.
        headers: Auth headers.
        path: Consent collection path.
        channel: Channel.

    Returns:
        The response.
    """
    return client.post(path, json={"channel": channel, "method": METHOD}, headers=headers)


def _ledger(db: MongoDb, subject_id: str) -> list[Doc]:
    """Return a subject's ledger rows in write order.

    Args:
        db: Firm database.
        subject_id: Subject id text.

    Returns:
        The rows.
    """
    return list(db["consent_events"].find({"subject.id": subject_id}).sort([("version", 1), ("_id", 1)]))


def test_f1_carrier_phone_change_revokes_consent(client: TestClient, mongo_client: MongoClientT,
                                                 clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    carrier = created(client, firms.headers("owner"), "/v1/carriers", CARRIER)
    path = f"/v1/carriers/{carrier['id']}/consent"
    for channel in ("sms", "voice"):
        assert _grant(client, firms.headers("owner"), path, channel).status_code == 200
    patched = client.patch(f"/v1/carriers/{carrier['id']}", json={"phone": "(469) 555-0111"},
                           headers=firms.headers("dispatcher"))
    assert patched.status_code == 200, patched.text
    assert patched.json()["phone"] == NEW_PHONE and patched.json()["consent"] is None
    db = firm_db(mongo_client, TENANT_A)
    stored = one(db, "carriers", {"phone": NEW_PHONE})
    assert stored.get("consent") is None
    revokes = [row for row in _ledger(db, carrier["id"]) if row["action"] == "revoked"]
    assert sorted(row["channel"] for row in revokes) == ["sms", "voice"]
    assert {row["method"] for row in revokes} == {"phone_changed"}
    assert {row["subject"]["phone"] for row in revokes} == {CARRIER_PHONE}
    regrant = _grant(client, firms.headers("owner"), path, "sms")
    assert regrant.json()["consent"]["sms"] is True and regrant.json()["consent"]["voice"] is False
    assert _ledger(db, carrier["id"])[-1]["subject"]["phone"] == NEW_PHONE


def test_f1_driver_phone_change_revokes_consent(client: TestClient, mongo_client: MongoClientT,
                                                clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    carrier = created(client, firms.headers("dispatcher"), "/v1/carriers", CARRIER)
    driver = created(client, firms.headers("dispatcher"), "/v1/drivers",
                     {"carrier_id": carrier["id"], "name": "Sam", "phone": "214-555-0500"})
    db = firm_db(mongo_client, TENANT_A)
    consent.record_consent(db, OWNER_CTX, "driver", driver["id"], "whatsapp", consent.GRANTED, METHOD)
    assert one(db, "drivers", {"_id": ObjectId(driver["id"])})["consent"]["whatsapp"] is True
    patched = client.patch(f"/v1/drivers/{driver['id']}", json={"phone": None}, headers=firms.headers("dispatcher"))
    assert patched.status_code == 200, patched.text
    assert one(db, "drivers", {"_id": ObjectId(driver["id"])}).get("consent") is None
    last = _ledger(db, driver["id"])[-1]
    assert (last["channel"], last["action"], last["method"]) == ("whatsapp", "revoked", "phone_changed")
    assert last["subject"]["phone"] == "+12145550500"


def test_f1_cache_ignores_grants_for_another_number() -> None:
    rows: list[Doc] = [{"_id": ObjectId(), "version": 1, "at": START, "channel": "sms", "action": "granted",
                        "method": METHOD, "subject": {"type": "carrier", "id": "x", "phone": CARRIER_PHONE}}]
    cache = consent.cache_for_phone(rows, CARRIER_PHONE)
    assert cache is not None and cache["sms"] is True
    assert consent.cache_for_phone(rows, NEW_PHONE) is None


def _bonded_reference(mongo_client: MongoClientT) -> MongoDb:
    """Load a complete bond table holding an active bond for DOT 777 only.

    Args:
        mongo_client: Database client.

    Returns:
        The reference database.
    """
    db = mongo_client[REFERENCE_DB]
    db["sync_meta"].insert_one({"_id": "broker_bonds", "complete": True, "source_updated": "2026-10-20"})
    db["broker_bonds"].insert_one({"_id": "b1", "mc_number": "123456", "dot_number": REAL_DOT, "form_name": "BMC-84",
                                   "surety": "ACME SURETY", "cancellation_effective_date": None})
    return db


def _statuses(result: dict[str, Any]) -> dict[str, str]:
    """Map check names to statuses.

    Args:
        result: run_check output.

    Returns:
        Check name to status.
    """
    return {str(check["check"]): str(check["status"]) for check in result["checks"]}


def _docket(dot: int) -> dict[str, Any]:
    """Build a docket-number response whose record carries a DOT.

    Args:
        dot: The record's DOT number.

    Returns:
        FMCSA JSON.
    """
    return {"content": [{"carrier": {"dotNumber": dot, "allowedToOperate": "Y", "legalName": "SHELL CO"}}]}


def test_f2_mc_and_dot_of_different_entities_is_do_not_book(mongo_client: MongoClientT) -> None:
    routes = {f"docket-number/{SHELL_MC}": _docket(555), "/authority": GOOD_AUTHORITY,
              f"carriers/{REAL_DOT}": GOOD_CARRIER, "carriers/555": GOOD_CARRIER}
    result = run_check(FakeTransport(routes), FMCSA_KEY, SHELL_MC, REAL_DOT, "", _bonded_reference(mongo_client),
                       START)
    statuses = _statuses(result)
    assert result["verdict"] == "do_not_book"
    assert statuses["mc_dot_match"] == "fail"
    mismatch = next(check for check in result["checks"] if check["check"] == "mc_dot_match")
    assert "different" in mismatch["detail"]


def test_f2_mc_without_docket_record_cannot_borrow_a_dot(mongo_client: MongoClientT) -> None:
    routes: dict[str, Any] = {f"docket-number/{SHELL_MC}": {"content": []}, "/authority": GOOD_AUTHORITY,
              f"carriers/{REAL_DOT}": GOOD_CARRIER}
    result = run_check(FakeTransport(routes), FMCSA_KEY, SHELL_MC, REAL_DOT, "", _bonded_reference(mongo_client),
                       START)
    assert result["verdict"] == "do_not_book"
    assert _statuses(result)["bond"] != "pass"


def test_f2_dot_only_check_is_never_looks_ok(mongo_client: MongoClientT) -> None:
    routes = {"/authority": GOOD_AUTHORITY, f"carriers/{REAL_DOT}": GOOD_CARRIER, "rdap.org": _rdap(2000)}
    result = run_check(FakeTransport(routes), FMCSA_KEY, "", REAL_DOT, "ops@acme.com",
                       _bonded_reference(mongo_client), START)
    statuses = _statuses(result)
    assert statuses["fmcsa_operating"] == statuses["broker_authority"] == statuses["bond"] == "pass"
    assert statuses["mc_dot_match"] == "unknown" and result["verdict"] == "review"


def test_f2_matching_mc_and_dot_still_look_ok(mongo_client: MongoClientT) -> None:
    routes = {"docket-number/123456": _docket(777), "/authority": GOOD_AUTHORITY, "rdap.org": _rdap(2000)}
    result = run_check(FakeTransport(routes), FMCSA_KEY, "123456", "0777", "ops@acme.com",
                       _bonded_reference(mongo_client), START)
    assert _statuses(result)["mc_dot_match"] == "pass" and result["verdict"] == "looks_ok"


@pytest.mark.parametrize("email", ["ops@acme.com", "not-an-email"])
def test_f3_unknown_check_caps_verdict_at_review(mongo_client: MongoClientT, email: str) -> None:
    routes = {"docket-number/123456": _docket(777), "/authority": GOOD_AUTHORITY, "rdap.org": LookupFailed("down")}
    transport = FakeTransport(routes, dns_failure=True)
    result = run_check(transport, FMCSA_KEY, "123456", "", email, _bonded_reference(mongo_client), START)
    statuses = _statuses(result)
    assert statuses["fmcsa_operating"] == statuses["broker_authority"] == statuses["bond"] == "pass"
    assert "unknown" in statuses.values() and result["verdict"] == "review"


def test_f5_non_finite_numbers_are_422_and_write_nothing(client: TestClient, mongo_client: MongoClientT,
                                                        clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    db = firm_db(mongo_client, TENANT_A)
    audits = db["audit"].count_documents({})
    json_headers = {"Content-Type": "application/json"}
    bodies = [("/v1/carriers", '{"phone": "2145550300", "name": "X", "rate_floor_per_mile": 1e999}', "owner"),
              ("/v1/carriers", '{"phone": "2145550300", "name": "X", "dispatch_fee_pct": NaN}', "owner"),
              ("/v1/facilities", '{"name": "Dock", "location": {"lat": NaN, "lng": 0}}', "dispatcher"),
              ("/v1/facilities", '{"name": "Dock", "location": {"lat": 1, "lng": -Infinity}}', "dispatcher")]
    for path, body, role in bodies:
        response = client.post(path, content=body, headers={**firms.headers(role), **json_headers})
        assert response.status_code == 422, (path, body, response.text)
    assert db["carriers"].count_documents({}) == db["facilities"].count_documents({}) == 0
    assert db["audit"].count_documents({}) == audits


def test_f5_repo_rejects_non_finite_values_before_writing(mongo_client: MongoClientT) -> None:
    db = mongo_client["firm_apex_freight"]
    for value in (float("inf"), float("-inf"), float("nan")):
        with pytest.raises(Invalid):
            carriers.create_carrier(db, OWNER_CTX, {"phone": CARRIER_PHONE, "rate_floor_per_mile": value}, True)
        with pytest.raises(Invalid):
            contacts.create_record(db, OWNER_CTX, "facility", {"name": "Dock", "location": {"lat": value, "lng": 0}})
        with pytest.raises(Invalid):
            insert(db, OWNER_CTX, "notes", "note", {"text": "x", "weight": value})
    assert db["carriers"].count_documents({}) == db["facilities"].count_documents({}) == 0
    assert db["notes"].count_documents({}) == db["audit"].count_documents({}) == 0


def test_f11_consent_grant_needs_owner_revoke_is_immediate(client: TestClient, mongo_client: MongoClientT,
                                                           clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    carrier = created(client, firms.headers("dispatcher"), "/v1/carriers", CARRIER)
    path = f"/v1/carriers/{carrier['id']}/consent"
    refused = _grant(client, firms.headers("dispatcher"), path, "sms")
    assert refused.status_code == 409 and error_code(refused) == "approval_required"
    assert refused.json()["error"]["details"]["approval_kind"] == "carrier_terms_change"
    db = firm_db(mongo_client, TENANT_A)
    assert db["consent_events"].count_documents({}) == 0
    assert _grant(client, firms.headers("owner"), path, "sms").json()["consent"]["sms"] is True
    revoked = client.delete(f"{path}/sms", headers=firms.headers("dispatcher"))
    assert revoked.status_code == 200 and revoked.json()["consent"]["sms"] is False
    assert client.delete(f"{path}/voice", headers=firms.headers("owner")).status_code == 200


def test_f12_stale_cache_write_cannot_resurrect_revoked_consent(mongo_client: MongoClientT,
                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    db = mongo_client["firm_apex_freight"]
    ensure_firm_indexes(db)
    carrier = carriers.create_carrier(db, OWNER_CTX, {"phone": CARRIER_PHONE, "name": "X"}, True)
    real_ledger = consent._ledger  # pyright: ignore[reportPrivateUsage]
    state = {"interleaved": False}

    def stale_ledger(*args: Any, **kwargs: Any) -> list[Doc]:
        rows = real_ledger(*args, **kwargs)
        if not state["interleaved"]:
            state["interleaved"] = True  # request B revokes while request A still holds its grant-only snapshot
            consent.record_consent(db, OWNER_CTX, "carrier", carrier["_id"], "sms", consent.REVOKED, None)
        return rows

    monkeypatch.setattr(consent, "_ledger", stale_ledger)
    consent.record_consent(db, OWNER_CTX, "carrier", carrier["_id"], "sms", consent.GRANTED, METHOD)
    monkeypatch.undo()
    stored = one(db, "carriers", {"_id": carrier["_id"]})
    assert stored["consent"]["sms"] is False
    assert stored["consent"] == consent.cache_for_phone(_ledger(db, str(carrier["_id"])), CARRIER_PHONE)


def _link_and_token(client: TestClient, headers: dict[str, str], carrier_id: str) -> tuple[str, dict[str, str]]:
    """Create a carrier link and exchange it for a portal token.

    Args:
        client: Test client.
        headers: Dispatcher headers.
        carrier_id: Carrier id.

    Returns:
        (link token, portal auth headers).
    """
    link = created(client, headers, f"/v1/carriers/{carrier_id}/links", {})
    exchanged = client.post("/v1/auth/scoped/exchange", json={"token": link["token"]})
    assert exchanged.status_code == 200, exchanged.text
    return str(link["token"]), bearer(exchanged.json()["access_token"])


def test_f14_portal_rejects_suspended_firm(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    carrier = created(client, firms.headers("dispatcher"), "/v1/carriers", CARRIER)
    raw, portal = _link_and_token(client, firms.headers("dispatcher"), carrier["id"])
    platform(mongo_client)["firms"].update_one({"_id": TENANT_A}, {"$set": {"status": "suspended"}})
    assert client.get("/v1/portal/me", headers=portal).status_code == 401
    assert client.post("/v1/auth/scoped/exchange", json={"token": raw}).status_code == 401


@pytest.mark.parametrize("offboard", ["patch", "delete", "direct"])
def test_f14_offboarded_carrier_loses_portal_access(client: TestClient, mongo_client: MongoClientT,
                                                    clock: FakeClock, offboard: str) -> None:
    firms = seed_firms(client, mongo_client, clock)
    carrier = created(client, firms.headers("dispatcher"), "/v1/carriers", CARRIER)
    raw, portal = _link_and_token(client, firms.headers("dispatcher"), carrier["id"])
    path = f"/v1/carriers/{carrier['id']}"
    if offboard == "patch":
        assert client.patch(path, json={"status": "offboarded"}, headers=firms.headers("dispatcher")).status_code \
            == 200
    elif offboard == "delete":
        assert client.delete(path, headers=firms.headers("owner")).status_code == 204
    else:
        firm_db(mongo_client, TENANT_A)["carriers"].update_one({"_id": ObjectId(carrier["id"])},
                                                                {"$set": {"status": "offboarded"}})
    assert client.get("/v1/portal/me", headers=portal).status_code == 401
    assert client.post("/v1/auth/scoped/exchange", json={"token": raw}).status_code == 401
    if offboard != "direct":
        links = platform(mongo_client)["scoped_links"]
        assert links.count_documents({"subject.id": carrier["id"], "revoked_at": None}) == 0


def test_f16_broker_notes_keep_only_the_newest(client: TestClient, mongo_client: MongoClientT, clock: FakeClock,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    assert isinstance(brokers.MAX_NOTES_KEPT, int) and brokers.MAX_NOTES_KEPT > 0
    monkeypatch.setattr(brokers, "MAX_NOTES_KEPT", 3)
    firms = seed_firms(client, mongo_client, clock)
    created(client, firms.headers("dispatcher"), "/v1/brokers", {"mc_number": "123456"})
    for index in range(5):
        response = client.post("/v1/brokers/123456/notes", json={"text": f"note {index}"},
                               headers=firms.headers("dispatcher"))
        assert response.status_code == 201
    stored = one(firm_db(mongo_client, TENANT_A), "brokers", {"mc_number": "123456"})["notes"]
    assert [note["text"] for note in stored] == ["note 2", "note 3", "note 4"]
    assert all(set(note) == {"at", "text", "session_id", "by"} for note in stored)
