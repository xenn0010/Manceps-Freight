"""Rolling-window rate limits in `platform.rate_limits` (same shape as signup-api's `signup_attempts`)."""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from manceps_core.mongo import MongoDb

from .errors import ApiError

RATE_LIMITS = "rate_limits"
MIN_RETRY_AFTER_SECONDS = 1
RATE_LIMITED_MESSAGE = "too many attempts; try again later"


def allow(db: MongoDb, kind: str, key: str, limit: int, window: timedelta, now: datetime) -> bool:
    """Count an attempt against a rolling window.

    Counting then inserting is not atomic, so a burst of concurrent requests can exceed the limit by the number of
    in-flight requests; this matches the signup API and is acceptable for abuse throttling.

    Args:
        db: Platform database.
        kind: Limit name, e.g. "otp_send_phone".
        key: What is limited, e.g. a phone number or client IP.
        limit: Attempts allowed per window.
        window: Window length.
        now: Current UTC time.

    Returns:
        False when the limit is already reached (the attempt is then not recorded).

    Raises:
        ValueError: If the limit is not positive or the kind or key is empty.
    """
    if limit <= 0 or not kind or not key:
        raise ValueError("rate limit needs a positive limit, a kind and a key")
    recent = db[RATE_LIMITS].count_documents({"kind": kind, "key": key, "at": {"$gt": now - window}})
    if recent >= limit:
        return False
    db[RATE_LIMITS].insert_one({"kind": kind, "key": key, "at": now})
    return True


def _retry_after(db: MongoDb, kind: str, key: str, window: timedelta, now: datetime) -> int:
    """Seconds until the oldest attempt in the window ages out.

    Args:
        db: Platform database.
        kind: Limit name.
        key: Limited key.
        window: Window length.
        now: Current UTC time.

    Returns:
        Whole seconds, at least MIN_RETRY_AFTER_SECONDS.
    """
    oldest = db[RATE_LIMITS].find_one({"kind": kind, "key": key, "at": {"$gt": now - window}}, sort=[("at", 1)])
    if oldest is None:
        return MIN_RETRY_AFTER_SECONDS
    remaining = (oldest["at"] + window - now).total_seconds()
    return max(MIN_RETRY_AFTER_SECONDS, math.ceil(remaining))


def enforce(db: MongoDb, kind: str, key: str, limit: int, window: timedelta, now: datetime) -> None:
    """Record an attempt or reject it with 429.

    Args:
        db: Platform database.
        kind: Limit name.
        key: Limited key.
        limit: Attempts allowed per window.
        window: Window length.
        now: Current UTC time.

    Raises:
        ApiError: 429 rate_limited with Retry-After when the limit is reached.
        ValueError: If the arguments are invalid.
    """
    if allow(db, kind, key, limit, window, now):
        return
    retry_after = _retry_after(db, kind, key, window, now)
    raise ApiError(429, "rate_limited", RATE_LIMITED_MESSAGE, headers={"Retry-After": str(retry_after)})
