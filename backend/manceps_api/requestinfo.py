"""Facts about the current request used for rate limiting, audit and session records."""

from __future__ import annotations

from fastapi import Request

from .settings import Settings

UNKNOWN_IP = "unknown"
FORWARDED_FOR = "x-forwarded-for"
USER_AGENT_MAX_CHARS = 200


def client_ip(request: Request, settings: Settings) -> str:
    """Identify the caller for rate limits, audit and sessions.

    Behind TRUST_PROXY, each of the TRUSTED_PROXY_HOPS proxies appends the address it received the request from to
    X-Forwarded-For, so the client is the entry that many hops from the right. Entries further left were written by
    the client and are never trusted. A header shorter than the proxy chain falls back to the peer address.

    Args:
        request: Incoming request.
        settings: Application settings (trust_proxy, trusted_proxy_hops).

    Returns:
        Client IP, or "unknown".
    """
    peer = request.client.host if request.client else UNKNOWN_IP
    if not settings.trust_proxy:
        return peer
    hops = [hop.strip() for hop in request.headers.get(FORWARDED_FOR, "").split(",") if hop.strip()]
    if len(hops) < settings.trusted_proxy_hops:
        return peer
    return hops[-settings.trusted_proxy_hops]


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
