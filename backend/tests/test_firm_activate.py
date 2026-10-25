"""Worker: `firm_activate` turns a ready signup into an active firm with an owner, idempotently."""

from __future__ import annotations

import threading

import pytest
from authkit import PHONE_NEW, firm_db, one, platform
from conftest import START, TENANT_A, FakeClock

from manceps_core import accounts
from manceps_core.indexes import FIRM_INDEXES
from manceps_core.mongo import Doc, MongoClientT
from manceps_core.tenancy import TenantDb
from manceps_worker import runner
from manceps_worker.firm_activate import firm_activate


def _ready_signup(mongo_client: MongoClientT, clock: FakeClock, with_user: bool = True) -> Doc:
    """Insert a signup in the state the provisioning worker leaves it: ready with a tenant id.

    Args:
        mongo_client: In-memory client.
        clock: Fake clock.
        with_user: Link a user (rows from the old signup API have none).

    Returns:
        The signup document.
    """
    db = platform(mongo_client)
    signup: Doc = {"_id": "tok-1", "phone": PHONE_NEW, "firm_name": "Apex Freight", "status": "ready",
                   "tenant_id": TENANT_A, "attempts": 1, "created_at": clock()}
    if with_user:
        signup["user_id"] = accounts.create_user(db, clock(), phone=PHONE_NEW)["_id"]
    db["signups"].insert_one(signup)
    return signup


def test_firm_activate_idempotent(mongo_client: MongoClientT, clock: FakeClock) -> None:
    signup = _ready_signup(mongo_client, clock)
    db = platform(mongo_client)
    assert firm_activate(db, TenantDb(mongo_client), signup, clock) is True
    assert firm_activate(db, TenantDb(mongo_client), signup, clock) is False
    firm = db["firms"].find_one({"_id": TENANT_A})
    assert firm == {"_id": TENANT_A, "name": "Apex Freight", "slug": TENANT_A, "status": "active", "plan": "trial",
                    "timezone": "America/Chicago", "owner_user_id": signup["user_id"], "created_at": START,
                    "signup_id": "tok-1"}
    memberships = list(db["memberships"].find({"tenant_id": TENANT_A}))
    assert len(memberships) == 1
    assert memberships[0]["role"] == "owner" and memberships[0]["user_id"] == signup["user_id"]
    tenant = firm_db(mongo_client, TENANT_A)
    for collection, specs in FIRM_INDEXES.items():
        names = set(tenant[collection].index_information())
        assert {spec.name for spec in specs} <= names, collection
    assert tenant["audit"].count_documents({"event": "firm.activated"}) == 1
    assert one(db, "signups", {"_id": "tok-1"})["activated_at"] == START


def test_firm_activate_legacy_signup_creates_user(mongo_client: MongoClientT, clock: FakeClock) -> None:
    signup = _ready_signup(mongo_client, clock, with_user=False)
    db = platform(mongo_client)
    assert firm_activate(db, TenantDb(mongo_client), signup, clock) is True
    user = db["users"].find_one({"phone": PHONE_NEW})
    assert user is not None
    assert one(db, "firms", {"_id": TENANT_A})["owner_user_id"] == user["_id"]


def test_firm_activate_rejects_bad_signup(mongo_client: MongoClientT, clock: FakeClock) -> None:
    db = platform(mongo_client)
    with pytest.raises(ValueError, match="not ready"):
        firm_activate(db, TenantDb(mongo_client), {"_id": "x", "status": "pending", "phone": PHONE_NEW}, clock)
    with pytest.raises(ValueError, match="tenant"):
        firm_activate(db, TenantDb(mongo_client), {"_id": "x", "status": "ready", "phone": PHONE_NEW,
                                                   "tenant_id": "Bad Id"}, clock)


def test_runner_processes_only_unactivated(mongo_client: MongoClientT, clock: FakeClock) -> None:
    _ready_signup(mongo_client, clock)
    db = platform(mongo_client)
    db["signups"].insert_one({"_id": "tok-2", "phone": "+12145550188", "firm_name": "Pending",
                              "status": "pending", "attempts": 0, "created_at": clock()})
    assert runner.run_once(db, TenantDb(mongo_client), clock) == 1
    assert runner.run_once(db, TenantDb(mongo_client), clock) == 0
    assert db["firms"].count_documents({}) == 1


def test_runner_survives_handler_failure(mongo_client: MongoClientT, clock: FakeClock,
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    _ready_signup(mongo_client, clock)
    db = platform(mongo_client)

    def explode(*_args: object) -> bool:
        raise RuntimeError("boom")

    monkeypatch.setattr(runner, "firm_activate", explode)
    assert runner.run_once(db, TenantDb(mongo_client), clock) == 0
    assert one(db, "signups", {"_id": "tok-1"})["activation_error"] == "RuntimeError"


def test_runner_loop_stops(mongo_client: MongoClientT, clock: FakeClock) -> None:
    _ready_signup(mongo_client, clock)
    stop = threading.Event()
    calls: list[int] = []

    def tick(count: int) -> None:
        calls.append(count)
        stop.set()

    runner.run_loop(platform(mongo_client), TenantDb(mongo_client), clock, stop, poll_seconds=0.01, on_tick=tick)
    assert calls == [1]


def test_runner_main_requires_database() -> None:
    with pytest.raises(RuntimeError, match="MONGODB_URI"):
        runner.main([])
