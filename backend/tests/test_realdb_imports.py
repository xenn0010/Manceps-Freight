"""Imports against a real MongoDB (META gate 8): concurrent commits, concurrent uploads, the undo window.

These run only with MONGODB_TEST_URI set (marker `realdb`).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import timedelta

import httpx2
import pytest
from authkit import firm_db
from bson import ObjectId
from conftest import TENANT_A, FakeClock
from datakit import seed_firms
from fastapi.testclient import TestClient
from importkit import commit, csv_bytes, fresh_owner, upload, uploaded

from manceps_api.errors import ApiError
from manceps_api.imports import commit as commit_job
from manceps_api.imports import undo as undo_job
from manceps_core.mongo import MongoClientT
from manceps_core.repo.store import WriteContext

pytestmark = pytest.mark.realdb

THREADS = 6
ROWS = 60
ROUNDS = 3


def _run_threads(count: int, work: Callable[[int], object]) -> tuple[list[object], list[BaseException]]:
    """Run work in threads released together by a barrier.

    Args:
        count: Number of threads.
        work: Function of the thread index.

    Returns:
        (results, errors).
    """
    barrier = threading.Barrier(count)
    results: list[object] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def runner(index: int) -> None:
        barrier.wait()
        try:
            outcome = work(index)
        except BaseException as exc:  # noqa: BLE001  # reported to the main thread
            with lock:
                errors.append(exc)
            return
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=runner, args=(index,)) for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results, errors


def _rows(round_no: int) -> bytes:
    """Build a carrier CSV unique to one round.

    Args:
        round_no: Round number.

    Returns:
        CSV bytes.
    """
    return csv_bytes(("Name", "Phone"), [[f"R{round_no}-{index}", f"214{round_no + 5}55{index:04d}"]
                                         for index in range(ROWS)])


def test_concurrent_commits_create_each_row_once(client: TestClient, mongo_client: MongoClientT,
                                                 clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    owner = firms.headers("owner")
    db = firm_db(mongo_client, TENANT_A)
    for round_no in range(ROUNDS):
        body = uploaded(client, owner, "carriers", f"r{round_no}.csv", _rows(round_no))
        assert commit(client, owner, body["id"]).status_code == 202
        import_id = ObjectId(body["id"])
        results, errors = _run_threads(THREADS, lambda index, iid=import_id: commit_job.commit_import(
            db, iid, clock, f"worker-{index}"))
        assert errors == []
        assert results.count(True) == 1
        doc = db["imports"].find_one({"_id": import_id})
        assert doc is not None and doc["status"] == "committed" and doc["stats"]["created"] == ROWS
    assert db["carriers"].count_documents({}) == ROWS * ROUNDS


def test_concurrent_identical_uploads_make_one_import(client: TestClient, mongo_client: MongoClientT,
                                                      clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    owner = firms.headers("owner")
    content = _rows(0)
    results, errors = _run_threads(THREADS, lambda _index: upload(client, owner, "carriers", "same.csv", content))
    assert errors == []
    statuses = sorted(response.status_code for response in results if isinstance(response, httpx2.Response))
    assert statuses.count(201) == 1 and statuses.count(200) == THREADS - 1
    db = firm_db(mongo_client, TENANT_A)
    assert db["imports"].count_documents({}) == 1
    assert db["import_rows"].count_documents({}) == ROWS


def test_undo_window_and_single_undo(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    owner = firms.headers("owner")
    db = firm_db(mongo_client, TENANT_A)
    late = uploaded(client, owner, "carriers", "late.csv", _rows(1))
    assert commit(client, owner, late["id"]).status_code == 202
    assert commit_job.commit_import(db, ObjectId(late["id"]), clock, "w") is True
    clock.advance(timedelta(hours=25))
    owner = fresh_owner(client)
    refused = client.post(f"/v1/imports/{late['id']}/undo", headers=owner)
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "undo_window_closed"
    body = uploaded(client, owner, "carriers", "r.csv", _rows(2))
    assert commit(client, owner, body["id"]).status_code == 202
    assert commit_job.commit_import(db, ObjectId(body["id"]), clock, "w") is True
    clock.advance(timedelta(hours=23))
    ctx = WriteContext(who={"kind": "user", "id": "usr_realdb"}, clock=clock)

    def work(_index: int) -> str:
        try:
            return str(undo_job.undo_import(db, ctx, ObjectId(body["id"]), clock)["status"])
        except ApiError as exc:
            return exc.code

    results, errors = _run_threads(THREADS, work)
    assert errors == []
    assert results.count("undone") == 1 and set(results) <= {"undone", "undo_in_progress", "already_undone"}
    assert db["carriers"].count_documents({"name": {"$regex": "^R2-"}}) == 0
    assert db["carriers"].count_documents({"name": {"$regex": "^R1-"}}) == ROWS
