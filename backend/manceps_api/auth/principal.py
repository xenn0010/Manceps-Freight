"""Principal dependencies: who is calling, for which firm, with which role.

Every authenticated request costs a session read and a user read (no caching: revoking a session or `logout-all`
bites on the very next request). Firm routes additionally read the firm row and the membership, so a suspended firm,
a removed member or a changed role takes effect immediately; the role used for checks is the membership's, not the
token's. Portal tokens (aud="portal") are checked against their scoped link and never satisfy firm routes.

This module deliberately does not use `from __future__ import annotations`: `require_role` returns a closure with an
`Annotated[...]` signature that FastAPI must evaluate eagerly.
"""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any, Literal, cast

import structlog
from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from manceps_core import accounts, signups
from manceps_core.mongo import Doc
from manceps_core.tenancy import Principal, Role

from ..context import AppContext, get_context
from ..errors import ApiError
from ..idempotency import IdempotencyGuard, idempotency_dependency
from .scoped import SCOPED_LINKS, link_is_live, portal_allowed
from .sessions import find_session
from .tokens import AUD_FIRM, AUD_PORTAL, Audience, TokenClaims, TokenError, TokenService

FirmRole = Literal["owner", "dispatcher", "viewer"]
ROLE_RANK: dict[str, int] = {"viewer": 1, "dispatcher": 2, "owner": 3}
FIRM_ROLES: frozenset[str] = frozenset(ROLE_RANK)
PROVISIONING = "provisioning"

firm_bearer = HTTPBearer(auto_error=False, scheme_name="FirmBearer",
                         description="Access token (aud=firm) from /v1/auth/otp/verify, magic-link or refresh.")
portal_bearer = HTTPBearer(auto_error=False, scheme_name="PortalBearer",
                           description="Portal token (aud=portal) from /v1/auth/scoped/exchange.")


def unauthorized(code: str = "unauthorized", message: str = "authentication required") -> ApiError:
    """Build a 401 with the Bearer challenge.

    Args:
        code: Error code.
        message: Safe message.

    Returns:
        The error to raise.
    """
    return ApiError(401, code, message, headers={"WWW-Authenticate": "Bearer"})


def require_tokens(context: AppContext) -> TokenService:
    """Return the token service or refuse with 503 when JWT keys are not configured.

    Args:
        context: Application context.

    Returns:
        The token service.

    Raises:
        ApiError: 503 auth_not_configured.
    """
    if context.tokens is None:
        raise ApiError(503, "auth_not_configured", "sign-in is not configured on this server")
    return context.tokens


def _verify(context: AppContext, credentials: HTTPAuthorizationCredentials | None, audience: Audience) -> TokenClaims:
    """Verify a bearer token for an audience.

    Args:
        context: Application context.
        credentials: Parsed Authorization header, or None.
        audience: Required audience.

    Returns:
        The claims.

    Raises:
        ApiError: 503 without keys, 401 for a missing or invalid token.
    """
    tokens = require_tokens(context)
    if credentials is None or not credentials.credentials:
        raise unauthorized()
    try:
        return tokens.verify(credentials.credentials, audience)
    except TokenError as exc:
        raise unauthorized(exc.code, exc.message) from exc


def _live_user(context: AppContext, claims: TokenClaims) -> Doc:
    """Check the token's session is live and its epoch is current.

    Args:
        context: Application context.
        claims: Verified claims.

    Returns:
        The user.

    Raises:
        ApiError: 401 session_revoked.
    """
    db = context.platform_db
    session = find_session(db, claims.sid)
    user = accounts.find_user(db, claims.sub)
    if (session is None or session["user_id"] != claims.sub or session["revoked_at"] is not None or user is None
            or user.get("status") != accounts.ACTIVE or user.get("token_epoch") != claims.epoch):
        raise unauthorized("session_revoked", "this session has ended; please sign in again")
    return user


async def current_user(
    request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(firm_bearer)],
) -> Principal:
    """Authenticate a signed-in user (aud=firm); the firm may still be provisioning.

    Args:
        request: Incoming request.
        credentials: Bearer credentials.

    Returns:
        The principal with the token's tenant and role.

    Raises:
        ApiError: 401 or 503.
    """
    context = get_context(request)
    claims = _verify(context, credentials, AUD_FIRM)
    _live_user(context, claims)
    structlog.contextvars.bind_contextvars(tenant_id=claims.tid, user_id=claims.sub)
    return Principal(user_id=claims.sub, tenant_id=claims.tid, role=claims.role, session_id=claims.sid, kind="user")


