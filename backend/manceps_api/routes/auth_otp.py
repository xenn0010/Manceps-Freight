"""Phone OTP sign-in and signup (`/v1/auth/otp/*`) and the public signup status poll.

Fails closed like signup-api: no verifier is 503, a verifier outage is 502, and only an approved code signs in.
Limits (signup-api constants): 3 sends per phone and 10 per IP per hour, 10 checks per phone per hour, plus
CHECK_PER_IP checks per IP. Verify never reveals whether a phone has an account: the limits and the code are checked
before the account lookup, a wrong code is the same 400 for every phone, and only after an approved code does an
unknown phone learn it needs signup details (with a single-use signup ticket, so the spent code is not wasted).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, cast

from fastapi import APIRouter, Path, Request, Response
from pymongo.errors import DuplicateKeyError

from manceps_core import accounts, signups
from manceps_core.mongo import Doc

from ..auth.issue import sign_in
from ..auth.models import OtpStartRequest, OtpVerifyRequest, SentResponse, SignupStatus, TokenResponse
from ..auth.principal import require_tokens
from ..auth.signup_tickets import issue_ticket, redeem_ticket
from ..context import AppContext, get_context
from ..errors import ApiError
from ..integrations.twilio_verify import Verifier, VerifyError
from ..ratelimit import enforce
from ..requestinfo import client_ip

router = APIRouter(prefix="/v1", tags=["auth"])

RATE_WINDOW = timedelta(hours=1)
SEND_PER_PHONE = 3
SEND_PER_IP = 10
CHECK_PER_PHONE = 10
CHECK_PER_IP = 60
SIGNUP_STATUS_PER_IP = 120
SIGNUP_TOKEN_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"  # noqa: S105 - a regex, not a secret
FAILED_MESSAGE = "We could not set up your firm. Please try signing up again."
ALREADY_SIGNED_UP = "a firm already exists for this phone number"
SIGNUP_STATES = frozenset({"pending", "provisioning", "ready", "failed"})


def _verifier(context: AppContext) -> Verifier:
    """Return the phone verifier or refuse with 503.

    Args:
        context: Application context.

    Returns:
        The verifier.

    Raises:
        ApiError: 503 twilio_not_configured.
    """
    if context.integrations.verifier is None:
        raise ApiError(503, "twilio_not_configured", "phone sign-in is temporarily unavailable")
    return context.integrations.verifier


@router.post("/auth/otp/start", status_code=202, operation_id="auth_otp_start", summary="Send a sign-in code")
def auth_otp_start(body: OtpStartRequest, request: Request) -> SentResponse:
    """Text a one-time code to a phone.

    Args:
        body: The phone.
        request: Incoming request.

    Returns:
        {"sent": true}.

    Raises:
        ApiError: 503 without Twilio, 429 over the limits, 502 when Twilio fails.
    """
    context = get_context(request)
    verifier = _verifier(context)
    db, now = context.platform_db, context.clock()
    enforce(db, "otp_send_ip", client_ip(request, context.settings), SEND_PER_IP, RATE_WINDOW, now)
    enforce(db, "otp_send_phone", body.phone, SEND_PER_PHONE, RATE_WINDOW, now)
    try:
        verifier.send(body.phone)
    except VerifyError as exc:
        raise ApiError(502, "verify_unavailable", "could not send the code; try again") from exc
    return SentResponse(sent=True)


def _sign_up(context: AppContext, request: Request, body: OtpVerifyRequest) -> tuple[Doc, str]:
    """Create the user and queue the firm for a verified new phone.

    Args:
        context: Application context.
        request: Incoming request.
        body: Verified request with signup fields.

    Returns:
        (user, signup status token).

    Raises:
        ApiError: 409 already_signed_up when the phone already has a firm or a signup.
    """
    db, now = context.platform_db, context.clock()
    if db[signups.SIGNUPS].count_documents({"phone": body.phone, "status": {"$ne": signups.FAILED}}, limit=1):
        raise ApiError(409, "already_signed_up", ALREADY_SIGNED_UP)
    try:
        user = accounts.create_user(db, now, phone=body.phone)
    except DuplicateKeyError as exc:
        raise ApiError(409, "already_signed_up", ALREADY_SIGNED_UP) from exc
    firm_name = cast(str, body.firm_name)
    try:
        token = signups.enqueue(db, body.phone, firm_name, client_ip(request, context.settings),
                                str(user["_id"]), now)
    except signups.AlreadySignedUp as exc:
        db[accounts.USERS].delete_one({"_id": user["_id"]})
        raise ApiError(409, "already_signed_up", ALREADY_SIGNED_UP) from exc
    return user, token


def _prove_phone(context: AppContext, verifier: Verifier, body: OtpVerifyRequest) -> None:
    """Check the code, or spend the signup ticket an earlier approved code earned.

    Args:
        context: Application context.
        verifier: Phone verifier.
        body: Verify request (exactly one of code and signup_ticket).

    Raises:
        ApiError: 400 invalid_code or invalid_ticket, 502 when the verifier fails.
    """
    if body.signup_ticket is not None:
        if not redeem_ticket(context.platform_db, body.signup_ticket, body.phone, context.clock()):
            raise ApiError(400, "invalid_ticket", "this signup ticket is invalid, used or expired")
        return
    try:
        approved = verifier.check(body.phone, cast(str, body.code))
    except VerifyError as exc:
        raise ApiError(502, "verify_unavailable", "could not check the code; try again") from exc
    if not approved:
        raise ApiError(400, "invalid_code", "wrong or expired code")


def _signup_details_required(context: AppContext, phone: str) -> ApiError:
    """Ask a verified new phone for the signup fields, handing back a ticket so its code is not wasted.

    Args:
        context: Application context.
        phone: Verified E.164 phone.

    Returns:
        The 422 to raise.
    """
    ticket, expires_in = issue_ticket(context.platform_db, phone, context.clock())
    return ApiError(422, "signup_details_required", "new accounts need firm_name and accept_terms",
                    {"fields": ["firm_name", "accept_terms"], "signup_ticket": ticket, "expires_in": expires_in})


@router.post("/auth/otp/verify", operation_id="auth_otp_verify", summary="Sign in or sign up with a code")
def auth_otp_verify(body: OtpVerifyRequest, request: Request, response: Response) -> TokenResponse:
    """Check a code (or signup ticket); sign in an existing user, or create the user and queue the firm.

    Args:
        body: Phone, code or signup_ticket, and for a new phone firm_name and accept_terms.
        request: Incoming request.
        response: Outgoing response (refresh cookie for browsers).

    Returns:
        Tokens; a new signup gets tid=null, role=owner, state=provisioning and a signup_token.

    Raises:
        ApiError: 503 without Twilio or JWT keys, 429, 400 invalid_code or invalid_ticket, 502, 422
            signup_details_required (only after an approved code, with details.signup_ticket), 409.
    """
    context = get_context(request)
    verifier = _verifier(context)
    require_tokens(context)
    db, now = context.platform_db, context.clock()
    enforce(db, "otp_check_ip", client_ip(request, context.settings), CHECK_PER_IP, RATE_WINDOW, now)
    enforce(db, "otp_check_phone", body.phone, CHECK_PER_PHONE, RATE_WINDOW, now)
    _prove_phone(context, verifier, body)
    user = db[accounts.USERS].find_one({"phone": body.phone})
    signup_token: str | None = None
    if user is None:
        if body.firm_name is None or body.accept_terms is not True:
            raise _signup_details_required(context, body.phone)
        user, signup_token = _sign_up(context, request, body)
    if user.get("status") != accounts.ACTIVE:
        raise ApiError(401, "account_disabled", "this account is disabled", headers={"WWW-Authenticate": "Bearer"})
    return sign_in(context, request, response, user, signup_token)


@router.get("/signup/status/{token}", operation_id="signup_status_get", summary="Poll a signup")
def signup_status_get(token: Annotated[str, Path(pattern=SIGNUP_TOKEN_PATTERN)], request: Request) -> SignupStatus:
    """Report a signup's status by its unguessable token (public, rate limited per IP).

    Args:
        token: Signup status token.
        request: Incoming request.

    Returns:
        Status, the tenant id once ready, and a message when failed.

    Raises:
        ApiError: 404 for an unknown token, 429 over the limit.
    """
    context = get_context(request)
    db = context.platform_db
    enforce(db, "signup_status_ip", client_ip(request, context.settings), SIGNUP_STATUS_PER_IP,
            RATE_WINDOW, context.clock())
    doc = signups.find_status(db, token)
    if doc is None:
        raise ApiError(404, "not_found", "unknown signup")
    status = str(doc.get("status"))
    if status == signups.FAILED:
        return SignupStatus(status="failed", tenant_id=None, message=FAILED_MESSAGE)
    if status not in SIGNUP_STATES:
        status = "provisioning"
    tenant_id = doc.get("tenant_id") if status == signups.READY else None
    return SignupStatus.model_validate({"status": status, "tenant_id": tenant_id})
