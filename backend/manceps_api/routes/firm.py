"""The firm: profile, provisioning status, integration status and the audit log."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from zoneinfo import available_timezones

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator, model_validator

from manceps_core import accounts, signups
from manceps_core.audit import AUDIT
from manceps_core.mongo import Doc
from manceps_core.tenancy import Principal

from .. import auditing
from ..auth.models import StrictModel, normalize_firm_name
from ..auth.principal import CurrentUser, FirmOwner, FirmViewer
from ..context import AppContext, get_context
from ..errors import ApiError
from ..pagination import DEFAULT_LIMIT, CursorQuery, LimitQuery, Page, decode_cursor, encode_cursor

router = APIRouter(prefix="/v1", tags=["firm"])

TIMEZONES: frozenset[str] = frozenset(available_timezones())
FIRM_FIELDS = ("name", "timezone")
FAILED_MESSAGE = "We could not set up your firm. Please try signing up again."

ProvisioningState = Literal["none", "pending", "provisioning", "ready", "failed"]
IntegrationState = Literal["not_configured", "ready"]


class Firm(BaseModel):
    """Firm profile."""

    id: str
    name: str
    slug: str
    status: str
    plan: str
    timezone: str
    owner_user_id: str
    created_at: datetime


class FirmPatch(StrictModel):
    """Firm profile changes (owner only)."""

    name: str | None = Field(default=None, max_length=200)
    timezone: str | None = Field(default=None, max_length=64)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return None if value is None else normalize_firm_name(value)

    @field_validator("timezone")
    @classmethod
    def _timezone(cls, value: str | None) -> str | None:
        if value is not None and value not in TIMEZONES:
            raise ValueError("unknown IANA timezone")
        return value

    @model_validator(mode="after")
    def _not_empty(self) -> FirmPatch:
        if self.name is None and self.timezone is None:
            raise ValueError("send at least one of name, timezone")
        return self


class Provisioning(BaseModel):
    """Where the caller's latest signup stands; `ready` means the firm is active and switch-firm will work."""

    status: ProvisioningState
    tenant_id: str | None
    message: str | None


class IntegrationStatus(BaseModel):
    """One external service."""

    name: str
    status: IntegrationState


class IntegrationList(BaseModel):
    """Every external service the platform uses."""

    items: list[IntegrationStatus]


class AuditItem(BaseModel):
    """One audit record (state is stored as hashes only)."""

    id: str
    event: str
    at: datetime
    who: dict[str, Any] | None
    ref: dict[str, Any] | None
    request_id: str | None
    session_id: str | None
    before_hash: str | None
    after_hash: str | None


def _firm_doc(context: AppContext, principal: Principal) -> Doc:
    """Load the principal's firm row.

    Args:
        context: Application context.
        principal: Firm principal.

    Returns:
        The firm.

    Raises:
        ApiError: 404 if it vanished.
    """
    firm = accounts.find_firm(context.platform_db, str(principal.tenant_id))
    if firm is None:
        raise ApiError(404, "not_found", "firm not found")
    return firm


def _render(firm: Doc) -> Firm:
    """Render a firm row.

    Args:
        firm: Firm document.

    Returns:
        The model.
    """
    return Firm(id=str(firm["_id"]), name=str(firm["name"]), slug=str(firm["slug"]), status=str(firm["status"]),
                plan=str(firm["plan"]), timezone=str(firm["timezone"]), owner_user_id=str(firm["owner_user_id"]),
                created_at=firm["created_at"])


@router.get("/firm", operation_id="firm_get", summary="The current firm")
def firm_get(request: Request, principal: FirmViewer) -> Firm:
    """Return the caller's firm.

    Args:
        request: Incoming request.
        principal: Firm member.

    Returns:
        The firm.
    """
    return _render(_firm_doc(get_context(request), principal))


