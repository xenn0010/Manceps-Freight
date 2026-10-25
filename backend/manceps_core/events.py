"""Firm event log feeding the SSE stream: `{seq, type, ref, data, at}` with a gap-free per-firm sequence."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .clock import Clock, utc_now
from .counters import next_value
from .hashing import canonical_json
from .mongo import Doc, MongoDb

EVENTS = "events"
SEQ_COUNTER = "events"
MAX_DATA_BYTES = 16 * 1024
EVENT_TYPE_PATTERN = re.compile(r"^[a-z][a-z_]*(\.[a-z][a-z_]*)+$")


def emit(db: MongoDb, event_type: str, ref: Mapping[str, Any] | None, data: Mapping[str, Any],
         clock: Clock = utc_now) -> Doc:
    """Append an event with the next sequence number.

    Args:
        db: Firm database.
        event_type: Dotted name such as "load.status_changed".
        ref: Subject reference {type, id}, or None.
        data: Small JSON-like payload.
        clock: Time source.

    Returns:
        The stored event document (without `_id`).

    Raises:
        ValueError: If the type is malformed or data exceeds MAX_DATA_BYTES.
        TypeError: If data holds values that are not JSON-like.
    """
    if not EVENT_TYPE_PATTERN.fullmatch(event_type):
        raise ValueError(f"invalid event type {event_type!r}")
    if len(canonical_json(data).encode("utf-8")) > MAX_DATA_BYTES:
        raise ValueError(f"event data too large (max {MAX_DATA_BYTES} bytes)")
    doc: Doc = {
        "seq": next_value(db, SEQ_COUNTER),
        "type": event_type,
        "ref": dict(ref) if ref is not None else None,
        "data": dict(data),
        "at": clock(),
    }
    db[EVENTS].insert_one(dict(doc))
    return doc
