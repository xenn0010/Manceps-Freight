"""Time source. Everything takes an injectable clock so tests stay deterministic."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TypeAlias

Clock: TypeAlias = Callable[[], datetime]


def utc_now() -> datetime:
    """Return the current time.

    Returns:
        Timezone-aware UTC datetime.
    """
    return datetime.now(UTC)
