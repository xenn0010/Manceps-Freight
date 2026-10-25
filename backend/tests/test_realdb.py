"""Real-MongoDB behavior mongomock cannot show (META gate 8): concurrency, TTL and unique indexes, query plans.

These tests run only with MONGODB_TEST_URI set (marker `realdb`); each uses its own prefixed databases.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from authkit import firm_db, platform
from bson import ObjectId
from conftest import MONGODB_TEST_URI, TENANT_A, FakeClock, IsolatedMongoClient, drop_prefixed, new_prefix
from datakit import CARRIER, created, seed_firms
from fastapi.testclient import TestClient
from pymongo import monitoring
from pymongo.errors import DuplicateKeyError

from manceps_api.errors import ApiError
from manceps_api.routes import members as members_routes
from manceps_core import accounts
from manceps_core.counters import next_value
from manceps_core.indexes import FIRM_INDEXES, PLATFORM_INDEXES, ensure_firm_indexes, ensure_platform_indexes
from manceps_core.mongo import Doc, MongoClientT, MongoDb
from manceps_core.repo import carriers, consent, fleet
from manceps_core.repo.errors import Conflict
from manceps_core.repo.store import WriteContext
from manceps_core.tenancy import PlatformRepo

pytestmark = pytest.mark.realdb

THREADS = 8
INCREMENTS_PER_THREAD = 50
RACE_ROUNDS = 12
CONSENT_FLIPS = 8
PHONE = "+12145550300"
CTX = WriteContext(who={"kind": "user", "id": "usr_realdb"})
EXPLAIN_KEYS = ("filter", "sort", "projection", "limit", "skip", "hint")
MIN_EXPLAINED_FINDS = 15
TENANT_PLATFORM_COLLECTIONS = frozenset({"memberships", "invitations", "scoped_links", "idempotency_keys"})


class FindRecorder(monitoring.CommandListener):
    """Records every `find` command so its query plan can be explained afterwards."""

    def __init__(self) -> None:
        """Start empty."""
        self.finds: list[tuple[str, Doc]] = []
        self._lock = threading.Lock()

    def started(self, event: monitoring.CommandStartedEvent) -> None:
        """Keep find commands.

        Args:
            event: Command start.
        """
        if event.command_name == "find":
            with self._lock:
                self.finds.append((event.database_name, dict(event.command)))

    def succeeded(self, event: monitoring.CommandSucceededEvent) -> None:
        """Ignore completions.

        Args:
            event: Command success.
        """

    def failed(self, event: monitoring.CommandFailedEvent) -> None:
        """Ignore failures.

        Args:
            event: Command failure.
        """


@pytest.fixture
def recorder() -> FindRecorder:
    """Return the find recorder wired into this module's client.

    Returns:
        The recorder.
    """
    return FindRecorder()


@pytest.fixture
def mongo_client(recorder: FindRecorder) -> Iterator[IsolatedMongoClient]:
    """Override the shared fixture: an isolated real client that also records find commands.

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


