"""Counters, events, audit records and canonical hashing."""

from __future__ import annotations

import hashlib
import math
import threading
from datetime import UTC, datetime
from typing import Any

import pytest
from bson import ObjectId
from conftest import START, FakeClock
from mongomock.collection import Collection as MockCollection
from pymongo.errors import DuplicateKeyError

from manceps_core import audit, events
from manceps_core.counters import next_value
from manceps_core.hashing import canonical_json, sha256_hex
from manceps_core.indexes import ensure_firm_indexes
from manceps_core.mongo import MongoClientT, MongoDb

THREADS = 8
EMITS_PER_THREAD = 40


@pytest.fixture
def firm_db(mongo_client: MongoClientT) -> MongoDb:
    """Return a firm database with indexes.

    Args:
        mongo_client: In-memory client.

    Returns:
        The firm database.
    """
    db = mongo_client["firm_apex_freight"]
    ensure_firm_indexes(db)
    return db


def test_counter_next_value(firm_db: MongoDb) -> None:
    """Counters start at 1 and are independent by name."""
    assert [next_value(firm_db, "loads_2026") for _ in range(3)] == [1, 2, 3]
    assert next_value(firm_db, "loads_2027") == 1


def _serialize_find_and_modify(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give mongomock MongoDB's per-document findAndModify atomicity.

    The real server applies `$inc` via findAndModify atomically; mongomock reads then writes without a lock, so
    without this the double (not the counter) produces duplicate values under threads.

    Args:
        monkeypatch: Pytest monkeypatch.
    """
    original = vars(MockCollection)["find_one_and_update"]
    lock = threading.Lock()

    def atomic(self: MockCollection, *args: Any, **kwargs: Any) -> Any:
        with lock:
            return original(self, *args, **kwargs)

    monkeypatch.setattr(MockCollection, "find_one_and_update", atomic)


def test_counter_retries_first_upsert_race(firm_db: MongoDb, monkeypatch: pytest.MonkeyPatch) -> None:
    """When a concurrent first upsert wins the _id race, the loser retries and gets the next value."""
    original = vars(MockCollection)["find_one_and_update"]
    calls = {"n": 0}

    def racing(self: MockCollection, *args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            original(self, *args, **kwargs)
            raise DuplicateKeyError("E11000 duplicate key error collection: counters index: _id_")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(MockCollection, "find_one_and_update", racing)
    assert next_value(firm_db, "events") == 2
    assert calls["n"] == 2


def test_counter_rejects_empty_name(firm_db: MongoDb) -> None:
    """A counter needs a name."""
    with pytest.raises(ValueError):
        next_value(firm_db, "")


def test_events_seq_monotonic_under_threads(firm_db: MongoDb, monkeypatch: pytest.MonkeyPatch) -> None:
    """Concurrent emitters get unique, gap-free sequence numbers, increasing within each thread."""
    _serialize_find_and_modify(monkeypatch)
    per_thread: list[list[int]] = [[] for _ in range(THREADS)]
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            for n in range(EMITS_PER_THREAD):
                doc = events.emit(firm_db, "load.status_changed", {"type": "load", "id": f"{index}-{n}"}, {"n": n})
                per_thread[index].append(doc["seq"])
        except Exception as exc:  # noqa: BLE001  # surfaced to the main thread below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    for seqs in per_thread:
        assert seqs == sorted(seqs)
    every = sorted(seq for seqs in per_thread for seq in seqs)
    assert every == list(range(1, THREADS * EMITS_PER_THREAD + 1))
    assert firm_db["events"].count_documents({}) == THREADS * EMITS_PER_THREAD


def test_emit_document_shape(firm_db: MongoDb) -> None:
    """An event stores seq, type, ref, data and the clock time."""
    clock = FakeClock(START)
    doc = events.emit(firm_db, "approval.created", {"type": "approval", "id": "a1"}, {"kind": "accept_rate"},
                      clock=clock)
    stored = firm_db["events"].find_one({"seq": doc["seq"]}, {"_id": 0})
    assert stored == {"seq": 1, "type": "approval.created", "ref": {"type": "approval", "id": "a1"},
                      "data": {"kind": "accept_rate"}, "at": START}


def test_emit_rejects_bad_type_and_large_data(firm_db: MongoDb) -> None:
    """Event types are dotted lowercase names and data stays small."""
    with pytest.raises(ValueError, match="event type"):
        events.emit(firm_db, "Load Changed", None, {})
    with pytest.raises(ValueError, match="too large"):
        events.emit(firm_db, "load.updated", None, {"blob": "x" * (events.MAX_DATA_BYTES + 1)})
    assert firm_db["events"].count_documents({}) == 0


def test_audit_write_hashes(firm_db: MongoDb) -> None:
    """Audit rows hold who, what, ref, request and session ids, and SHA-256 hashes of canonical JSON."""
    clock = FakeClock(START)
    before = {"dispatch_fee_pct": 8.0, "name": "Ace"}
    after = {"name": "Ace", "dispatch_fee_pct": 10.0}
    audit_id = audit.write(
        firm_db, {"kind": "user", "id": "u1"}, "carrier.update", {"type": "carrier", "id": "c1"},
        "req-1", "sess-1", before, after, clock=clock,
    )
    row = firm_db["audit"].find_one({"_id": audit_id})
    assert row is not None
    assert row["event"] == "carrier.update"
    assert row["who"] == {"kind": "user", "id": "u1"}
    assert row["ref"] == {"type": "carrier", "id": "c1"}
    assert (row["request_id"], row["session_id"], row["at"]) == ("req-1", "sess-1", START)
    assert row["before_hash"] == sha256_hex({"name": "Ace", "dispatch_fee_pct": 8.0})
    assert row["after_hash"] == sha256_hex(after)
    assert row["before_hash"] != row["after_hash"]


def test_audit_create_has_no_before_hash(firm_db: MongoDb) -> None:
    """Creates have no before state."""
    audit_id = audit.write(firm_db, {"kind": "system", "id": "worker"}, "carrier.create", None, None, None,
                           None, {"name": "Ace"})
    row = firm_db["audit"].find_one({"_id": audit_id})
    assert row is not None and row["before_hash"] is None and row["ref"] is None
    assert row["at"].tzinfo is not None


def test_canonical_json_is_stable() -> None:
    """Key order and whitespace never change the hash; special types serialize deterministically."""
    oid = ObjectId("65f000000000000000000001")
    when = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    text = canonical_json({"b": [1, {"z": when, "a": oid}], "a": "é"})
    assert text == '{"a":"é","b":[1,{"a":"65f000000000000000000001","z":"2026-01-02T03:04:05+00:00"}]}'
    assert sha256_hex({"x": 1, "y": 2}) == sha256_hex({"y": 2, "x": 1})
    assert sha256_hex({"x": 1}) == hashlib.sha256(b'{"x":1}').hexdigest()


def test_canonical_json_rejects_ambiguous_values() -> None:
    """NaN, naive datetimes and unknown types are refused rather than hashed ambiguously."""
    with pytest.raises(ValueError):
        canonical_json({"x": math.nan})
    with pytest.raises(ValueError, match="timezone"):
        canonical_json({"at": datetime(2026, 1, 1)})
    with pytest.raises(TypeError):
        canonical_json({"x": {1, 2}})
