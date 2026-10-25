"""The import commit job, run by the worker (and callable directly): every row is written through the repositories.

Exactly once, even across crashes and concurrent workers:
- A worker holds a lease on the import (LEASE, renewed per batch); other workers back off until it expires.
- A row's outcome is recorded with a conditional write; rows with an outcome are never processed again.
- A created row gets its id reserved on the import row before the insert, so a retry finds the record it already
  wrote instead of creating a second one.
- An updated row stores its `before` snapshot (and target) before the update, so a retry re-applies the same change
  computed from the same snapshot, and undo restores exactly that state.
Every write is audited as `{kind: "import", id: <import id>, user_id: <requester>}`; progress goes out as
`import.progress` events.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from manceps_core import events
from manceps_core.clock import Clock
from manceps_core.mongo import Doc, MongoDb
from manceps_core.repo import brokers, carriers, contacts, fleet, loads
from manceps_core.repo.errors import RepoError
from manceps_core.repo.store import WriteContext

from .header import as_map
from .records import COMMITTED, COMMITTING, FAILED, IMPORT_ROWS, IMPORTS, ROWS_TTL, outcome_stats
from .schema import ENTITY_SPECS
from .validate import DEFAULT_CONTACT_KIND, find_match

LEASE = timedelta(minutes=5)
BATCH_ROWS = 200
PROGRESS_EVERY = 250
MAX_ATTEMPTS = 5
DEFAULT_UNDO_HOURS = 24
PROGRESS_EVENT = "import.progress"
EMPTY_VALUES: tuple[Any, ...] = (None, "", [])
MICROS_PER_MILLI = 1000


def emit_progress(db: MongoDb, job: Doc, status: str, done: int, clock: Clock) -> None:
    """Record progress on the import and emit an `import.progress` event.

    Args:
        db: Firm database.
        job: Import document.
        status: Status to report.
        done: Rows processed so far.
        clock: Time source.
    """
    total = int(job["stats"]["rows"])
    db[IMPORTS].update_one({"_id": job["_id"]}, {"$set": {"progress": {"done": done, "total": total}}})
    events.emit(db, PROGRESS_EVENT, {"type": "import", "id": str(job["_id"])},
                {"status": status, "done": done, "total": total, "entity": job["entity"]}, clock)


def record_outcome(db: MongoDb, row_id: ObjectId, outcome: Mapping[str, Any]) -> None:
    """Store a row's outcome once (a row that already has one keeps it).

    Args:
        db: Firm database.
        row_id: Import row id.
        outcome: {action, reason?, target_id?, changed?, after_updated_at?}.
    """
    db[IMPORT_ROWS].update_one({"_id": row_id, "outcome": None}, {"$set": {"outcome": dict(outcome)}})


def _claim(db: MongoDb, import_id: ObjectId, clock: Clock, worker_id: str) -> Doc | None:
    """Take the lease on a queued commit.

    Args:
        db: Firm database.
        import_id: Import id.
        clock: Time source.
        worker_id: This worker.

    Returns:
        The import, or None when it is not queued or another worker holds a live lease.
    """
    now = clock()
    free = {"$or": [{"lease_until": None}, {"lease_until": {"$lt": now}}]}
    return db[IMPORTS].find_one_and_update(
        {"_id": import_id, "status": COMMITTING, **free},
        {"$set": {"lease_until": now + LEASE, "lease_owner": worker_id, "updated_at": now}, "$inc": {"attempts": 1}},
        return_document=ReturnDocument.AFTER)


def _renew(db: MongoDb, import_id: ObjectId, worker_id: str, clock: Clock) -> bool:
    """Extend this worker's lease.

    Args:
        db: Firm database.
        import_id: Import id.
        worker_id: This worker.
        clock: Time source.

    Returns:
        False when the lease was lost (another worker took over).
    """
    result = db[IMPORTS].update_one({"_id": import_id, "status": COMMITTING, "lease_owner": worker_id},
                                    {"$set": {"lease_until": clock() + LEASE}})
    return result.matched_count == 1


def _context(job: Doc, clock: Clock) -> WriteContext:
    """Describe the import as the writer.

    Args:
        job: Import document.
        clock: Time source.

    Returns:
        The write context.
    """
    requester = as_map(job.get("commit_requested_by"))
    return WriteContext(who={"kind": "import", "id": str(job["_id"]), "user_id": requester.get("id")}, clock=clock)


def _skip(reason: str, target_id: ObjectId | None = None) -> Doc:
    """Build a skipped outcome.

    Args:
        reason: Why.
        target_id: Matching record, if any.

    Returns:
        The outcome.
    """
    return {"action": "skipped", "reason": reason, "target_id": target_id}


def _rejected(reason: str) -> Doc:
    """Build a rejected outcome (the repository refused the write).

    Args:
        reason: Error code.

    Returns:
        The outcome.
    """
    return {"action": "rejected", "reason": reason, "target_id": None}


def _collection(job: Doc) -> str:
    """Return the entity's collection.

    Args:
        job: Import document.

    Returns:
        Collection name.
    """
    return ENTITY_SPECS[job["entity"]].collection


def _created(db: MongoDb, job: Doc, target_id: ObjectId) -> Doc | None:
    """Build the created outcome when the reserved record exists.

    Args:
        db: Firm database.
        job: Import document.
        target_id: Reserved id.

    Returns:
        The outcome, or None when nothing was written under that id.
    """
    stored = db[_collection(job)].find_one({"_id": target_id}, {"updated_at": 1})
    if stored is None:
        return None
    return {"action": "created", "reason": None, "target_id": target_id, "after_updated_at": stored["updated_at"]}


def _write_new(db: MongoDb, ctx: WriteContext, job: Doc, values: Mapping[str, Any], target_id: ObjectId) -> Doc:
    """Create the record through its repository.

    Args:
        db: Firm database.
        ctx: Import writer.
        job: Import document.
        values: Validated values.
        target_id: Reserved id.

    Returns:
        The stored record.
    """
    entity, allow = job["entity"], bool(job.get("commit_allow_sensitive"))
    if entity == "carriers":
        return carriers.create_carrier(db, ctx, values, allow, target_id)
    if entity == "drivers":
        return fleet.create_driver(db, ctx, values, target_id)
    if entity == "brokers":
        return brokers.create_broker(db, ctx, values, target_id)
    if entity == "loads":
        return loads.create_load(db, ctx, {key: value for key, value in values.items() if key != "ref"}, target_id)
    contact = {"kind": DEFAULT_CONTACT_KIND, "source": job.get("source") or "import", **values}
    return contacts.create_record(db, ctx, "contact", contact, target_id)


def stored_time(moment: datetime) -> datetime:
    """Round a time the way MongoDB stores it (milliseconds), so it compares equal to the stored value.

    Args:
        moment: Time written.

    Returns:
        The time truncated to milliseconds.
    """
    return moment.replace(microsecond=moment.microsecond // MICROS_PER_MILLI * MICROS_PER_MILLI)


def _create(db: MongoDb, ctx: WriteContext, job: Doc, row: Doc) -> Doc:
    """Create a new record for a row.

    Args:
        db: Firm database.
        ctx: Import writer.
        job: Import document.
        row: Import row.

    Returns:
        The outcome.
    """
    target_id = row["target_id"]
    try:
        stored = _write_new(db, ctx, job, row["values"], target_id)
    except (RepoError, DuplicateKeyError) as exc:
        recovered = _created(db, job, target_id)
        if recovered is not None:
            return recovered
        return _rejected(exc.code if isinstance(exc, RepoError) else "duplicate")
    return {"action": "created", "reason": None, "target_id": target_id,
            "after_updated_at": stored_time(stored["updated_at"])}


def changes_for(entity: str, strategy: str, before: Mapping[str, Any], values: Mapping[str, Any]) -> dict[str, Any]:
    """Compute what an update or merge changes; merge only fills empty fields and never overwrites a value.

    Args:
        entity: Entity name.
        strategy: update or merge.
        before: The record before the import.
        values: The row's values.

    Returns:
        Field to new value.
    """
    identity = ENTITY_SPECS[entity].identity
    changes: dict[str, Any] = {}
    for field, value in values.items():
        current = before.get(field)
        if field in identity or current == value:
            continue
        if strategy == "merge" and current not in EMPTY_VALUES:
            continue
        changes[field] = value
    return changes


def _write_update(db: MongoDb, ctx: WriteContext, job: Doc, before: Doc, changes: Mapping[str, Any]) -> Doc:
    """Update the record through its repository.

    Args:
        db: Firm database.
        ctx: Import writer.
        job: Import document.
        before: The record before the import.
        changes: Field changes.

    Returns:
        The record after the update.
    """
    entity, target_id = job["entity"], before["_id"]
    if entity == "carriers":
        return carriers.update_carrier(db, ctx, target_id, changes, bool(job.get("commit_allow_sensitive")))
    if entity == "drivers":
        return fleet.update_record(db, ctx, "driver", target_id, changes)
    if entity == "brokers":
        return brokers.update_broker(db, ctx, before["mc_number"], changes)
    if entity == "loads":
        return loads.update_load(db, ctx, target_id, changes)
    return contacts.update_record(db, ctx, "contact", target_id, changes)


def _update(db: MongoDb, ctx: WriteContext, job: Doc, row: Doc, before: Doc) -> Doc:
    """Update or merge into an existing record, from the stored snapshot.

    Args:
        db: Firm database.
        ctx: Import writer.
        job: Import document.
        row: Import row.
        before: Snapshot stored on the row.

    Returns:
        The outcome.
    """
    strategy = job["duplicate_strategy"]
    changes = changes_for(job["entity"], strategy, before, row["values"])
    if not changes:
        return _skip("no_changes", before["_id"])
    try:
        after = _write_update(db, ctx, job, before, changes)
    except RepoError as exc:
        return _rejected(exc.code)
    return {"action": "merged" if strategy == "merge" else "updated", "reason": None, "target_id": before["_id"],
            "changed": sorted(changes), "after_updated_at": after["updated_at"]}


def _snapshot(db: MongoDb, row: Doc, match: Doc) -> Doc:
    """Store the record's state before the import on the row (once) and return the stored snapshot.

    Args:
        db: Firm database.
        row: Import row.
        match: The record as it is now.

    Returns:
        The snapshot that the update and undo will use.
    """
    db[IMPORT_ROWS].update_one({"_id": row["_id"], "before": None},
                               {"$set": {"before": match, "target_id": match["_id"]}})
    stored = db[IMPORT_ROWS].find_one({"_id": row["_id"]}, {"before": 1})
    if stored is None or not isinstance(stored.get("before"), dict):
        raise RuntimeError("import row vanished while committing")
    return stored["before"]


def commit_row(db: MongoDb, ctx: WriteContext, job: Doc, row: Doc) -> Doc:
    """Decide and apply one row.

    Args:
        db: Firm database.
        ctx: Import writer.
        job: Import document.
        row: Import row.

    Returns:
        The outcome.
    """
    if row.get("errors"):
        return _skip("invalid")
    if row.get("duplicate_of") is not None:
        return _skip("duplicate_in_file")
    if isinstance(row.get("before"), dict):
        return _update(db, ctx, job, row, row["before"])
    if int(job.get("attempts") or 0) > 1 and isinstance(row.get("target_id"), ObjectId):
        recovered = _created(db, job, row["target_id"])
        if recovered is not None:
            return recovered
    match = find_match(db, job["entity"], row.get("key"))
    if match is None:
        return _create(db, ctx, job, row)
    if job["duplicate_strategy"] == "skip":
        return _skip("exists", match["_id"])
    return _update(db, ctx, job, row, _snapshot(db, row, match))


def _finish(db: MongoDb, job: Doc, worker_id: str, clock: Clock) -> None:
    """Mark the import committed, open the undo window and keep its rows for ROWS_TTL.

    Args:
        db: Firm database.
        job: Import document.
        worker_id: This worker.
        clock: Time source.
    """
    now = clock()
    stats = outcome_stats(db, job["_id"], job["stats"])
    db[IMPORT_ROWS].update_many({"import_id": job["_id"]}, {"$set": {"expires_at": now + ROWS_TTL}})
    undo_hours = int(job.get("undo_hours") or DEFAULT_UNDO_HOURS)
    db[IMPORTS].update_one(
        {"_id": job["_id"], "status": COMMITTING, "lease_owner": worker_id},
        {"$set": {"status": COMMITTED, "stats": stats, "committed_at": now, "lease_until": None,
                  "undo_until": now + timedelta(hours=undo_hours), "updated_at": now}})
    emit_progress(db, {**job, "stats": stats}, COMMITTED, int(stats["rows"]), clock)


def fail_import(db: MongoDb, job: Doc, reason: str, clock: Clock) -> None:
    """Give up on an import: mark it failed and free its content hash so the file can be uploaded again.

    Args:
        db: Firm database.
        job: Import document.
        reason: Error code.
        clock: Time source.
    """
    now = clock()
    db[IMPORTS].update_one({"_id": job["_id"], "status": COMMITTING},
                           {"$set": {"status": FAILED, "error": reason, "lease_until": None, "updated_at": now,
                                     "idempotency_hash": f"{job['idempotency_hash']}:failed:{job['_id']}"}})
    emit_progress(db, job, FAILED, 0, clock)


def commit_import(db: MongoDb, import_id: ObjectId, clock: Clock, worker_id: str) -> bool:
    """Run a queued commit to the end (or resume one whose worker died).

    Args:
        db: Firm database.
        import_id: Import id.
        clock: Time source.
        worker_id: Name of this worker (lease owner).

    Returns:
        True when this call finished the import; False when there was nothing to do or another worker owns it.
    """
    job = _claim(db, import_id, clock, worker_id)
    if job is None:
        return False
    if int(job.get("attempts") or 0) > MAX_ATTEMPTS:
        fail_import(db, job, "too_many_attempts", clock)
        return False
    ctx = _context(job, clock)
    done = db[IMPORT_ROWS].count_documents({"import_id": import_id, "outcome": {"$ne": None}})
    emit_progress(db, job, COMMITTING, done, clock)
    while batch := list(db[IMPORT_ROWS].find({"import_id": import_id, "outcome": None}).sort([("row_no", 1)])
                        .limit(BATCH_ROWS)):
        for row in batch:
            record_outcome(db, row["_id"], commit_row(db, ctx, job, row))
            done += 1
            if done % PROGRESS_EVERY == 0:
                emit_progress(db, job, COMMITTING, done, clock)
        if not _renew(db, import_id, worker_id, clock):
            return False
    _finish(db, job, worker_id, clock)
    return True
