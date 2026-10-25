"""Facts about the current request used for rate limiting, audit and session records."""

from __future__ import annotations

from fastapi import Request

UNKNOWN_IP = "unknown"
FORWARDED_FOR = "x-forwarded-for"
USER_AGENT_MAX_CHARS = 200


def client_ip(request: Request, trust_proxy: bool) -> str:
    """Identify the caller (ported from signup-api).

    Args:
        request: Incoming request.
        trust_proxy: Use the first X-Forwarded-For hop (only behind a proxy that sets it).

    Returns:
        Client IP, or "unknown".
    """
    forwarded = request.headers.get(FORWARDED_FOR, "") if trust_proxy else ""
    if forwarded.strip():
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else UNKNOWN_IP


def request_id(request: Request) -> str | None:
    """Return the id RequestContextMiddleware assigned to this request.

    Args:
        request: Incoming request.

    Returns:
        The request id, or None outside the middleware.
    """
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else None


def user_agent(request: Request) -> str:
    """Return a bounded User-Agent string for session records.

    Args:
        request: Incoming request.

    Returns:
        The first USER_AGENT_MAX_CHARS characters of the header, or "".
    """
    return request.headers.get("user-agent", "")[:USER_AGENT_MAX_CHARS]
