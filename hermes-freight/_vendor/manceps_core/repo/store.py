"""Generic firm-data operations: live lookups, paging, and writes that always append an audit record.

Soft-deleted records carry `deleted_at`; every read here filters `deleted_at: None` (which also matches records
written by the plugin, which never sets the field). Every write takes a `WriteContext` naming the actor, so imports,
approvals and the API audit the same way by construction.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from .. import audit
from ..clock import Clock, utc_now
from ..mongo import Doc, MongoDb
from .errors import Conflict, NotFound
from .fields import parse_id

LIVE: Mapping[str, Any] = {"deleted_at": None}
ASCENDING = 1
DESCENDING = -1

DuplicateRule = tuple[str, str]


@dataclass(frozen=True)
class WriteContext:
    """Who is writing, and the request and session to record in the audit log."""

    who: Mapping[str, Any]
    request_id: str | None = None
    session_id: str | None = None
    clock: Clock = field(default=utc_now)

    def now(self) -> datetime:
        """Return the current time from the context's clock.

        Returns:
            Timezone-aware UTC datetime.
        """
        return self.clock()

    def audit(self, db: MongoDb, what: str, ref: Mapping[str, Any] | None, before: Mapping[str, Any] | None,
              after: Mapping[str, Any] | None) -> None:
        """Append an audit record for a write.

        Args:
            db: Firm database.
            what: Event name, e.g. "carrier.update".
            ref: Subject {type, id}.
            before: State before, or None for a create.
            after: State after, or None for a delete.
        """
        audit.write(db, self.who, what, ref, self.request_id, self.session_id, before, after, self.clock)


def ref_of(ref_type: str, doc: Mapping[str, Any]) -> dict[str, str]:
    """Build the audit subject for a document.

    Args:
        ref_type: Record kind.
        doc: Stored document.

    Returns:
        {type, id}.
    """
    return {"type": ref_type, "id": str(doc["_id"])}


def find_live(db: MongoDb, collection: str, query: Mapping[str, Any], what: str) -> Doc:
    """Load one live (not soft-deleted) record.

    Args:
        db: Firm database.
        collection: Collection name.
        query: Filter.
        what: Record kind for the error.

    Returns:
        The document.

    Raises:
        NotFound: If no live record matches.
    """
    doc = db[collection].find_one({**query, **LIVE})
    if doc is None:
        raise NotFound(what)
    return doc


def get_by_id(db: MongoDb, collection: str, raw_id: Any, what: str) -> Doc:
    """Load one live record by id.

    Args:
        db: Firm database.
        collection: Collection name.
        raw_id: Id text or ObjectId.
        what: Record kind for the error.

    Returns:
        The document.

    Raises:
        NotFound: If the id is malformed or no live record has it.
    """
    return find_live(db, collection, {"_id": parse_id(raw_id, what)}, what)


def list_live(db: MongoDb, collection: str, query: Mapping[str, Any], after: ObjectId | None, limit: int,
              direction: int = ASCENDING) -> list[Doc]:
    """List live records by `_id`, one more than the page size so the caller can tell if more follow.

    Args:
        db: Firm database.
        collection: Collection name.
        query: Filter.
        after: Last id of the previous page, or None.
        limit: Page size.
        direction: ASCENDING (oldest first) or DESCENDING (newest first).

    Returns:
        Up to limit + 1 documents.
    """
    condition: dict[str, Any] = {**query, **LIVE}
    if after is not None:
        condition["_id"] = {"$gt" if direction == ASCENDING else "$lt": after}
    return list(db[collection].find(condition, limit=limit + 1).sort([("_id", direction)]))


def insert(db: MongoDb, ctx: WriteContext, collection: str, ref_type: str, doc: Mapping[str, Any],
           duplicate: DuplicateRule | None = None) -> Doc:
    """Insert a record stamped with created/updated times and creator, then audit it.

    Args:
        db: Firm database.
        ctx: Writer.
        collection: Collection name.
        ref_type: Record kind (audit event "<ref_type>.create").
        doc: Validated fields.
        duplicate: (code, message) for a unique-index clash, or None to re-raise it.

    Returns:
        The stored document.

    Raises:
        Conflict: On a unique-index clash with a duplicate rule.
        DuplicateKeyError: On a unique-index clash without one.
    """
    now = ctx.now()
    stored: Doc = {"_id": ObjectId(), **doc, "created_at": now, "updated_at": now, "created_by": dict(ctx.who)}
    try:
        db[collection].insert_one(stored)
    except DuplicateKeyError as exc:
        if duplicate is None:
            raise
        raise Conflict(duplicate[0], duplicate[1]) from exc
    ctx.audit(db, f"{ref_type}.create", ref_of(ref_type, stored), None, stored)
    return stored


def update(db: MongoDb, ctx: WriteContext, collection: str, ref_type: str, current: Doc, changes: Mapping[str, Any],
           duplicate: DuplicateRule | None = None) -> Doc:
    """Apply validated changes (None removes a field) to a live record, then audit before and after.

    Args:
        db: Firm database.
        ctx: Writer.
        collection: Collection name.
        ref_type: Record kind (audit event "<ref_type>.update").
        current: The record as loaded.
        changes: Field values; None means remove the field.
        duplicate: (code, message) for a unique-index clash.

    Returns:
        The updated document.

    Raises:
        NotFound: If the record was deleted meanwhile.
        Conflict: On a unique-index clash with a duplicate rule.
    """
    operations: dict[str, Any] = {"$set": {**{k: v for k, v in changes.items() if v is not None},
                                           "updated_at": ctx.now()}}
    removed = {key: "" for key, value in changes.items() if value is None}
    if removed:
        operations["$unset"] = removed
    return _apply(db, ctx, collection, ref_type, current, operations, "update", duplicate)


def soft_delete(db: MongoDb, ctx: WriteContext, collection: str, ref_type: str, current: Doc,
                changes: Mapping[str, Any] | None = None, removed: tuple[str, ...] = ()) -> Doc:
    """Mark a record deleted (it disappears from every live read), then audit it.

    Args:
        db: Firm database.
        ctx: Writer.
        collection: Collection name.
        ref_type: Record kind (audit event "<ref_type>.delete").
        current: The record as loaded.
        changes: Extra fields to set (e.g. a phone tombstone).
        removed: Fields to remove (e.g. a unique VIN).

    Returns:
        The deleted document.

    Raises:
        NotFound: If the record was deleted meanwhile.
    """
    now = ctx.now()
    operations: dict[str, Any] = {"$set": {**dict(changes or {}), "deleted_at": now, "updated_at": now}}
    if removed:
        operations["$unset"] = {name: "" for name in removed}
    return _apply(db, ctx, collection, ref_type, current, operations, "delete", None)


def _apply(db: MongoDb, ctx: WriteContext, collection: str, ref_type: str, current: Doc,
           operations: Mapping[str, Any], verb: str, duplicate: DuplicateRule | None) -> Doc:
    """Run one conditional update on a live record and audit it.

    Args:
        db: Firm database.
        ctx: Writer.
        collection: Collection name.
        ref_type: Record kind.
        current: The record as loaded.
        operations: Update operators.
        verb: Audit verb.
        duplicate: (code, message) for a unique-index clash.

    Returns:
        The document after the update.

    Raises:
        NotFound: If the record was deleted meanwhile.
        Conflict: On a unique-index clash with a duplicate rule.
        DuplicateKeyError: On a unique-index clash without one.
    """
    try:
        after = db[collection].find_one_and_update({"_id": current["_id"], **LIVE}, dict(operations),
                                                   return_document=ReturnDocument.AFTER)
    except DuplicateKeyError as exc:
        if duplicate is None:
            raise
        raise Conflict(duplicate[0], duplicate[1]) from exc
    if after is None:
        raise NotFound(ref_type)
    ctx.audit(db, f"{ref_type}.{verb}", ref_of(ref_type, current), current, None if verb == "delete" else after)
    return after
