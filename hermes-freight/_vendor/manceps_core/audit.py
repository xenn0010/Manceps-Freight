"""Append-only audit trail in each firm's `audit` collection (field names compatible with the plugin)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .clock import Clock, utc_now
from .hashing import sha256_hex
from .mongo import MongoDb

AUDIT = "audit"


def write(
    db: MongoDb,
    who: Mapping[str, Any],
    what: str,
    ref: Mapping[str, Any] | None,
    request_id: str | None,
    session_id: str | None,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    clock: Clock = utc_now,
) -> Any:
    """Append an audit record holding hashes of the state before and after a change.

    Args:
        db: Firm database.
        who: Actor, e.g. {"kind": "user", "id": "u1"}.
        what: Event name, e.g. "carrier.update" (stored as `event`, like the plugin).
        ref: Subject {type, id}, or None.
        request_id: HTTP request id, or None outside a request.
        session_id: Auth session id, or None.
        before: State before the change, or None for a create.
        after: State after the change, or None for a delete.
        clock: Time source.

    Returns:
        The inserted audit id.

    Raises:
        ValueError: If the event name is empty or a state holds naive datetimes or NaN.
        TypeError: If a state holds values that are not JSON-like.
    """
    if not what:
        raise ValueError("audit event name is empty")
    record = {
        "event": what,
        "at": clock(),
        "who": dict(who),
        "ref": dict(ref) if ref is not None else None,
        "request_id": request_id,
        "session_id": session_id,
        "before_hash": sha256_hex(before) if before is not None else None,
        "after_hash": sha256_hex(after) if after is not None else None,
    }
    return db[AUDIT].insert_one(record).inserted_id
