"""Repository rules called directly (the importer and the agent use these without HTTP)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from bson import ObjectId
from conftest import START, FakeClock

from manceps_core.indexes import ensure_firm_indexes
from manceps_core.mongo import MongoClientT, MongoDb
from manceps_core.repo import brokers, carriers, consent, fields
from manceps_core.repo.errors import Conflict, Invalid, NotFound
from manceps_core.repo.store import WriteContext

PHONE = "+12145550300"
TOO_MANY_TAGS = [f"tag_{index}" for index in range(fields.MAX_TAGS + 1)]
INVALID_CARRIER_CHANGES: list[dict[str, Any]] = [
    {"dispatch_fee_pct": True}, {"dispatch_fee_pct": "8"}, {"rate_floor_per_mile": 0}, {"agreement_signed": "yes"},
    {"preferred_lanes": "Dallas"}, {"preferred_lanes": ["Dallas"]}, {"preferred_lanes": [{}]},
    {"preferred_lanes": [{"origin": "A"}] * 51}, {"avoid": "TX"}, {"avoid": ["x"] * 51}, {"tags": TOO_MANY_TAGS},
    {"insurance_expires_at": datetime(2027, 1, 1)}, {"insurance_expires_at": "2027-01-01"}, {"unknown": 1},
    {"phone": None}, {"name": "x" * 201},
]


@pytest.fixture
def db(mongo_client: MongoClientT) -> MongoDb:
    """Return a firm database with its indexes.

    Args:
        mongo_client: In-memory client.

    Returns:
        The database.
    """
    firm = mongo_client["firm_repo_rules"]
    ensure_firm_indexes(firm)
    return firm


@pytest.fixture
def ctx(clock: FakeClock) -> WriteContext:
    """Return a writer for direct repository calls.

    Args:
        clock: Fake clock.

    Returns:
        The context.
    """
    return WriteContext(who={"kind": "system", "id": "import"}, clock=clock)


@pytest.mark.parametrize("changes", INVALID_CARRIER_CHANGES)
def test_carrier_validation_rules(changes: dict[str, Any]) -> None:
    with pytest.raises(Invalid) as caught:
        carriers.validate(changes)
    assert caught.value.code == "validation_error" and caught.value.details["errors"][0]["loc"][0] == "body"


def test_carrier_validation_normalizes() -> None:
    clean = carriers.validate({"preferred_lanes": [{"origin": " Dallas, TX ", "destination": None}],
                               "equipment": ["reefer", "reefer"], "avoid": ["NYC", " "], "notes": " ok ",
                               "insurance_expires_at": START, "dispatch_fee_pct": 8, "email": None})
    assert clean["preferred_lanes"] == [{"origin": "Dallas, TX", "destination": None}]
    assert clean["equipment"] == ["reefer"] and clean["avoid"] == ["NYC"] and clean["notes"] == "ok"
    assert clean["dispatch_fee_pct"] == 8.0 and clean["email"] is None


def test_carrier_repo_direct(db: MongoDb, ctx: WriteContext) -> None:
    with pytest.raises(Invalid):
        carriers.create_carrier(db, ctx, {"name": "no phone"}, allow_sensitive=True)
    with pytest.raises(Conflict) as approval:
        carriers.update_carrier(db, ctx, ObjectId(), {"agreement_signed": True}, allow_sensitive=False)
    assert approval.value.details == {"approval_kind": "carrier_terms_change", "fields": ["agreement_signed"]}
    carrier = carriers.create_carrier(db, ctx, {"phone": "214 555 0300", "agreement_signed": True}, True)
    assert carrier["status"] == "onboarding" and carrier["created_by"] == {"kind": "system", "id": "import"}
    with pytest.raises(Invalid):
        carriers.update_carrier(db, ctx, carrier["_id"], {}, allow_sensitive=True)
    with pytest.raises(NotFound):
        carriers.get_carrier(db, 12345)
    assert carriers.list_carriers(db, {"q": "nobody"}, None, 10) == []
    carriers.delete_carrier(db, ctx, carrier["_id"])
    with pytest.raises(NotFound):
        carriers.update_carrier(db, ctx, carrier["_id"], {"name": "x"}, True)


def test_consent_repo_rules(db: MongoDb, ctx: WriteContext) -> None:
    carrier = carriers.create_carrier(db, ctx, {"phone": PHONE}, True)
    with pytest.raises(Invalid):
        consent.record_consent(db, ctx, "carrier", carrier["_id"], "fax", consent.GRANTED, "signed")
    with pytest.raises(Invalid):
        consent.record_consent(db, ctx, "carrier", carrier["_id"], "sms", consent.GRANTED, None)
    revoked = consent.record_consent(db, ctx, "carrier", carrier["_id"], "sms", consent.REVOKED, None)
    assert revoked["consent"]["method"] == consent.REVOKE_METHOD and revoked["consent"]["sms"] is False
    assert consent.cache_from_events([]) is None
    db["consent_events"].delete_many({})
    assert consent.rebuild_cache(db, "carrier", carrier["_id"]) is None
    stored = db["carriers"].find_one({"_id": carrier["_id"]})
    assert stored is not None and "consent" not in stored
    assert db["audit"].count_documents({"event": "carrier.consent_rebuild"}) == 1
    assert consent.rebuild_cache(db, "carrier", carrier["_id"]) is None
    assert db["audit"].count_documents({"event": "carrier.consent_rebuild"}) == 1


def test_broker_repo_rules(db: MongoDb, ctx: WriteContext) -> None:
    with pytest.raises(Invalid):
        brokers.create_broker(db, ctx, {"company": "No MC"})
    broker = brokers.create_broker(db, ctx, {"mc_number": "MC-777", "company": "Acme", "payment_terms": None})
    for changes in ({}, {"mc_number": "1"}, {"unknown": 1}):
        with pytest.raises(Invalid):
            brokers.update_broker(db, ctx, "777", changes)
    assert brokers.update_broker(db, ctx, "777", {"company": None}).get("company") is None
    with pytest.raises(NotFound):
        brokers.get_broker(db, "MC-")
    with pytest.raises(Invalid):
        brokers.add_note(db, ctx, "777", " ")
    assert brokers.list_brokers(db, {"q": "777"}, None, 10)[0]["_id"] == broker["_id"]
    assert brokers.list_checks(db, "777", ObjectId(), 10) == []
    assert brokers.latest_check(db, "777") is None


def test_field_rules() -> None:
    assert fields.parse_id(oid := ObjectId(), "carrier") == oid
    assert fields.text("x", None) is None and fields.text_list("x", None) == []
    for call in (lambda: fields.text_list("x", "abc"), lambda: fields.aware_datetime("x", START.replace(tzinfo=None)),
                 lambda: fields.state("x", "T1"), lambda: fields.choice("x", "z", ("a",)),
                 lambda: fields.email("x", "nope"), lambda: fields.digits("x", None)):
        with pytest.raises(Invalid):
            call()
    assert fields.phones("x", ["2145550300", "+1 214 555 0300"]) == [PHONE]
    assert fields.contains("a.b") == {"$regex": "a\\.b", "$options": "i"}
