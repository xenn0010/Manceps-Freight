"""Scoped-link exchange and the carrier portal (`aud="portal"` tokens work only here)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Request
from pydantic import BaseModel

from manceps_core import accounts

from ..auth.models import PortalTokenResponse, ScopedExchangeRequest
from ..auth.principal import PortalPrincipal, require_tokens, unauthorized
from ..auth.scoped import SCOPED_LINKS, link_is_live
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


def _id_filter(raw_id: str) -> dict[str, Any]:
    """Match a document id stored either as an ObjectId (plugin-written carriers) or as a string.

    Args:
        raw_id: Id from a verified token.

    Returns:
        The `_id` filter.
    """
    if ObjectId.is_valid(raw_id):
        return {"_id": {"$in": [ObjectId(raw_id), raw_id]}}
    return {"_id": raw_id}


@router.post("/auth/scoped/exchange", operation_id="auth_scoped_exchange", summary="Exchange a scoped link")
def auth_scoped_exchange(body: ScopedExchangeRequest, request: Request) -> PortalTokenResponse:
    """Exchange a carrier link token for a 60-minute portal token (aud=portal, role=carrier, sub=carrier id).

    Args:
        body: Link token.
        request: Incoming request.

    Returns:
        The portal token.

    Raises:
        ApiError: 401 invalid_link for unknown, revoked or expired links; 429; 503 without JWT keys.
    """
    context = get_context(request)
    tokens = require_tokens(context)
    db, now = context.platform_db, context.clock()
    enforce(db, "scoped_exchange_ip", client_ip(request, context.settings.trust_proxy), EXCHANGE_PER_IP,
            RATE_WINDOW, now)
    link = db[SCOPED_LINKS].find_one({"token_hash": hash_token(body.token)})
    if link is None or not link_is_live(link, now):
        raise unauthorized("invalid_link", "this link is invalid or has expired")
    subject = link["subject"]
    role = "driver" if subject["type"] == "driver" else "carrier"
    issued = tokens.issue(sub=str(subject["id"]), tid=str(link["tenant_id"]), role=role, sid=str(link["_id"]),
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
    carrier = firm_db[CARRIERS].find_one({**_id_filter(principal.user_id), "deleted_at": None})
    if carrier is None:
        raise ApiError(404, "not_found", "carrier not found")
    firm = accounts.find_firm(context.platform_db, str(principal.tenant_id))
    return PortalMe(carrier_id=principal.user_id, carrier_name=str(carrier.get("name") or ""),
                    firm_name=str(firm.get("name") or "") if firm is not None else "")
