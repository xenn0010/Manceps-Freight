"""Carrier consent ledger (truth) with its cache, and scoped carrier links (create, exchange, revoke)."""

from __future__ import annotations

from typing import Any

from authkit import bearer, firm_db, one
from bson import ObjectId
from conftest import TENANT_A, FakeClock
from datakit import CARRIER, CARRIER_PHONE, created, error_code, seed_firms
from fastapi.testclient import TestClient

from manceps_core.mongo import MongoClientT
from manceps_core.repo import consent

METHOD = "signed dispatch agreement 2026-10-24"


def _grant(client: TestClient, headers: dict[str, str], carrier_id: str, channel: str) -> dict[str, Any]:
    """Grant consent on a channel and expect 200.

    Args:
        client: Test client.
        headers: Auth headers.
        carrier_id: Carrier id.
        channel: Channel.

    Returns:
        The carrier.
    """
    response = client.post(f"/v1/carriers/{carrier_id}/consent", json={"channel": channel, "method": METHOD,
                                                                      "evidence_ref": "doc_123"}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_consent_ledger_and_cache(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    carrier = created(client, firms.headers("dispatcher"), "/v1/carriers", CARRIER)
    _grant(client, firms.headers("owner"), carrier["id"], "sms")
    granted = _grant(client, firms.headers("owner"), carrier["id"], "voice")
    assert granted["consent"]["sms"] is True and granted["consent"]["voice"] is True
    assert granted["consent"]["whatsapp"] is False and granted["consent"]["method"] == METHOD
    revoked = client.delete(f"/v1/carriers/{carrier['id']}/consent/sms", headers=firms.headers("dispatcher"))
    assert revoked.status_code == 200 and revoked.json()["consent"]["sms"] is False
    db = firm_db(mongo_client, TENANT_A)
    ledger = list(db["consent_events"].find({}).sort([("_id", 1)]))
    assert [(row["channel"], row["action"]) for row in ledger] == [("sms", "granted"), ("voice", "granted"),
                                                                   ("sms", "revoked")]
    assert ledger[0]["subject"] == {"type": "carrier", "id": carrier["id"], "phone": CARRIER_PHONE}
    assert ledger[0]["evidence_ref"] == "doc_123" and ledger[0]["by"]["kind"] == "user"
    oid = ObjectId(carrier["id"])
    cached = one(db, "carriers", {"_id": oid})["consent"]
    assert cached == consent.cache_from_events(ledger)
    assert cached["voice"] is True and cached["sms"] is False
    db["carriers"].update_one({"_id": oid}, {"$set": {"consent": {"sms": True, "voice": True, "whatsapp": True,
                                                                  "method": "forged"}}})
    assert consent.rebuild_cache(db, "carrier", oid) == cached
    assert one(db, "carriers", {"_id": oid})["consent"] == cached
    events = [doc["event"] for doc in db["audit"].find({"ref.id": carrier["id"]})]
    assert events.count("carrier.consent_grant") == 2 and "carrier.consent_revoke" in events


def test_consent_requires_method(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    carrier = created(client, firms.headers("dispatcher"), "/v1/carriers", CARRIER)
    path = f"/v1/carriers/{carrier['id']}/consent"
    for body in ({"channel": "sms"}, {"channel": "sms", "method": "   "}, {"channel": "fax", "method": METHOD}):
        response = client.post(path, json=body, headers=firms.headers("owner"))
        assert response.status_code == 422, body
        assert error_code(response) == "validation_error"
    assert client.delete(f"{path}/fax", headers=firms.headers("dispatcher")).status_code == 422
    assert firm_db(mongo_client, TENANT_A)["consent_events"].count_documents({}) == 0
    assert client.post(path, json={"channel": "sms", "method": METHOD}).status_code == 401
    assert client.post(path, json={"channel": "sms", "method": METHOD},
                       headers=firms.headers("viewer")).status_code == 403
    assert client.delete(f"{path}/sms", headers=firms.headers("viewer")).status_code == 403
    assert client.post(path, json={"channel": "sms", "method": METHOD},
                       headers=firms.headers("owner_b")).status_code == 404
    assert client.delete(f"{path}/sms", headers=firms.headers("owner_b")).status_code == 404
    assert one(firm_db(mongo_client, TENANT_A), "carriers", {"_id": ObjectId(carrier["id"])}).get("consent") is None


def test_carrier_links_create_exchange_and_revoke(client: TestClient, mongo_client: MongoClientT,
                                                  clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    carrier = created(client, firms.headers("dispatcher"), "/v1/carriers", CARRIER)
    other = created(client, firms.headers("dispatcher"), "/v1/carriers", {"phone": "+12145550399", "name": "Other"})
    links = f"/v1/carriers/{carrier['id']}/links"
    link = created(client, firms.headers("dispatcher"), links, {"ttl_days": 7})
    assert str(link["token"]).startswith("mcl_") and str(link["id"]).startswith("lnk_")
    exchanged = client.post("/v1/auth/scoped/exchange", json={"token": link["token"]})
    assert exchanged.status_code == 200
    portal = bearer(exchanged.json()["access_token"])
    assert client.get("/v1/portal/me", headers=portal).json()["carrier_name"] == "Lone Wolf"
    assert client.post(links, json={"ttl_days": 0}, headers=firms.headers("dispatcher")).status_code == 422
    assert client.post(links, json={}, headers=firms.headers("viewer")).status_code == 403
    assert client.post(links, json={}).status_code == 401
    assert client.post(links, json={}, headers=firms.headers("owner_b")).status_code == 404
    default = client.post(links, headers=firms.headers("dispatcher"))
    assert default.status_code == 201 and default.json()["token"] != link["token"]
    wrong_carrier = f"/v1/carriers/{other['id']}/links/{link['id']}"
    assert client.delete(wrong_carrier, headers=firms.headers("dispatcher")).status_code == 404
    assert client.delete(f"{links}/{link['id']}", headers=firms.headers("owner_b")).status_code == 404
    assert client.delete(f"{links}/{link['id']}", headers=firms.headers("viewer")).status_code == 403
    assert client.delete(f"{links}/{link['id']}", headers=firms.headers("dispatcher")).status_code == 204
    assert client.delete(f"{links}/{link['id']}", headers=firms.headers("dispatcher")).status_code == 404
    assert client.get("/v1/portal/me", headers=portal).status_code == 401
    events = [doc["event"] for doc in firm_db(mongo_client, TENANT_A)["audit"].find({"ref.type": "scoped_link"})]
    assert events.count("carrier.link_create") == 2 and "carrier.link_revoke" in events
