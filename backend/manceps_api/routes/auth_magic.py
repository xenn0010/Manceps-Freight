"""Email magic-link sign-in: only with EMAIL_LOGIN_ENABLED=1 and SMTP configured, otherwise 503.

`start` always answers 202 and sends only when the address belongs to an active user, so it cannot be used to probe
which emails have accounts. Tokens are 32 random bytes, stored hashed, valid 15 minutes, and single use.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

import structlog
from fastapi import APIRouter, Request, Response
from pymongo import ReturnDocument

from manceps_core import accounts
from manceps_core.accounts import new_id

from ..auth.issue import sign_in
from ..auth.models import AcceptedResponse, MagicLinkStartRequest, SecretTokenRequest, TokenResponse
from ..auth.principal import require_tokens, unauthorized
from ..auth.sessions import hash_token
from ..context import AppContext, get_context
from ..errors import ApiError
from ..integrations.mailer import Mailer, MailError
from ..ratelimit import enforce
from ..requestinfo import client_ip

router = APIRouter(prefix="/v1", tags=["auth"])
log = structlog.get_logger(__name__)

MAGIC_LINKS = "magic_links"
MAGIC_LINK_TTL = timedelta(minutes=15)
MAGIC_TOKEN_BYTES = 32
MAGIC_LINK_PATH = "/auth/magic-link"
RATE_WINDOW = timedelta(hours=1)
START_PER_EMAIL = 3
START_PER_IP = 10
VERIFY_PER_IP = 30
SUBJECT = "Your Manceps sign-in link"
BODY_TEMPLATE = (
    "Sign in to Manceps with this link:\n\n{url}\n\n"
    "It works once and expires in 15 minutes. If you did not ask for it, you can ignore this email.\n"
)


def _mailer(context: AppContext) -> tuple[Mailer, str]:
    """Return the mailer and public base URL, or refuse with 503.

    Args:
        context: Application context.

    Returns:
        (mailer, base URL without a trailing slash).

    Raises:
        ApiError: 503 email_login_not_configured.
    """
    settings, mailer = context.settings, context.integrations.mailer
    if not settings.email_login_enabled or mailer is None or not settings.public_base_url:
        raise ApiError(503, "email_login_not_configured", "email sign-in is not available")
    return mailer, settings.public_base_url.rstrip("/")


@router.post("/auth/magic-link/start", status_code=202, operation_id="auth_magic_link_start",
             summary="Email a sign-in link")
def auth_magic_link_start(body: MagicLinkStartRequest, request: Request) -> AcceptedResponse:
    """Email a single-use sign-in link if the address belongs to an active user.

    Args:
        body: The email address.
        request: Incoming request.

    Returns:
        {"accepted": true} whether or not an email was sent.

    Raises:
        ApiError: 503 when email sign-in is not configured, 429 over the limits.
    """
    context = get_context(request)
    mailer, base_url = _mailer(context)
    db, now = context.platform_db, context.clock()
    enforce(db, "magic_start_ip", client_ip(request, context.settings.trust_proxy), START_PER_IP, RATE_WINDOW, now)
    enforce(db, "magic_start_email", body.email, START_PER_EMAIL, RATE_WINDOW, now)
    user = db[accounts.USERS].find_one({"email": body.email, "status": accounts.ACTIVE})
    if user is None:
        return AcceptedResponse(accepted=True)
    raw = secrets.token_urlsafe(MAGIC_TOKEN_BYTES)
    db[MAGIC_LINKS].insert_one({"_id": new_id("mgl"), "token_hash": hash_token(raw), "user_id": user["_id"],
                                "created_at": now, "expires_at": now + MAGIC_LINK_TTL, "used_at": None})
    try:
        mailer.send(body.email, SUBJECT, BODY_TEMPLATE.format(url=f"{base_url}{MAGIC_LINK_PATH}?token={raw}"))
    except MailError as exc:
        log.error("magic_link.send_failed", error_type=type(exc).__name__)
    return AcceptedResponse(accepted=True)


@router.post("/auth/magic-link/verify", operation_id="auth_magic_link_verify", summary="Sign in with a link")
def auth_magic_link_verify(body: SecretTokenRequest, request: Request, response: Response) -> TokenResponse:
    """Spend a magic-link token and sign the user in.

    Args:
        body: The token from the link.
        request: Incoming request.
        response: Outgoing response.

    Returns:
        Tokens.

    Raises:
        ApiError: 503 when not configured, 429, 400 invalid_token for unknown, used or expired tokens, 401 when the
            account is disabled.
    """
    context = get_context(request)
    _mailer(context)
    require_tokens(context)
    db, now = context.platform_db, context.clock()
    enforce(db, "magic_verify_ip", client_ip(request, context.settings.trust_proxy), VERIFY_PER_IP, RATE_WINDOW, now)
    link = db[MAGIC_LINKS].find_one_and_update(
        {"token_hash": hash_token(body.token), "used_at": None, "expires_at": {"$gt": now}},
        {"$set": {"used_at": now}}, return_document=ReturnDocument.AFTER,
    )
    if link is None:
        raise ApiError(400, "invalid_token", "this sign-in link is invalid or has expired")
    user = accounts.find_user(db, str(link["user_id"]))
    if user is None or user.get("status") != accounts.ACTIVE:
        raise unauthorized("account_disabled", "this account is disabled")
    return sign_in(context, request, response, user)
