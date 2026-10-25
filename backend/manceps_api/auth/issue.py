"""Turn a verified user into a session and tokens: pick the firm, create the session, set the refresh cookie.

Browser clients (no `X-Client: native`) receive the refresh token only in the `mc_refresh` cookie
(HttpOnly; Secure; SameSite=Lax; Path=/v1/auth); native clients receive it in the body.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import cast

from fastapi import Request, Response

from manceps_core import accounts, signups
from manceps_core.mongo import Doc, MongoDb
from manceps_core.tenancy import Role

from ..context import AppContext
from ..requestinfo import client_ip, user_agent
from ..settings import Settings
from .models import LoginState, TokenResponse
from .principal import FIRM_ROLES, require_tokens
from .sessions import create_session
from .tokens import AUD_FIRM

REFRESH_COOKIE = "mc_refresh"
REFRESH_COOKIE_PATH = "/v1/auth"
CLIENT_HEADER = "X-Client"
NATIVE_CLIENT = "native"
SECONDS_PER_DAY = 86_400


@dataclass(frozen=True)
class LoginTarget:
    """Which firm (if any) a session's access tokens are for, and with which role."""

    tenant_id: str | None
    role: Role
    state: LoginState


def membership_target(db: MongoDb, user_id: str, tenant_id: str) -> LoginTarget | None:
    """Return the target for a firm the user actively belongs to.

    Args:
        db: Platform database.
        user_id: User id.
        tenant_id: Firm id.

    Returns:
        The target, or None when the user is not an active member of an active firm.
    """
    membership = accounts.find_membership(db, user_id, tenant_id)
    firm = accounts.find_firm(db, tenant_id)
    if membership is None or firm is None or firm.get("status") != accounts.ACTIVE:
        return None
    if membership.get("role") not in FIRM_ROLES:
        return None
    return LoginTarget(tenant_id, cast(Role, membership["role"]), "active")


def resolve_target(db: MongoDb, user: Doc, preferred_tenant: str | None) -> LoginTarget:
    """Pick the firm for a session.

    Args:
        db: Platform database.
        user: User document.
        preferred_tenant: Firm the session already had, kept when still valid.

    Returns:
        The preferred firm, else the default membership, else provisioning (role owner) or no firm (role viewer).
    """
    user_id = str(user["_id"])
    if preferred_tenant is not None:
        kept = membership_target(db, user_id, preferred_tenant)
        if kept is not None:
            return kept
    membership = accounts.default_membership(db, user)
    if membership is not None:
        return LoginTarget(str(membership["tenant_id"]), cast(Role, membership["role"]), "active")
    if signups.has_open_signup(db, user_id):
        return LoginTarget(None, "owner", "provisioning")
    return LoginTarget(None, "viewer", "no_firm")


def is_native(request: Request) -> bool:
    """Tell native clients (refresh token in the body) from browsers (cookie).

    Args:
        request: Incoming request.

    Returns:
        True when X-Client is "native".
    """
    return request.headers.get(CLIENT_HEADER, "").lower() == NATIVE_CLIENT


def set_refresh_cookie(response: Response, settings: Settings, raw: str) -> None:
    """Set the browser refresh cookie.

    Args:
        response: Outgoing response.
        settings: Application settings.
        raw: Refresh token.
    """
    response.set_cookie(REFRESH_COOKIE, raw, max_age=settings.refresh_token_days * SECONDS_PER_DAY,
                        path=REFRESH_COOKIE_PATH, domain=settings.cookie_domain, secure=True, httponly=True,
                        samesite="lax")


def clear_refresh_cookie(response: Response, settings: Settings) -> None:
    """Remove the browser refresh cookie.

    Args:
        response: Outgoing response.
        settings: Application settings.
    """
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, domain=settings.cookie_domain, secure=True,
                           httponly=True, samesite="lax")


def respond(context: AppContext, request: Request, response: Response, user: Doc, session: Doc,
            raw_refresh: str | None, target: LoginTarget, signup_token: str | None = None) -> TokenResponse:
    """Sign an access token for a session and deliver the refresh token.

    Args:
        context: Application context.
        request: Incoming request.
        response: Outgoing response (receives the cookie).
        user: User document.
        session: Session document.
        raw_refresh: New refresh token, or None when it did not change.
        target: Firm and role.
        signup_token: Signup status token after a new signup.

    Returns:
        The token response.

    Raises:
        ApiError: 503 when JWT keys are not configured.
    """
    issued = require_tokens(context).issue(sub=str(user["_id"]), tid=target.tenant_id, role=target.role,
                                           sid=str(session["_id"]), epoch=int(user["token_epoch"]),
                                           audience=AUD_FIRM)
    native = is_native(request)
    if raw_refresh is not None and not native:
        set_refresh_cookie(response, context.settings, raw_refresh)
    return TokenResponse(access_token=issued.token, expires_in=issued.expires_in,
                         refresh_token=raw_refresh if native else None, session_id=str(session["_id"]),
                         user_id=str(user["_id"]), tenant_id=target.tenant_id, role=target.role, state=target.state,
                         signup_token=signup_token)


def sign_in(context: AppContext, request: Request, response: Response, user: Doc,
            signup_token: str | None = None) -> TokenResponse:
    """Start a new session for a verified user.

    Args:
        context: Application context.
        request: Incoming request.
        response: Outgoing response.
        user: Verified user.
        signup_token: Signup status token after a new signup.

    Returns:
        The token response.

    Raises:
        ApiError: 503 when JWT keys are not configured.
    """
    require_tokens(context)
    db, now = context.platform_db, context.clock()
    target = resolve_target(db, user, None)
    db[accounts.USERS].update_one({"_id": user["_id"]}, {"$set": {"last_login_at": now}})
    ttl = timedelta(days=context.settings.refresh_token_days)
    session, raw = create_session(db, str(user["_id"]), target.tenant_id, now, ttl, user_agent(request),
                                  client_ip(request, context.settings.trust_proxy))
    return respond(context, request, response, user, session, raw, target, signup_token)