def _firm_gate(context: AppContext, user: Principal) -> str:
    """Refuse firm access while there is no active firm.

    Args:
        context: Application context.
        user: Signed-in principal.

    Returns:
        The tenant id.

    Raises:
        ApiError: 409 firm_provisioning, 403 no_firm or firm_suspended.
    """
    db = context.platform_db
    if user.tenant_id is None:
        if signups.has_open_signup(db, user.user_id):
            raise ApiError(409, "firm_provisioning", "your firm is still being set up")
        raise ApiError(403, "no_firm", "this account has no active firm")
    firm = accounts.find_firm(db, user.tenant_id)
    if firm is None or firm.get("status") == PROVISIONING:
        raise ApiError(409, "firm_provisioning", "your firm is still being set up")
    if firm.get("status") != accounts.ACTIVE:
        raise ApiError(403, "firm_suspended", "this firm is suspended")
    return user.tenant_id


async def firm_principal(request: Request, user: Annotated[Principal, Depends(current_user)]) -> Principal:
    """Authenticate a member of an active firm; the role comes from the live membership.

    Args:
        request: Incoming request.
        user: Signed-in principal.

    Returns:
        The firm principal.

    Raises:
        ApiError: 401, 403 or 409 as described in `_firm_gate`, 403 not_a_member.
    """
    context = get_context(request)
    tenant_id = _firm_gate(context, user)
    membership = accounts.find_membership(context.platform_db, user.user_id, tenant_id)
    if membership is None or membership.get("role") not in FIRM_ROLES:
        raise ApiError(403, "not_a_member", "you are not a member of this firm")
    return Principal(user_id=user.user_id, tenant_id=tenant_id, role=cast(Role, membership["role"]),
                     session_id=user.session_id, kind="user")


def require_role(minimum: FirmRole) -> Callable[..., Coroutine[Any, Any, Principal]]:
    """Build a dependency that admits firm members at or above a role (viewer < dispatcher < owner).

    Args:
        minimum: Lowest role allowed.

    Returns:
        The dependency, returning the firm principal.
    """
    needed = ROLE_RANK[minimum]

    async def dependency(principal: Annotated[Principal, Depends(firm_principal)]) -> Principal:
        if ROLE_RANK.get(principal.role, 0) < needed:
            raise ApiError(403, "forbidden", f"this action requires the {minimum} role")
        return principal

    return dependency


async def portal_principal(
    request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(portal_bearer)],
) -> Principal:
    """Authenticate a portal token (aud=portal) against its live scoped link, active firm and live subject.

    Args:
        request: Incoming request.
        credentials: Bearer credentials.

    Returns:
        A scoped principal whose user id is the carrier id.

    Raises:
        ApiError: 401 when the token or its link is invalid, 503 without keys.
    """
    context = get_context(request)
    claims = _verify(context, credentials, AUD_PORTAL)
    link = context.platform_db[SCOPED_LINKS].find_one({"_id": claims.sid})
    if (not link_is_live(link, context.clock()) or link is None or claims.tid is None
            or link.get("tenant_id") != claims.tid or link.get("subject", {}).get("id") != claims.sub
            or not portal_allowed(context.platform_db, context.tenant_db, link)):
        raise unauthorized("link_revoked", "this link is no longer valid")
    structlog.contextvars.bind_contextvars(tenant_id=claims.tid, user_id=claims.sub)
    return Principal(user_id=claims.sub, tenant_id=claims.tid, role=claims.role, session_id=claims.sid,
                     kind="scoped")


ACCESS_TOKEN_QUERY_MAX = 4096


async def stream_viewer(
    request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(firm_bearer)],
    access_token: Annotated[str | None, Query(max_length=ACCESS_TOKEN_QUERY_MAX, description=(
        "Access token for EventSource clients, which cannot set headers. Accepted only on the events stream; "
        "the Authorization header wins when both are sent. Redacted from logs."))] = None,
) -> Principal:
    """Authenticate a firm member on the SSE route by bearer header or `?access_token=`.

    Args:
        request: Incoming request.
        credentials: Bearer credentials.
        access_token: Token from the query string.

    Returns:
        The firm principal (any firm role).

    Raises:
        ApiError: 401, 403, 409 or 503 like every firm route.
    """
    if (credentials is None or not credentials.credentials) and access_token:
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=access_token)
    user = await current_user(request, credentials)
    return await firm_principal(request, user)


firm_idempotency = idempotency_dependency(firm_principal)

CurrentUser = Annotated[Principal, Depends(current_user)]
FirmViewer = Annotated[Principal, Depends(require_role("viewer"))]
FirmDispatcher = Annotated[Principal, Depends(require_role("dispatcher"))]
FirmOwner = Annotated[Principal, Depends(require_role("owner"))]
PortalPrincipal = Annotated[Principal, Depends(portal_principal)]
FirmIdempotency = Annotated[IdempotencyGuard, Depends(firm_idempotency)]
StreamViewer = Annotated[Principal, Depends(stream_viewer)]
