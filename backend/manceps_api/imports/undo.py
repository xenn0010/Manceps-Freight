"""Undo a committed import inside its window: restore updated records from their snapshots, remove created ones.

A record is only touched when it is exactly as the import left it (same `updated_at`, not deleted, and for a
created record nothing else refers to it: drivers, trucks, notes, consent rows, facilities). Anything changed since
is left alone and reported as `skipped_modified`. Restoring sets back only the fields the import changed plus
`updated_at`, so the record equals its `before` snapshot again while state the import never touched (for example a
consent cache refreshed meanwhile) is kept. Each step is a conditional write, so two concurrent undo requests cannot
both run (the status claim) and a row is never undone twice.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument

from manceps_core.clock import Clock
from manceps_core.mongo import Doc, MongoDb
from manceps_core.repo.store import WriteContext

from ..errors import ApiError
from .commit import emit_progress
from .header import as_list
from .records import COMMITTED, IMPORT_ROWS, IMPORTS, UNDOING, UNDONE, load_import
from .schema import ENTITY_SPECS

CONFLICT = 409
RESTORED, REMOVED, SKIPPED = "restored", "removed", "skipped_modified"
UNDO_ACTIONS = ("created", "updated", "merged")
REFERENCES: Mapping[str, tuple[tuple[str, str], ...]] = {
    "carriers": (("drivers", "carrier_id"), ("trucks", "carrier_id"), ("consent_events", "subject.id"),
                 ("notes", "ref.id")),
    "drivers": (("consent_events", "subject.id"), ("notes", "ref.id")),
    "brokers": (),
    "contacts": (("facilities", "contact_ids"), ("notes", "ref.id")),
}


def _refuse(doc: Doc, now: Any) -> None:
    """Refuse an undo the import's state or window does not allow.

    Args:
        doc: Import document.
        now: Current time.

    Raises:
        ApiError: 409 already_undone, undo_in_progress, import_not_committed or undo_window_closed.
    """
    status = doc["status"]
    if status == UNDONE:
        raise ApiError(CONFLICT, "already_undone", "this import was already undone")
    if status == UNDOING:
        raise ApiError(CONFLICT, "undo_in_progress", "this import is being undone")
    if status != COMMITTED:
        raise ApiError(CONFLICT, "import_not_committed", "only a committed import can be undone")
    if doc.get("undo_until") is None or now > doc["undo_until"]:
        raise ApiError(CONFLICT, "undo_window_closed", "the undo window for this import has closed")


def _referenced(db: MongoDb, entity: str, record_id: ObjectId) -> bool:
    """Tell whether another record refers to a created record.

    Args:
        db: Firm database.
        entity: Entity name.
        record_id: Record id.

    Returns:
        True when something refers to it.
    """
    text = str(record_id)
    return any(db[collection].count_documents({field: text}, limit=1) > 0 for collection, field in REFERENCES[entity])


def _remove(db: MongoDb, ctx: WriteContext, entity: str, outcome: Mapping[str, Any]) -> str:
    """Delete a record the import created, if nothing changed it since.

    Args:
        db: Firm database.
        ctx: Writer.
        entity: Entity name.
        outcome: The row's commit outcome.

    Returns:
        removed or skipped_modified.
    """
    spec = ENTITY_SPECS[entity]
    target_id = outcome["target_id"]
    current = db[spec.collection].find_one({"_id": target_id})
    if current is None or current.get("deleted_at") is not None or current.get("updated_at") != \
            outcome.get("after_updated_at") or _referenced(db, entity, target_id):
        return SKIPPED
    deleted = db[spec.collection].delete_one({"_id": target_id, "updated_at": outcome["after_updated_at"]})
    if deleted.deleted_count != 1:
        return SKIPPED
    ctx.audit(db, f"{spec.ref_type}.import_undo", {"type": spec.ref_type, "id": str(target_id)}, current, None)
    return REMOVED


def _restore(db: MongoDb, ctx: WriteContext, entity: str, row: Doc) -> str:
    """Put back the fields an update changed, if nothing changed the record since.

    Args:
        db: Firm database.
        ctx: Writer.
        entity: Entity name.
        row: Import row with its outcome and before snapshot.

    Returns:
        restored or skipped_modified.
    """
    spec = ENTITY_SPECS[entity]
    outcome, before = row["outcome"], row["before"]
    target_id = outcome["target_id"]
    current = db[spec.collection].find_one({"_id": target_id})
    if current is None or current.get("updated_at") != outcome.get("after_updated_at"):
        return SKIPPED
    changed = [str(name) for name in as_list(outcome.get("changed"))]
    operations: dict[str, Any] = {"$set": {**{name: before[name] for name in changed if name in before},
                                           "updated_at": before.get("updated_at")}}
    removed = {name: "" for name in changed if name not in before}
    if removed:
        operations["$unset"] = removed
    restored = db[spec.collection].find_one_and_update(
        {"_id": target_id, "updated_at": outcome["after_updated_at"], "deleted_at": None}, operations,
        return_document=ReturnDocument.AFTER)
    if restored is None:
        return SKIPPED
    ctx.audit(db, f"{spec.ref_type}.import_undo", {"type": spec.ref_type, "id": str(target_id)}, current, restored)
    return RESTORED


def _undo_rows(db: MongoDb, ctx: WriteContext, job: Doc) -> dict[str, int]:
    """Undo every written row, newest first.

    Args:
        db: Firm database.
        ctx: Writer.
        job: Import document.

    Returns:
        {restored, removed, skipped_modified}.
    """
    query = {"import_id": job["_id"], "outcome.action": {"$in": list(UNDO_ACTIONS)}, "undo": None}
    for row in db[IMPORT_ROWS].find(query).sort([("row_no", -1)]):
        if row["outcome"]["action"] == "created":
            result = _remove(db, ctx, job["entity"], row["outcome"])
        else:
            result = _restore(db, ctx, job["entity"], row)
        db[IMPORT_ROWS].update_one({"_id": row["_id"], "undo": None}, {"$set": {"undo": result}})
    return {name: db[IMPORT_ROWS].count_documents({"import_id": job["_id"], "undo": name})
            for name in (RESTORED, REMOVED, SKIPPED)}


def undo_import(db: MongoDb, ctx: WriteContext, raw_id: Any, clock: Clock) -> Doc:
    """Undo a committed import within its window.

    Args:
        db: Firm database.
        ctx: Writer (the requesting user).
        raw_id: Import id.
        clock: Time source.

    Returns:
        The undone import, with `undo` counts.

    Raises:
        NotFound: Unknown import.
        ApiError: 409 already_undone, undo_in_progress, import_not_committed or undo_window_closed.
    """
    current = load_import(db, raw_id)
    now = clock()
    _refuse(current, now)
    claimed = db[IMPORTS].find_one_and_update({"_id": current["_id"], "status": COMMITTED},
                                              {"$set": {"status": UNDOING, "updated_at": now}},
                                              return_document=ReturnDocument.AFTER)
    if claimed is None:
        _refuse(load_import(db, current["_id"]), now)
        raise ApiError(CONFLICT, "undo_in_progress", "this import is being undone")
    counts = _undo_rows(db, ctx, claimed)
    done = clock()
    final = db[IMPORTS].find_one_and_update(
        {"_id": claimed["_id"]},
        {"$set": {"status": UNDONE, "undo": counts, "undone_at": done, "updated_at": done,
                  "idempotency_hash": f"{claimed['idempotency_hash']}:undone:{claimed['_id']}"}},
        return_document=ReturnDocument.AFTER)
    if final is None:
        raise RuntimeError("import vanished while undoing")
    ctx.audit(db, "import.undo", {"type": "import", "id": str(final["_id"])}, None, {"undo": counts})
    emit_progress(db, final, UNDONE, int(final["stats"]["rows"]), clock)
    return final