def _run_threads(count: int, work: Callable[[int], None]) -> list[BaseException]:
    """Start threads behind a barrier so they really overlap, and collect their errors.

    Args:
        count: Number of threads.
        work: Function of the thread index.

    Returns:
        Exceptions raised in the threads.
    """
    barrier = threading.Barrier(count)
    errors: list[BaseException] = []

    def runner(index: int) -> None:
        barrier.wait()
        try:
            work(index)
        except BaseException as exc:  # noqa: BLE001  # reported to the main thread
            errors.append(exc)

    threads = [threading.Thread(target=runner, args=(index,)) for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return errors


def _firm(mongo_client: MongoClientT) -> MongoDb:
    """Return firm A's database with its indexes.

    Args:
        mongo_client: Client.

    Returns:
        The database.
    """
    db = firm_db(mongo_client, TENANT_A)
    ensure_firm_indexes(db)
    return db


def test_counters_are_atomic_under_threads(mongo_client: MongoClientT) -> None:
    db = _firm(mongo_client)
    seen: list[int] = []
    lock = threading.Lock()

    def work(_index: int) -> None:
        for _ in range(INCREMENTS_PER_THREAD):
            value = next_value(db, "loads_2026")
            with lock:
                seen.append(value)

    assert _run_threads(THREADS, work) == []
    assert sorted(seen) == list(range(1, THREADS * INCREMENTS_PER_THREAD + 1))


def test_ttl_unique_and_sparse_options_reach_the_server(mongo_client: MongoClientT) -> None:
    firm, plat = _firm(mongo_client), mongo_client["platform"]
    ensure_platform_indexes(plat)
    for db, specs in ((firm, FIRM_INDEXES), (plat, PLATFORM_INDEXES)):
        for collection, indexes in specs.items():
            info = db[collection].index_information()
            for spec in indexes:
                served = info[spec.name]
                assert served.get("expireAfterSeconds") == spec.expire_after_seconds, (collection, spec.name)
                assert bool(served.get("unique")) is spec.unique and bool(served.get("sparse")) is spec.sparse


def test_unique_indexes_and_phone_tombstones(mongo_client: MongoClientT) -> None:
    db = _firm(mongo_client)
    first = carriers.create_carrier(db, CTX, {"phone": PHONE, "name": "A"}, True)
    with pytest.raises(Conflict):
        carriers.create_carrier(db, CTX, {"phone": "(214) 555-0300", "name": "B"}, True)
    carriers.delete_carrier(db, CTX, first["_id"])
    second = carriers.create_carrier(db, CTX, {"phone": PHONE, "name": "B"}, True)
    carriers.delete_carrier(db, CTX, second["_id"])
    live = str(carriers.create_carrier(db, CTX, {"phone": PHONE, "name": "C"}, True)["_id"])
    assert db["carriers"].count_documents({"phone_deleted": PHONE}) == 2
    for name in ("No phone 1", "No phone 2"):
        fleet.create_driver(db, CTX, {"carrier_id": live, "name": name})
    fleet.create_driver(db, CTX, {"carrier_id": live, "name": "P", "phone": "214-555-0500"})
    with pytest.raises(Conflict):
        fleet.create_driver(db, CTX, {"carrier_id": live, "name": "Q", "phone": "2145550500"})
    vin = "1FUJGLDR5CLBP8834"
    fleet.create_truck(db, CTX, {"carrier_id": live, "unit": "1", "vin": vin})
    with pytest.raises(Conflict):
        fleet.create_truck(db, CTX, {"carrier_id": live, "unit": "2", "vin": vin})
    row = {"subject": {"type": "carrier", "id": "x"}, "version": 1}
    db["consent_events"].insert_one(dict(row))
    with pytest.raises(DuplicateKeyError):
        db["consent_events"].insert_one(dict(row))
    users = mongo_client["platform"]
    ensure_platform_indexes(users)
    accounts.create_user(users, CTX.now(), email="a@x.test")
    accounts.create_user(users, CTX.now(), email="b@x.test")
    with pytest.raises(DuplicateKeyError):
        accounts.create_user(users, CTX.now(), email="a@x.test")


def _owner_race(mongo_client: MongoClientT, clock: FakeClock, change: Callable[[PlatformRepo, Doc], None]) -> None:
    """Race two owners changing each other, many times, and check an owner always remains.

    Args:
        mongo_client: Client.
        clock: Fake clock.
        change: The concurrent change applied to each owner's membership.
    """
    db = platform(mongo_client)
    ensure_platform_indexes(db)
    repo = PlatformRepo(db, TENANT_A)
    for _round in range(RACE_ROUNDS):
        repo.delete_many("memberships", {})
        for user in ("usr_o1", "usr_o2"):
            repo.insert_one("memberships", {"user_id": user, "role": "owner", "status": "active",
                                            "created_at": clock(), "updated_at": clock()})
        owners = repo.find("memberships", {})
        outcomes: list[str] = []

        def work(index: int, members: list[Doc] = owners, results: list[str] = outcomes) -> None:
            try:
                change(repo, members[index])
                results.append("ok")
            except ApiError as exc:
                results.append(exc.code)

        assert _run_threads(2, work) == []
        left = repo.count_documents("memberships", {"role": "owner", "status": "active"})
        assert left >= 1 and left == 2 - outcomes.count("ok")
        assert set(outcomes) <= {"ok", "last_owner"}


def test_last_owner_removal_is_atomic(mongo_client: MongoClientT, clock: FakeClock) -> None:
    _owner_race(mongo_client, clock, lambda repo, member: members_routes.remove_membership(repo, member, clock()))


def test_last_owner_demotion_is_atomic(mongo_client: MongoClientT, clock: FakeClock) -> None:
    _owner_race(mongo_client, clock,
                lambda repo, member: members_routes.change_membership_role(repo, member, "viewer", clock()))


def test_consent_cache_matches_ledger_under_concurrent_writes(mongo_client: MongoClientT) -> None:
    db = _firm(mongo_client)
    carrier = carriers.create_carrier(db, CTX, {"phone": PHONE, "name": "X"}, True)

    def work(_index: int) -> None:
        for _ in range(CONSENT_FLIPS):
            consent.record_consent(db, CTX, "carrier", carrier["_id"], "sms", consent.GRANTED, "signed form")
            consent.record_consent(db, CTX, "carrier", carrier["_id"], "sms", consent.REVOKED, None)

    assert _run_threads(THREADS, work) == []
    ledger = list(db["consent_events"].find({"subject.id": str(carrier["_id"])}))
    assert sorted(row["version"] for row in ledger) == list(range(1, len(ledger) + 1))
    assert len(ledger) == THREADS * CONSENT_FLIPS * 2
    stored = db["carriers"].find_one({"_id": carrier["_id"]})
    assert stored is not None and stored["consent_version"] == len(ledger)
    assert stored["consent"] == consent.cache_for_phone(ledger, PHONE)
    latest = max(ledger, key=lambda row: row["version"])
    assert stored["consent"]["sms"] is (latest["action"] == consent.GRANTED)


def _plan_stages(plan: Any) -> Iterator[str]:
    """Yield every stage name in an explain plan.

    Args:
        plan: Plan fragment.

    Yields:
        Stage names.
    """
    if isinstance(plan, dict):
        node: dict[str, Any] = plan  # pyright: ignore[reportUnknownVariableType]
        if isinstance(node.get("stage"), str):
            yield str(node["stage"])
        for value in node.values():
            yield from _plan_stages(value)
    elif isinstance(plan, list):
        for value in plan:  # pyright: ignore[reportUnknownVariableType]
            yield from _plan_stages(value)


def _list_everything(client: TestClient, headers: dict[str, str], carrier_id: str) -> None:
    """Call every tenant list route, with and without filters.

    Args:
        client: Test client.
        headers: Owner headers.
        carrier_id: A carrier id for filters.
    """
    paths = ["/v1/carriers", "/v1/carriers?status=onboarding&q=wolf", "/v1/carriers?tag=team_driver",
             f"/v1/drivers?carrier_id={carrier_id}", f"/v1/trucks?carrier_id={carrier_id}", "/v1/brokers",
             "/v1/brokers?q=123456", "/v1/brokers/123456/checks", "/v1/contacts", "/v1/contacts?kind=shipper",
             "/v1/facilities", "/v1/facilities?state=TX", f"/v1/notes?ref_type=carrier&ref_id={carrier_id}",
             "/v1/audit", "/v1/members", "/v1/members/invitations", "/v1/tags"]
    for path in paths:
        response = client.get(path, headers=headers)
        assert response.status_code == 200, (path, response.text)


def test_tenant_list_queries_use_an_index(client: TestClient, mongo_client: IsolatedMongoClient, clock: FakeClock,
                                          recorder: FindRecorder) -> None:
    firms = seed_firms(client, mongo_client, clock)
    owner = firms.headers("owner")
    carrier = created(client, owner, "/v1/carriers", CARRIER)
    created(client, owner, "/v1/drivers", {"carrier_id": carrier["id"], "name": "Sam"})
    created(client, owner, "/v1/brokers", {"mc_number": "123456"})
    created(client, owner, "/v1/contacts", {"kind": "shipper", "name": "Dock Boss"})
    created(client, owner, "/v1/notes", {"ref": {"type": "carrier", "id": carrier["id"]}, "text": "hello"})
    recorder.finds.clear()
    _list_everything(client, owner, carrier["id"])
    prefix = mongo_client.prefix
    checked = 0
    for database, command in list(recorder.finds):
        name = database.removeprefix(prefix)
        if not (name.startswith("firm_") or command["find"] in TENANT_PLATFORM_COLLECTIONS):
            continue
        query = {"find": command["find"], **{key: command[key] for key in EXPLAIN_KEYS if key in command}}
        explained = mongo_client[name].command("explain", query, verbosity="queryPlanner")
        stages = set(_plan_stages(explained["queryPlanner"]["winningPlan"]))
        assert "COLLSCAN" not in stages, (name, query, stages)
        checked += 1
    assert checked >= MIN_EXPLAINED_FINDS


def test_explain_detects_a_collection_scan(mongo_client: MongoClientT) -> None:
    db = _firm(mongo_client)
    db["carriers"].insert_one({"_id": ObjectId(), "phone": PHONE, "nickname": "x"})
    plan = db.command("explain", {"find": "carriers", "filter": {"nickname": "x"}}, verbosity="queryPlanner")
    assert "COLLSCAN" in set(_plan_stages(plan["queryPlanner"]["winningPlan"]))