@router.patch("/firm", operation_id="firm_update", summary="Update the firm")
def firm_update(body: FirmPatch, request: Request, principal: FirmOwner) -> Firm:
    """Change the firm's name or timezone (audited).

    Args:
        body: Fields to change.
        request: Incoming request.
        principal: Firm owner.

    Returns:
        The updated firm.
    """
    context = get_context(request)
    firm = _firm_doc(context, principal)
    before = {field: firm.get(field) for field in FIRM_FIELDS}
    changes = body.model_dump(exclude_none=True)
    context.platform_db[accounts.FIRMS].update_one({"_id": principal.tenant_id}, {"$set": changes})
    after = {**before, **changes}
    auditing.record(request, principal, "firm.update", {"type": "firm", "id": principal.tenant_id}, before, after)
    return _render({**firm, **changes})


@router.get("/firm/provisioning", operation_id="firm_provisioning_get", summary="Signup provisioning status")
def firm_provisioning_get(request: Request, principal: CurrentUser) -> Provisioning:
    """Report the caller's latest signup; poll until `ready`, then call /v1/auth/switch-firm.

    Args:
        request: Incoming request.
        principal: Signed-in user.

    Returns:
        The provisioning status.
    """
    db = get_context(request).platform_db
    signup = signups.latest_for_user(db, principal.user_id)
    if signup is None:
        return Provisioning(status="none", tenant_id=None, message=None)
    status = signup.get("status")
    if status == signups.FAILED:
        return Provisioning(status="failed", tenant_id=None, message=FAILED_MESSAGE)
    if status == signups.PENDING:
        return Provisioning(status="pending", tenant_id=None, message=None)
    tenant_id = signup.get("tenant_id")
    firm = accounts.find_firm(db, str(tenant_id)) if status == signups.READY and tenant_id else None
    if firm is not None and firm.get("status") == accounts.ACTIVE:
        return Provisioning(status="ready", tenant_id=str(tenant_id), message=None)
    return Provisioning(status="provisioning", tenant_id=None, message=None)


@router.get("/integrations", operation_id="integrations_list", summary="External service status")
def integrations_list(request: Request, principal: FirmViewer) -> IntegrationList:
    """Report which external services are configured (never their credentials).

    Args:
        request: Incoming request.
        principal: Firm member.

    Returns:
        Status per service.
    """
    del principal
    context = get_context(request)
    settings = context.settings
    configured = {
        "twilio_verify": context.integrations.verifier is not None,
        "smtp": context.integrations.mailer is not None and settings.email_login_enabled,
        "fmcsa": settings.fmcsa_webkey is not None,
        "eia": settings.eia_api_key is not None,
        "google_routes": settings.google_maps_api_key is not None,
        "ors": settings.ors_api_key is not None,
    }
    return IntegrationList(items=[IntegrationStatus(name=name, status="ready" if ready else "not_configured")
                                  for name, ready in configured.items()])


@router.get("/audit", operation_id="audit_list", summary="Firm audit log")
def audit_list(request: Request, principal: FirmOwner, limit: LimitQuery = DEFAULT_LIMIT,
               cursor: CursorQuery = None) -> Page[AuditItem]:
    """List the firm's audit records, newest first.

    Args:
        request: Incoming request.
        principal: Firm owner.
        limit: Page size.
        cursor: Cursor from the previous page.

    Returns:
        One page.

    Raises:
        ApiError: 400 invalid_cursor.
    """
    after = decode_cursor(cursor)
    firm_db = get_context(request).tenant_db.for_principal(principal)
    query: dict[str, Any] = {"_id": {"$lt": after}} if after is not None else {}
    docs = list(firm_db[AUDIT].find(query, limit=limit + 1).sort([("_id", -1)]))
    page = docs[:limit]
    items = [AuditItem(id=str(doc["_id"]), event=str(doc.get("event")), at=doc["at"], who=doc.get("who"),
                       ref=doc.get("ref"), request_id=doc.get("request_id"), session_id=doc.get("session_id"),
                       before_hash=doc.get("before_hash"), after_hash=doc.get("after_hash")) for doc in page]
    next_cursor = encode_cursor(page[-1]["_id"]) if len(docs) > limit else None
    return Page[AuditItem](items=items, next_cursor=next_cursor)
