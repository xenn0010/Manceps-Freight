"""Scoped-link exchange and the carrier portal (`aud="portal"` tokens work only here)."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Request
from pydantic import BaseModel

from manceps_core import accounts

from ..auth.models import PortalTokenResponse, ScopedExchangeRequest
from ..auth.principal import PortalPrincipal, require_tokens, unauthorized
from ..auth.scoped import SCOPED_LINKS, link_is_live, link_principal, portal_allowed, subject_id_filter
from ..auth.sessions import hash_token
from ..auth.tokens import AUD_PORTAL
from ..context import get_context
from ..errors import ApiError
from ..ratelimit import enforce
from ..requestinfo import client_ip

router = APIRouter(prefix="/v1", tags=["portal"])

RATE_WINDOW = timedelta(hours=1)
EXCHANGE_PER_IP = 60
PORTAL_EPOCH = 0
CARRIERS = "carriers"


class PortalMe(BaseModel):
    """Who the portal token is for."""

    carrier_id: str
    carrier_name: str
    firm_name: str


@router.post("/auth/scoped/exchange", operation_id="auth_scoped_exchange", summary="Exchange a scoped link")
def auth_scoped_exchange(body: ScopedExchangeRequest, request: Request) -> PortalTokenResponse:
    """Exchange a carrier link token for a 60-minute portal token (aud=portal, role=carrier, sub=carrier id).

    Args:
        body: Link token.
        request: Incoming request.

    Returns:
        The portal token.

    Raises:
        ApiError: 401 invalid_link for unknown, revoked or expired links, a suspended firm or an offboarded or
            deleted carrier; 429; 503 without JWT keys.
    """
    context = get_context(request)
    tokens = require_tokens(context)
    db, now = context.platform_db, context.clock()
    enforce(db, "scoped_exchange_ip", client_ip(request, context.settings), EXCHANGE_PER_IP,
            RATE_WINDOW, now)
    link = db[SCOPED_LINKS].find_one({"token_hash": hash_token(body.token)})
    if link is None or not link_is_live(link, now) or not portal_allowed(db, context.tenant_db, link):
        raise unauthorized("invalid_link", "this link is invalid or has expired")
    scoped = link_principal(link)
    issued = tokens.issue(sub=scoped.user_id, tid=scoped.tenant_id, role=scoped.role, sid=str(link["_id"]),
                          epoch=PORTAL_EPOCH, audience=AUD_PORTAL)
    db[SCOPED_LINKS].update_one({"_id": link["_id"]}, {"$set": {"last_used_at": now}})
    return PortalTokenResponse(access_token=issued.token, expires_in=issued.expires_in)


@router.get("/portal/me", operation_id="portal_me_get", summary="Portal identity")
def portal_me_get(request: Request, principal: PortalPrincipal) -> PortalMe:
    """Return the carrier and firm a portal token belongs to.

    Args:
        request: Incoming request.
        principal: Portal principal.

    Returns:
        Carrier id and name and the firm name.

    Raises:
        ApiError: 404 when the carrier no longer exists in the firm.
    """
    context = get_context(request)
    firm_db = context.tenant_db.for_principal(principal)
    carrier = firm_db[CARRIERS].find_one({**subject_id_filter(principal.user_id), "deleted_at": None})
    if carrier is None:
        raise ApiError(404, "not_found", "carrier not found")
    firm = accounts.find_firm(context.platform_db, str(principal.tenant_id))
    return PortalMe(carrier_id=principal.user_id, carrier_name=str(carrier.get("name") or ""),
                    firm_name=str(firm.get("name") or "") if firm is not None else "")
