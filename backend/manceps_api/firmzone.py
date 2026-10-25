"""The firm's IANA timezone (dashboard weeks, board times, imported load times)."""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Request

from manceps_core import accounts
from manceps_core.tenancy import Principal

from .context import get_context

DEFAULT_TIMEZONE = "America/Chicago"


def firm_zone(request: Request, principal: Principal) -> ZoneInfo:
    """Read the firm's timezone.

    Args:
        request: Incoming request.
        principal: Firm principal.

    Returns:
        The zone (America/Chicago when unset or unknown).
    """
    firm = accounts.find_firm(get_context(request).platform_db, str(principal.tenant_id)) or {}
    try:
        return ZoneInfo(str(firm.get("timezone") or DEFAULT_TIMEZONE))
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)
