"""Notes attached to any firm record, and the firm's tag vocabulary.

A note's subject must be a live record of the same firm. Broker notes are not stored here: they stay in the
broker's own `notes` array, the shape the plugin reads (see `brokers.add_note`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from bson import ObjectId

from ..mongo import Doc, MongoDb
from . import fields
from .store import LIVE, WriteContext, get_by_id, insert, list_live

NOTES = "notes"
REF_TYPE = "note"
NOTE_SUBJECTS: Mapping[str, str] = {
    "carrier": "carriers", "driver": "drivers", "truck": "trucks", "contact": "contacts", "facility": "facilities",
    "load": "loads",
}
TAGGED_COLLECTIONS = ("carriers", "brokers", "contacts")
MAX_TAGS_LISTED = 500


def _subject(db: MongoDb, ref_type: str, ref_id: Any) -> Doc:
    """Load the live record a note is about.

    Args:
        db: Firm database.
        ref_type: Subject kind (a key of NOTE_SUBJECTS).
        ref_id: Subject id.

    Returns:
        The subject.

    Raises:
        Invalid: If the kind is not one notes can attach to.
        NotFound: If the subject is not a live record of this firm.
    """
    fields.choice("ref.type", ref_type, NOTE_SUBJECTS)
    return get_by_id(db, NOTE_SUBJECTS[ref_type], ref_id, ref_type)


def create_note(db: MongoDb, ctx: WriteContext, ref_type: str, ref_id: Any, text: Any, pinned: bool = False) -> Doc:
    """Attach a note to a record.

    Args:
        db: Firm database.
        ctx: Writer (also the note's author).
        ref_type: Subject kind.
        ref_id: Subject id.
        text: Note text (at most MAX_NOTE_CHARS).
        pinned: Show the note first.

    Returns:
        The stored note.

    Raises:
        Invalid: On a blank or long text or an unsupported subject kind.
        NotFound: If the subject is not live.
    """
    body = fields.text("text", text, fields.MAX_NOTE_CHARS, required=True)
    subject = _subject(db, ref_type, ref_id)
    doc = {"ref": {"type": ref_type, "id": str(subject["_id"])}, "text": body, "pinned": bool(pinned),
           "author": dict(ctx.who)}
    return insert(db, ctx, NOTES, REF_TYPE, doc)


def list_notes(db: MongoDb, ref_type: str, ref_id: Any, after: ObjectId | None, limit: int) -> list[Doc]:
    """List the notes of one record, oldest first.

    Args:
        db: Firm database.
        ref_type: Subject kind.
        ref_id: Subject id.
        after: Cursor id.
        limit: Page size.

    Returns:
        Up to limit + 1 notes.

    Raises:
        Invalid: On an unsupported subject kind.
        NotFound: If the subject is not live.
    """
    subject = _subject(db, ref_type, ref_id)
    return list_live(db, NOTES, {"ref.type": ref_type, "ref.id": str(subject["_id"])}, after, limit)


def tag_counts(db: MongoDb) -> list[dict[str, Any]]:
    """Count tag use across live carriers, brokers and contacts.

    Args:
        db: Firm database.

    Returns:
        [{tag, count, by_entity}] sorted by count (descending) then tag, at most MAX_TAGS_LISTED.
    """
    counts: dict[str, dict[str, int]] = {}
    for collection in TAGGED_COLLECTIONS:
        pipeline: list[dict[str, Any]] = [{"$match": dict(LIVE)}, {"$unwind": "$tags"},
                                          {"$group": {"_id": "$tags", "n": {"$sum": 1}}}]
        for row in db[collection].aggregate(pipeline):
            by_entity = counts.setdefault(str(row["_id"]), dict.fromkeys(TAGGED_COLLECTIONS, 0))
            by_entity[collection] = int(row["n"])
    ranked = sorted(counts.items(), key=lambda pair: (-sum(pair[1].values()), pair[0]))[:MAX_TAGS_LISTED]
    return [{"tag": tag, "count": sum(by_entity.values()), "by_entity": by_entity} for tag, by_entity in ranked]
