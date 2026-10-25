"""Rolling-window rate limits stored in platform.rate_limits."""

from __future__ import annotations

from datetime import timedelta

import pytest
from conftest import START, FakeClock

from manceps_api.errors import ApiError
from manceps_api.ratelimit import RATE_LIMITS, allow, enforce
from manceps_core.mongo import MongoDb

WINDOW = timedelta(hours=1)
PHONE = "+12145550199"


def test_rate_limit_window(platform_db: MongoDb) -> None:
    """The limit holds inside the window, is per kind and key, and frees up once old attempts age out."""
    clock = FakeClock(START)
    assert [allow(platform_db, "otp_check", PHONE, 3, WINDOW, clock()) for _ in range(3)] == [True] * 3
    assert allow(platform_db, "otp_check", PHONE, 3, WINDOW, clock()) is False
    assert allow(platform_db, "otp_check", "+12145550100", 3, WINDOW, clock()) is True
    assert allow(platform_db, "otp_send", PHONE, 3, WINDOW, clock()) is True
    assert platform_db[RATE_LIMITS].count_documents({"kind": "otp_check", "key": PHONE}) == 3

    clock.advance(WINDOW - timedelta(seconds=1))
    assert allow(platform_db, "otp_check", PHONE, 3, WINDOW, clock()) is False
    clock.advance(timedelta(seconds=1))
    assert allow(platform_db, "otp_check", PHONE, 3, WINDOW, clock()) is True


def test_enforce_raises_429_with_retry_after(platform_db: MongoDb) -> None:
    """Exceeding the limit is 429 rate_limited with Retry-After counting down to the oldest attempt's expiry."""
    clock = FakeClock(START)
    enforce(platform_db, "otp_send", PHONE, 1, WINDOW, clock())
    clock.advance(timedelta(minutes=10))
    with pytest.raises(ApiError) as caught:
        enforce(platform_db, "otp_send", PHONE, 1, WINDOW, clock())
    assert caught.value.status_code == 429
    assert caught.value.code == "rate_limited"
    assert caught.value.headers == {"Retry-After": str(50 * 60)}


def test_rate_limit_rejects_bad_arguments(platform_db: MongoDb) -> None:
    """A zero limit or empty key is a programming error, not an open door."""
    with pytest.raises(ValueError):
        allow(platform_db, "otp_send", PHONE, 0, WINDOW, START)
    with pytest.raises(ValueError):
        allow(platform_db, "otp_send", "", 3, WINDOW, START)
