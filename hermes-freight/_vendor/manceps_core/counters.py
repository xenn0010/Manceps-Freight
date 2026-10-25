"""Atomic named counters in a firm's `counters` collection (load refs, event seq, invoice numbers)."""

from __future__ import annotations

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from .mongo import Doc, MongoDb

COUNTERS = "counters"


def _increment(db: MongoDb, name: str) -> Doc:
    """Run the atomic upsert-increment.

    Args:
        db: Firm database.
        name: Counter name.

    Returns:
        The counter document after the increment.

    Raises:
        RuntimeError: If the server returns no document despite upsert.
    """
    doc = db[COUNTERS].find_one_and_update(
        {"_id": name}, {"$inc": {"value": 1}}, upsert=True, return_document=ReturnDocument.AFTER,
    )
    if doc is None:
        raise RuntimeError(f"counter {name!r} upsert returned no document")
    return doc


def next_value(db: MongoDb, name: str) -> int:
    """Increment a counter and return its new value; the first call returns 1.

    Two concurrent first-time upserts can race on `_id`; the loser retries once, when the document exists.

    Args:
        db: Firm database.
        name: Counter name, e.g. "events" or "loads_2026".

    Returns:
        The incremented value.

    Raises:
        ValueError: If the name is empty.
        DuplicateKeyError: If the retry collides again (not expected once the document exists).
    """
    if not name:
        raise ValueError("counter name is empty")
    try:
        doc = _increment(db, name)
    except DuplicateKeyError:
        doc = _increment(db, name)
    return int(doc["value"])
