"""The commit job without the worker loop: exactly-once rows across crashes, leases, and failure handling."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from authkit import firm_db, platform
from bson import ObjectId
from conftest import TENANT_A, FakeClock
from datakit import seed_firms
from fastapi.testclient import TestClient
from importkit import commit, csv_bytes, uploaded

from manceps_api.imports import commit as commit_job
from manceps_core.mongo import MongoClientT, MongoDb
from manceps_core.tenancy import TenantDb
from manceps_worker.runner import run_pass

ROWS = 12
CRASH_AFTER = 3


class Crash(RuntimeError):
    """Injected worker crash."""


def _queued(client: TestClient, mongo_client: MongoClientT, clock: FakeClock, entity: str = "carriers",
            content: bytes | None = None) -> tuple[MongoDb, ObjectId]:
    """Upload a file and request its commit.

    Args:
        client: Test client.
        mongo_client: Client.
        clock: Fake clock.
        entity: Entity name.
        content: File bytes (12 carriers by default).

    Returns:
        (firm database, import id).
    """
    firms = seed_firms(client, mongo_client, clock)
    owner = firms.headers("owner")
    rows = [[f"C{index}", f"21455507{index:02d}"] for index in range(ROWS)]
    body = uploaded(client, owner, entity, "rows.csv", content or csv_bytes(("Name", "Phone"), rows))
    assert commit(client, owner, body["id"]).status_code == 202
    return firm_db(mongo_client, TENANT_A), ObjectId(body["id"])


def test_crash_after_write_before_outcome_resumes_exactly_once(client: TestClient, mongo_client: MongoClientT,
                                                               clock: FakeClock,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    db, import_id = _queued(client, mongo_client, clock)
    real = commit_job.record_outcome
    calls = {"count": 0}

    def crashing(*args: Any, **kwargs: Any) -> None:
        calls["count"] += 1
        if calls["count"] == CRASH_AFTER:
            raise Crash("worker died after writing the row")
        real(*args, **kwargs)

    monkeypatch.setattr(commit_job, "record_outcome", crashing)
    with pytest.raises(Crash):
        commit_job.commit_import(db, import_id, clock, "worker-1")
    assert db["carriers"].count_documents({}) == CRASH_AFTER
    monkeypatch.setattr(commit_job, "record_outcome", real)
    assert commit_job.commit_import(db, import_id, clock, "worker-2") is False
    clock.advance(commit_job.LEASE + timedelta(seconds=1))
    assert commit_job.commit_import(db, import_id, clock, "worker-2") is True
    assert db["carriers"].count_documents({}) == ROWS
    doc = db["imports"].find_one({"_id": import_id})
    assert doc is not None and doc["status"] == "committed" and doc["stats"]["created"] == ROWS
    assert commit_job.commit_import(db, import_id, clock, "worker-3") is False


def test_update_resume_reuses_the_first_before_snapshot(client: TestClient, mongo_client: MongoClientT,
                                                        clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> None:
    firms = seed_firms(client, mongo_client, clock)
    owner = firms.headers("owner")
    assert client.post("/v1/carriers", json={"phone": "2145550700", "name": "Original"},
                       headers=owner).status_code == 201
    body = uploaded(client, owner, "carriers", "u.csv", csv_bytes(("Name", "Phone"), [["Changed", "2145550700"]]))
    assert commit(client, owner, body["id"]).status_code == 202
    db, import_id = firm_db(mongo_client, TENANT_A), ObjectId(body["id"])
    real = commit_job.record_outcome

    def crashing(*_args: Any, **_kwargs: Any) -> None:
        raise Crash("died")

    monkeypatch.setattr(commit_job, "record_outcome", crashing)
    with pytest.raises(Crash):
        commit_job.commit_import(db, import_id, clock, "worker-1")
    monkeypatch.setattr(commit_job, "record_outcome", real)
    clock.advance(commit_job.LEASE + timedelta(seconds=1))
    assert commit_job.commit_import(db, import_id, clock, "worker-2") is True
    row = db["import_rows"].find_one({"import_id": import_id})
    assert row is not None and row["before"]["name"] == "Original" and row["outcome"]["action"] == "updated"


def test_unknown_or_unqueued_import_is_a_no_op(client: TestClient, mongo_client: MongoClientT,
                                               clock: FakeClock) -> None:
    db, import_id = _queued(client, mongo_client, clock)
    assert commit_job.commit_import(db, ObjectId(), clock, "w") is False
    assert commit_job.commit_import(db, import_id, clock, "w") is True
    assert commit_job.commit_import(db, import_id, clock, "w") is False


def test_record_vanishing_mid_commit_is_reported(client: TestClient, mongo_client: MongoClientT,
                                                 clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    owner = firms.headers("owner")
    made = client.post("/v1/carriers", json={"phone": "2145550700", "name": "Original"}, headers=owner).json()
    body = uploaded(client, owner, "carriers", "u.csv", csv_bytes(("Name", "Phone"), [["Changed", "2145550700"]]))
    assert commit(client, owner, body["id"]).status_code == 202
    db = firm_db(mongo_client, TENANT_A)
    db["carriers"].delete_one({"_id": ObjectId(made["id"])})
    assert commit_job.commit_import(db, ObjectId(body["id"]), clock, "w") is True
    doc = db["imports"].find_one({"_id": ObjectId(body["id"])})
    assert doc is not None and doc["stats"]["created"] == 1


def test_undo_states_and_hash_release(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    owner = firms.headers("owner")
    content = csv_bytes(("Name", "Phone"), [["A", "2145550700"]])
    body = uploaded(client, owner, "carriers", "a.csv", content)
    early = client.post(f"/v1/imports/{body['id']}/undo", headers=owner)
    assert early.status_code == 409 and early.json()["error"]["code"] == "import_not_committed"
    assert commit(client, owner, body["id"]).status_code == 202
    assert run_pass(platform(mongo_client), TenantDb(mongo_client), clock, None) == 1
    assert client.post(f"/v1/imports/{body['id']}/undo", headers=owner).status_code == 200
    again = commit(client, owner, body["id"])
    assert again.status_code == 409 and again.json()["error"]["code"] == "import_undone"
    fresh = uploaded(client, owner, "carriers", "a.csv", content)
    assert fresh["id"] != body["id"]


def test_poisoned_import_fails_after_max_attempts(client: TestClient, mongo_client: MongoClientT,
                                                  clock: FakeClock) -> None:
    db, import_id = _queued(client, mongo_client, clock)
    db["imports"].update_one({"_id": import_id}, {"$set": {"attempts": commit_job.MAX_ATTEMPTS}})
    assert commit_job.commit_import(db, import_id, clock, "w") is False
    doc = db["imports"].find_one({"_id": import_id})
    assert doc is not None and doc["status"] == "failed" and doc["error"] == "too_many_attempts"
    events = [event["data"]["status"] for event in db["events"].find({"type": "import.progress"})]
    assert events == ["failed"]
