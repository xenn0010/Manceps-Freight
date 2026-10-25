"""Real-MongoDB checks for loads, approvals and events: races that must book once, unique refs, indexed reads."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from authkit import firm_db
from conftest import (
    MONGODB_TEST_URI,
    TENANT_A,
    FakeClock,
    IsolatedMongoClient,
    drop_prefixed,
    make_principal,
    new_prefix,
)
from fastapi.testclient import TestClient
from loadkit import move, new_load, propose, seed_fleet
from test_realdb import FindRecorder, _plan_stages, _run_threads  # pyright: ignore[reportPrivateUsage]

from manceps_core.approvals import service
from manceps_core.mongo import MongoClientT
from manceps_core.repo import loads
from manceps_core.repo.errors import Conflict
from manceps_core.repo.store import WriteContext

pytestmark = pytest.mark.realdb

THREADS = 8
EXPLAIN_KEYS = ("filter", "sort", "projection", "limit", "skip", "hint")
MIN_EXPLAINED_FINDS = 12
CTX = WriteContext(who={"kind": "user", "id": "usr_realdb"})


@pytest.fixture
def recorder() -> FindRecorder:
    """Return a find recorder.

    Returns:
        The recorder.
    """
    return FindRecorder()


@pytest.fixture
def mongo_client(recorder: FindRecorder) -> Iterator[IsolatedMongoClient]:
    """An isolated real client that records find commands.

    Args:
        recorder: Find recorder.

    Yields:
        The client.
    """
    prefix = new_prefix()
    client = IsolatedMongoClient(MONGODB_TEST_URI, prefix, event_listeners=[recorder])
    try:
        yield client
    finally:
        client.close()
        drop_prefixed(prefix)


def test_concurrent_decisions_book_exactly_once(client: TestClient, mongo_client: MongoClientT,
                                                clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    load = new_load(client, fleet)
    move(client, fleet, load["id"], "evaluating")
    approval = propose(client, fleet, "accept_rate", load["id"], {"rate_cents": 70_000})
    db = firm_db(mongo_client, TENANT_A)
    owner = make_principal(TENANT_A, role="owner", user_id="usr_owner")
    outcomes: list[str] = []

    def work(_index: int) -> None:
        try:
            doc = service.decide(db, CTX, approval["id"], owner, "approve", approval["payload_hash"], None)
            outcomes.append(str(doc["status"]))
        except Conflict as exc:
            outcomes.append(exc.code)

    assert _run_threads(THREADS, work) == []
    assert db["load_events"].count_documents({"type": "status_changed", "data.to": "booked"}) == 1
    stored = db["approvals"].find_one({"kind": "accept_rate"})
    assert stored is not None and stored["status"] == "applied"
    assert db["loads"].find_one({"ref": load["ref"]}, {"status": 1})["status"] == "booked"  # pyright: ignore[reportOptionalSubscript]
    assert set(outcomes) <= {"applied", "already_decided", "status_changed", "apply_failed"}


def test_load_refs_are_unique_under_threads(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    seed_fleet(client, mongo_client, clock)
    db = firm_db(mongo_client, TENANT_A)
    refs: list[str] = []
    assert _run_threads(THREADS, lambda _i: refs.append(str(loads.create_load(db, CTX, {})["ref"]))) == []
    assert len(set(refs)) == THREADS


def test_wp15_reads_use_an_index(client: TestClient, mongo_client: IsolatedMongoClient, clock: FakeClock,
                                 recorder: FindRecorder) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    load = new_load(client, fleet)
    move(client, fleet, load["id"], "evaluating")
    propose(client, fleet, "accept_rate", load["id"], {"rate_cents": 70_000})
    headers = fleet.firms.headers("owner")
    recorder.finds.clear()
    for path in ("/v1/loads", f"/v1/loads?status=evaluating&carrier_id={fleet.carrier}", f"/v1/loads?truck_id="
                 f"{fleet.truck}", "/v1/loads?broker_mc=123456", f"/v1/loads/{load['id']}/events", "/v1/loads/board",
                 "/v1/approvals", "/v1/approvals?status=pending", f"/v1/approvals?subject_id={load['id']}",
                 "/v1/approvals/stats", "/v1/board", "/v1/dashboard/summary", "/v1/events?after=0"):
        assert client.get(path, headers=headers).status_code == 200, path
    checked = 0
    for database, command in list(recorder.finds):
        name = database.removeprefix(mongo_client.prefix)
        if not name.startswith("firm_"):
            continue
        query = {"find": command["find"], **{key: command[key] for key in EXPLAIN_KEYS if key in command}}
        explained = mongo_client[name].command("explain", query, verbosity="queryPlanner")
        stages = set(_plan_stages(explained["queryPlanner"]["winningPlan"]))
        assert "COLLSCAN" not in stages, (name, query, stages)
        checked += 1
    assert checked >= MIN_EXPLAINED_FINDS
