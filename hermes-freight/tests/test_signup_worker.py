"""Signup worker: claims queued signups from Atlas and provisions each firm exactly once."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import mongomock
import pytest
from pymongo.database import Database

SCRIPT = Path(__file__).resolve().parent.parent / "deploy" / "signup_worker.py"
NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("signup_worker", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


worker = _load()


@pytest.fixture
def db() -> Database:
    database = mongomock.MongoClient(tz_aware=True)[worker.PLATFORM_DB]
    worker.ensure_indexes(database)
    return database


def _queue(db: Database, token: str, firm: str, phone: str, **extra: Any) -> None:
    db[worker.SIGNUPS].insert_one({"_id": token, "phone": phone, "firm_name": firm, "status": "pending",
                                   "attempts": 0, "created_at": NOW - timedelta(minutes=1), **extra})


class _Provisioner:
    def __init__(self, fail_with: Exception | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail_with = fail_with

    def __call__(self, tenant_id: str, phone: str) -> None:
        self.calls.append((tenant_id, phone))
        if self.fail_with:
            raise self.fail_with


def _never_taken(tenant_id: str) -> bool:
    return False


@pytest.mark.parametrize(("name", "slug"), [
    ("Apex Freight LLC", "apex-freight-llc"),
    ("  Carlos & Sons Trucking!! ", "carlos-sons-trucking"),
    ("123 Haulers", "firm-123-haulers"),
    ("!!!", "firm"),
])
def test_slugify(name: str, slug: str) -> None:
    assert worker.slugify(name) == slug


def test_slugify_long_name_stays_valid() -> None:
    slug = worker.slugify("The Extremely Long Name Of A Dispatch Company Incorporated")
    assert len(slug) <= 32 and not slug.endswith("-")
    worker.tenant.validate_tenant_id(slug)


def test_pending_signup_is_provisioned(db: Database) -> None:
    _queue(db, "tok1", "Apex Freight", "+12405550100")
    run = _Provisioner()
    assert worker.process_one(db, run, _never_taken, now=NOW) == "tok1"
    doc = db[worker.SIGNUPS].find_one({"_id": "tok1"})
    assert doc["status"] == "ready" and doc["tenant_id"] == "apex-freight"
    assert run.calls == [("apex-freight", "+12405550100")]


def test_taken_tenant_id_gets_suffix(db: Database) -> None:
    _queue(db, "tok1", "Apex Freight", "+12405550100")
    worker.process_one(db, _Provisioner(), lambda tid: tid == "apex-freight", now=NOW)
    assert db[worker.SIGNUPS].find_one({"_id": "tok1"})["tenant_id"] == "apex-freight-2"


def test_two_signups_same_name_get_distinct_ids(db: Database) -> None:
    _queue(db, "tok1", "Apex Freight", "+12405550100")
    _queue(db, "tok2", "Apex Freight", "+12405550101")
    run = _Provisioner()
    worker.process_one(db, run, _never_taken, now=NOW)
    worker.process_one(db, run, _never_taken, now=NOW)
    assert sorted(tid for tid, _ in run.calls) == ["apex-freight", "apex-freight-2"]


def test_failure_requeues_then_gives_up(db: Database) -> None:
    _queue(db, "tok1", "Apex Freight", "+12405550100")
    run = _Provisioner(fail_with=RuntimeError("atlas down"))
    for attempt in range(1, worker.MAX_ATTEMPTS + 1):
        worker.process_one(db, run, _never_taken, now=NOW)
        doc = db[worker.SIGNUPS].find_one({"_id": "tok1"})
        assert doc["attempts"] == attempt and "atlas down" in doc["error"]
    assert doc["status"] == "failed"
    assert worker.process_one(db, run, _never_taken, now=NOW) is None


def test_empty_queue_returns_none(db: Database) -> None:
    assert worker.process_one(db, _Provisioner(), _never_taken, now=NOW) is None


def test_fresh_claim_is_not_taken_twice(db: Database) -> None:
    _queue(db, "tok1", "Apex Freight", "+12405550100", status="provisioning", claimed_at=NOW)
    assert worker.process_one(db, _Provisioner(), _never_taken, now=NOW) is None


def test_stale_claim_is_recovered(db: Database) -> None:
    stale = NOW - worker.STALE_CLAIM - timedelta(seconds=1)
    _queue(db, "tok1", "Apex Freight", "+12405550100", status="provisioning", claimed_at=stale)
    assert worker.process_one(db, _Provisioner(), _never_taken, now=NOW) == "tok1"
    assert db[worker.SIGNUPS].find_one({"_id": "tok1"})["status"] == "ready"
