"""Refresh, logout, logout-all, switching firm, and listing or revoking the caller's sessions."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Cookie, Path, Request, Response

from manceps_core import accounts, signups
from manceps_core.mongo import Doc

from ..auth import sessions
from ..auth.issue import (
    REFRESH_COOKIE,
    LoginTarget,
    clear_refresh_cookie,
    membership_target,
    resolve_target,
    respond,
)
from ..auth.models import RefreshRequest, SessionItem, SwitchFirmRequest, TokenResponse
from ..auth.principal import CurrentUser, require_tokens, unauthorized
from ..context import AppContext, get_context
from ..errors import ApiError
from ..pagination import Page
from ..ratelimit import enforce
from ..requestinfo import client_ip, user_agent

router = APIRouter(prefix="/v1", tags=["auth"])

RATE_WINDOW = timedelta(hours=1)
REFRESH_PER_IP = 300
MAX_REFRESH_CHARS = 128
SESSION_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


@router.post("/auth/refresh", operation_id="auth_refresh", summary="Rotate the refresh token")
def auth_refresh(
    request: Request, response: Response, body: RefreshRequest | None = None,
    mc_refresh: Annotated[str | None, Cookie(alias=REFRESH_COOKIE, max_length=MAX_REFRESH_CHARS)] = None,
) -> TokenResponse:
    """Exchange a refresh token (body for native clients, mc_refresh cookie for browsers) for new tokens.

    Args:
        request: Incoming request.
        response: Outgoing response.
        body: Optional body with refresh_token.
        mc_refresh: Browser refresh cookie.

    Returns:
        New tokens; the old refresh token is spent.

    Raises:
        ApiError: 401 invalid_refresh or refresh_reuse (the family is then revoked), 429, 503.
    """
    context = get_context(request)
    require_tokens(context)
    db, now = context.platform_db, context.clock()
    ip = client_ip(request, context.settings.trust_proxy)
    enforce(db, "refresh_ip", ip, REFRESH_PER_IP, RATE_WINDOW, now)
    raw = body.refresh_token if body is not None and body.refresh_token else mc_refresh
    if not raw:
        raise unauthorized("invalid_refresh", "no refresh token was presented")
    ttl = timedelta(days=context.settings.refresh_token_days)
    try:
        session, new_raw = sessions.rotate(db, raw, now, ttl, user_agent(request), ip)
    except sessions.RefreshError as exc:
        raise unauthorized(exc.code, exc.message) from exc
    user = accounts.find_user(db, str(session["user_id"]))
    if user is None or user.get("status") != accounts.ACTIVE:
        sessions.revoke_family(db, str(session["family_id"]), now)
        raise unauthorized("invalid_refresh", "the refresh token is not valid")
    target = resolve_target(db, user, session["tenant_id"])
    if target.tenant_id != session["tenant_id"]:
        db[sessions.SESSIONS].update_one({"_id": session["_id"]}, {"$set": {"tenant_id": target.tenant_id}})
    return respond(context, request, response, user, session, new_raw, target)


@router.post("/auth/logout", status_code=204, operation_id="auth_logout", summary="End this session")
def auth_logout(request: Request, principal: CurrentUser) -> Response:
    """Revoke the caller's session family and clear the refresh cookie.

    Args:
        request: Incoming request.
        principal: Signed-in user.

    Returns:
        204 with the cookie cleared.
    """
    context = get_context(request)
    session = sessions.find_session(context.platform_db, str(principal.session_id))
    if session is not None:
        sessions.revoke_family(context.platform_db, str(session["family_id"]), context.clock())
    response = Response(status_code=204)
    clear_refresh_cookie(response, context.settings)
    return response


@router.post("/auth/logout-all", status_code=204, operation_id="auth_logout_all", summary="End every session")
def auth_logout_all(request: Request, principal: CurrentUser) -> Response:
    """Bump the token epoch (every access token dies on its next use) and revoke every session.

    Args:
        request: Incoming request.
        principal: Signed-in user.

    Returns:
        204 with the cookie cleared.
    """
    context = get_context(request)
    accounts.bump_epoch(context.platform_db, principal.user_id)
    sessions.revoke_user(context.platform_db, principal.user_id, context.clock())
    response = Response(status_code=204)
    clear_refresh_cookie(response, context.settings)
    return response


def _switch_target(context: AppContext, user_id: str, tenant_id: str | None) -> LoginTarget:
    """Find the firm to switch to.

    Args:
        context: Application context.
        user_id: Signed-in user.
        tenant_id: Requested firm, or None for the newest active membership.

    Returns:
        The target firm and role (from the membership, never from the request).

    Raises:
        ApiError: 404 when the user is not an active member, 409 firm_provisioning while the firm is being set up.
    """
    db = context.platform_db
    if tenant_id is None:
        memberships = accounts.active_memberships(db, user_id)
        if memberships:
            tenant_id = str(memberships[-1]["tenant_id"])
        elif signups.has_open_signup(db, user_id):
            raise ApiError(409, "firm_provisioning", "your firm is still being set up")
        else:
            raise ApiError(404, "not_found", "no firm to switch to")
    target = membership_target(db, user_id, tenant_id)
    if target is None:
        raise ApiError(404, "not_found", "firm not found")
    return target


@router.post("/auth/switch-firm", operation_id="auth_switch_firm", summary="Switch this session to a firm")
def auth_switch_firm(body: SwitchFirmRequest, request: Request, response: Response,
                     principal: CurrentUser) -> TokenResponse:
    """Point the current session at a firm the user belongs to and issue a firm access token.

    Args:
        body: Optional firm id (checked against the user's memberships).
        request: Incoming request.
        response: Outgoing response.
        principal: Signed-in user.

    Returns:
        A new access token for the firm; the refresh token is unchanged.

    Raises:
        ApiError: 404 or 409 as in `_switch_target`.
    """
    context = get_context(request)
    db = context.platform_db
    target = _switch_target(context, principal.user_id, body.tenant_id)
    db[sessions.SESSIONS].update_one({"_id": principal.session_id, "user_id": principal.user_id},
                                     {"$set": {"tenant_id": target.tenant_id}})
    db[accounts.USERS].update_one({"_id": principal.user_id}, {"$set": {"last_tenant_id": target.tenant_id}})
    user = accounts.find_user(db, principal.user_id)
    session = sessions.find_session(db, str(principal.session_id))
    if user is None or session is None:
        raise unauthorized("session_revoked", "this session has ended; please sign in again")
    return respond(context, request, response, user, session, None, target)


def _session_item(session: Doc, current_family: str | None) -> SessionItem:
    """Render a session.

    Args:
        session: Session document.
        current_family: Family of the caller's session.

    Returns:
        The item.
    """
    return SessionItem(id=str(session["_id"]), tenant_id=session.get("tenant_id"), created_at=session["created_at"],
                       expires_at=session["expires_at"], ua=str(session.get("ua", "")), ip=str(session.get("ip", "")),
                       current=session["family_id"] == current_family)


@router.get("/sessions", operation_id="sessions_list", summary="List my sessions", tags=["sessions"])
def sessions_list(request: Request, principal: CurrentUser) -> Page[SessionItem]:
    """List the caller's live sessions (one per device sign-in), newest first.

    Args:
        request: Incoming request.
        principal: Signed-in user.

    Returns:
        All live sessions; next_cursor is always null (the list is bounded by refresh expiry).
    """
    context = get_context(request)
    db = context.platform_db
    mine = sessions.find_session(db, str(principal.session_id))
    family = str(mine["family_id"]) if mine is not None else None
    live = sessions.active_sessions(db, principal.user_id, context.clock())
    return Page[SessionItem](items=[_session_item(session, family) for session in live], next_cursor=None)


@router.delete("/sessions/{session_id}", status_code=204, operation_id="sessions_delete",
               summary="Revoke one of my sessions", tags=["sessions"])
def sessions_delete(session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)], request: Request,
                    principal: CurrentUser) -> Response:
    """Revoke a session (its whole family) that belongs to the caller.

    Args:
        session_id: Session id.
        request: Incoming request.
        principal: Signed-in user.

    Returns:
        204.

    Raises:
        ApiError: 404 when the session is not the caller's.
    """
    context = get_context(request)
    session = sessions.find_session(context.platform_db, session_id)
    if session is None or session["user_id"] != principal.user_id:
        raise ApiError(404, "not_found", "session not found")
    sessions.revoke_family(context.platform_db, str(session["family_id"]), context.clock())
    return Response(status_code=204)
