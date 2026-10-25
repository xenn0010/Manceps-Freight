"""Team management: members, invitations (hashed `mci_` tokens, 7 days) and accepting them.

Per-firm rows are reached only through `PlatformRepo` bound to the caller's firm, or, when accepting, to the firm named
by the stored invitation. The firm always keeps at least one owner.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, Path, Request, Response
from pydantic import BaseModel, Field, field_validator, model_validator
from pymongo.errors import DuplicateKeyError

from manceps_core import accounts
from manceps_core.mongo import Doc
from manceps_core.phones import normalize_phone
from manceps_core.tenancy import PlatformRepo, Principal

from .. import auditing
from ..auth.models import EMAIL_MAX, SecretTokenRequest, StrictModel, normalize_email
from ..auth.principal import CurrentUser, FirmOwner, FirmViewer, firm_idempotency
from ..auth.sessions import hash_token
from ..context import get_context
from ..errors import ApiError
from ..idempotency import IdempotencyGuard
from ..pagination import DEFAULT_LIMIT, CursorQuery, LimitQuery, Page, decode_cursor, encode_cursor
from ..ratelimit import enforce

router = APIRouter(prefix="/v1", tags=["team"])

INVITATIONS = "invitations"
INVITATION_TTL = timedelta(days=7)
INVITE_TOKEN_PREFIX = "mci_"  # noqa: S105 - a public prefix, not a secret
INVITE_TOKEN_BYTES = 32
ACCEPT_PATH = "/invitations/accept"
ACCEPT_PER_USER = 20
RATE_WINDOW = timedelta(hours=1)
PENDING, ACCEPTED, REVOKED = "pending", "accepted", "revoked"
REMOVING = "removing"
OWNER = "owner"
USER_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
OBJECT_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"

FirmRoleName = Literal["owner", "dispatcher", "viewer"]
IdempotencyDep = Annotated[IdempotencyGuard, Depends(firm_idempotency)]


class Member(BaseModel):
    """A firm member."""

    user_id: str
    name: str | None
    phone: str | None
    email: str | None
    role: str
    status: str
    created_at: datetime


class MemberPatch(StrictModel):
    """Role change."""

    role: FirmRoleName


class InvitationCreate(StrictModel):
    """Invite someone by email and/or phone."""

    email: str | None = Field(default=None, max_length=EMAIL_MAX)
    phone: str | None = Field(default=None, max_length=32)
    role: FirmRoleName

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        return None if value is None else normalize_email(value)

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        return None if value is None else normalize_phone(value)

    @model_validator(mode="after")
    def _identified(self) -> InvitationCreate:
        if self.email is None and self.phone is None:
            raise ValueError("an invitation needs an email or a phone")
        return self


class Invitation(BaseModel):
    """A pending or past invitation (the token is never listed)."""

    id: str
    email: str | None
    phone: str | None
    role: str
    status: str
    created_at: datetime
    expires_at: datetime


class InvitationCreated(Invitation):
    """A new invitation; `token` is shown once (null on an idempotent replay, where it is not stored)."""

    token: str | None
    accept_url: str | None


class AcceptResult(BaseModel):
    """The firm joined; call /v1/auth/switch-firm to use it."""

    tenant_id: str
    role: str


def _repo(request: Request, principal: Principal) -> PlatformRepo:
    """Return the platform repo confined to the caller's firm.

    Args:
        request: Incoming request.
        principal: Firm principal.

    Returns:
        The repo.
    """
    return PlatformRepo.for_principal(get_context(request).platform_db, principal)


def _invitation(doc: Doc) -> Invitation:
    """Render an invitation.

    Args:
        doc: Invitation document.

    Returns:
        The model.
    """
    return Invitation(id=str(doc["_id"]), email=doc.get("email"), phone=doc.get("phone"), role=str(doc["role"]),
                      status=str(doc["status"]), created_at=doc["created_at"], expires_at=doc["expires_at"])


def _object_id(raw: str) -> ObjectId:
    """Parse an id from a path, treating malformed ids as not found.

    Args:
        raw: Path value.

    Returns:
        The ObjectId.

    Raises:
        ApiError: 404 when malformed.
    """
    if not ObjectId.is_valid(raw):
        raise ApiError(404, "not_found", "not found")
    return ObjectId(raw)


@router.get("/members", operation_id="members_list", summary="List members")
def members_list(request: Request, principal: FirmViewer, limit: LimitQuery = DEFAULT_LIMIT,
                 cursor: CursorQuery = None) -> Page[Member]:
    """List the firm's members, oldest first.

    Args:
        request: Incoming request.
        principal: Firm member.
        limit: Page size.
        cursor: Cursor from the previous page.

    Returns:
        One page.

    Raises:
        ApiError: 400 invalid_cursor.
    """
    after = decode_cursor(cursor)
    query: dict[str, Any] = {"status": accounts.ACTIVE, **({"_id": {"$gt": after}} if after is not None else {})}
    docs = _repo(request, principal).find(accounts.MEMBERSHIPS, query, sort=[("_id", 1)], limit=limit + 1)
    page = docs[:limit]
    users = {user["_id"]: user for user in get_context(request).platform_db[accounts.USERS].find(
        {"_id": {"$in": [doc["user_id"] for doc in page]}})}
    items = [Member(user_id=str(doc["user_id"]), name=users.get(doc["user_id"], {}).get("name"),
                    phone=users.get(doc["user_id"], {}).get("phone"), email=users.get(doc["user_id"], {}).get("email"),
                    role=str(doc["role"]), status=str(doc["status"]), created_at=doc["created_at"]) for doc in page]
    return Page[Member](items=items, next_cursor=encode_cursor(page[-1]["_id"]) if len(docs) > limit else None)


@router.post("/members/invitations", status_code=201, operation_id="invitations_create", summary="Invite a member")
def invitations_create(body: InvitationCreate, request: Request, principal: FirmOwner,
                       guard: IdempotencyDep) -> InvitationCreated:
    """Create an invitation and return its one-time token and accept URL (sending it is up to the owner).

    Args:
        body: Who to invite and with which role.
        request: Incoming request.
        principal: Firm owner.
        guard: Idempotency guard (Idempotency-Key header optional).

    Returns:
        The invitation with its token.
    """
    context = get_context(request)
    now = context.clock()
    raw = INVITE_TOKEN_PREFIX + secrets.token_urlsafe(INVITE_TOKEN_BYTES)
    doc: Doc = {"_id": ObjectId(), "token_hash": hash_token(raw), "role": body.role, "status": PENDING,
                "invited_by": principal.user_id, "created_at": now, "expires_at": now + INVITATION_TTL}
    doc.update({key: value for key, value in (("email", body.email), ("phone", body.phone)) if value is not None})
    _repo(request, principal).insert_one(INVITATIONS, doc)
    auditing.record(request, principal, "invitation.create", {"type": "invitation", "id": str(doc["_id"])}, None,
                    {"role": body.role, "email": body.email, "phone": body.phone})
    base = context.settings.public_base_url
    accept_url = f"{base.rstrip('/')}{ACCEPT_PATH}?token={raw}" if base else None
    created = InvitationCreated(**_invitation(doc).model_dump(), token=raw, accept_url=accept_url)
    guard.save(201, created.model_copy(update={"token": None, "accept_url": None}).model_dump(mode="json"))
    return created


@router.get("/members/invitations", operation_id="invitations_list", summary="List pending invitations")
def invitations_list(request: Request, principal: FirmOwner, limit: LimitQuery = DEFAULT_LIMIT,
                     cursor: CursorQuery = None) -> Page[Invitation]:
    """List the firm's pending, unexpired invitations, oldest first.

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
    query: dict[str, Any] = {"status": PENDING, "expires_at": {"$gt": get_context(request).clock()}}
    if after is not None:
        query["_id"] = {"$gt": after}
    docs = _repo(request, principal).find(INVITATIONS, query, sort=[("_id", 1)], limit=limit + 1)
    page = docs[:limit]
    return Page[Invitation](items=[_invitation(doc) for doc in page],
                            next_cursor=encode_cursor(page[-1]["_id"]) if len(docs) > limit else None)


@router.delete("/members/invitations/{invitation_id}", status_code=204, operation_id="invitations_delete",
               summary="Revoke an invitation")
def invitations_delete(invitation_id: Annotated[str, Path(pattern=OBJECT_ID_PATTERN)], request: Request,
                       principal: FirmOwner) -> Response:
    """Revoke a pending invitation of the caller's firm.

    Args:
        invitation_id: Invitation id.
        request: Incoming request.
        principal: Firm owner.

    Returns:
        204.

    Raises:
        ApiError: 404 when it is not a pending invitation of this firm.
    """
    oid = _object_id(invitation_id)
    matched = _repo(request, principal).update_one(
        INVITATIONS, {"_id": oid, "status": PENDING},
        {"$set": {"status": REVOKED, "revoked_at": get_context(request).clock()}})
    if matched == 0:
        raise ApiError(404, "not_found", "invitation not found")
    auditing.record(request, principal, "invitation.revoke", {"type": "invitation", "id": invitation_id},
                    {"status": PENDING}, {"status": REVOKED})
    return Response(status_code=204)


def _check_identity(invitation: Doc, user: Doc) -> None:
    """Require the accepting user to match the invitation's phone or its email, and an email only once verified.

    Args:
        invitation: Invitation document.
        user: Accepting user.

    Raises:
        ApiError: 403 email_not_verified when only an unverified email matches, else 403 invitation_mismatch.
    """
    phone, email = invitation.get("phone"), invitation.get("email")
    if phone is not None and phone == user.get("phone"):
        return
    if email is not None and email == user.get("email"):
        if user.get("email_verified_at") is not None:
            return
        raise ApiError(403, "email_not_verified", "verify this email address with a sign-in link first")
    raise ApiError(403, "invitation_mismatch", "this invitation was sent to someone else")


@router.post("/invitations/accept", operation_id="invitations_accept", summary="Accept an invitation")
def invitations_accept(body: SecretTokenRequest, request: Request, principal: CurrentUser) -> AcceptResult:
    """Join the firm that issued an invitation; the signed-in user's email or phone must match it.

    Args:
        body: Invitation token.
        request: Incoming request.
        principal: Signed-in user.

    Returns:
        The firm and role; switch to it with /v1/auth/switch-firm.

    Raises:
        ApiError: 404 unknown, used or expired; 403 invitation_mismatch or email_not_verified; 409 already_member;
            429.
    """
    context = get_context(request)
    db, now = context.platform_db, context.clock()
    enforce(db, "invite_accept_user", principal.user_id, ACCEPT_PER_USER, RATE_WINDOW, now)
    invitation = db[INVITATIONS].find_one({"token_hash": hash_token(body.token), "status": PENDING,
                                           "expires_at": {"$gt": now}})
    user = accounts.find_user(db, principal.user_id)
    if invitation is None or user is None:
        raise ApiError(404, "not_found", "invitation not found or expired")
    _check_identity(invitation, user)
    repo = PlatformRepo(db, str(invitation["tenant_id"]))
    if repo.find_one(accounts.MEMBERSHIPS, {"user_id": principal.user_id}) is not None:
        raise ApiError(409, "already_member", "you are already a member of this firm")
    claimed = repo.update_one(INVITATIONS, {"_id": invitation["_id"], "status": PENDING},
                              {"$set": {"status": ACCEPTED, "accepted_by": principal.user_id, "accepted_at": now}})
    if claimed == 0:
        raise ApiError(404, "not_found", "invitation not found or expired")
    try:
        repo.insert_one(accounts.MEMBERSHIPS, {"user_id": principal.user_id, "role": invitation["role"],
                                               "status": accounts.ACTIVE, "created_at": now, "updated_at": now})
    except DuplicateKeyError as exc:
        raise ApiError(409, "already_member", "you are already a member of this firm") from exc
    member = Principal(user_id=principal.user_id, tenant_id=repo.tenant_id, role=invitation["role"],
                       session_id=principal.session_id, kind="user")
    auditing.record(request, member, "invitation.accept", {"type": "invitation", "id": str(invitation["_id"])},
                    {"status": PENDING}, {"status": ACCEPTED, "user_id": principal.user_id})
    return AcceptResult(tenant_id=repo.tenant_id, role=str(invitation["role"]))


def _active_member(repo: PlatformRepo, user_id: str) -> Doc:
    """Load an active membership of the repo's firm.

    Args:
        repo: Firm-confined repo.
        user_id: Member's user id.

    Returns:
        The membership.

    Raises:
        ApiError: 404 when the user is not an active member of this firm.
    """
    membership = repo.find_one(accounts.MEMBERSHIPS, {"user_id": user_id, "status": accounts.ACTIVE})
    if membership is None:
        raise ApiError(404, "not_found", "member not found")
    return membership


def _last_owner() -> ApiError:
    """Build the refusal for leaving a firm without an owner.

    Returns:
        409 last_owner.
    """
    return ApiError(409, "last_owner", "a firm must keep at least one owner")


def _owners_left(repo: PlatformRepo) -> int:
    """Count the firm's active owners.

    Args:
        repo: Firm-confined repo.

    Returns:
        The count.
    """
    return repo.count_documents(accounts.MEMBERSHIPS, {"role": OWNER, "status": accounts.ACTIVE})


def change_membership_role(repo: PlatformRepo, membership: Doc, role: str, now: datetime) -> None:
    """Change a member's role without ever leaving the firm ownerless, even under concurrent changes.

    An owner's demotion is written first and the owners are counted after it: of two concurrent demotions at
    most one can see another owner left, and a demotion that leaves none is undone.

    Args:
        repo: Firm-confined repo.
        membership: The active membership as loaded.
        role: New role.
        now: Current UTC time.

    Raises:
        ApiError: 404 when the member changed meanwhile, 409 last_owner.
    """
    was_owner = membership["role"] == OWNER
    unchanged = {"_id": membership["_id"], "role": membership["role"], "status": accounts.ACTIVE}
    if not repo.update_one(accounts.MEMBERSHIPS, unchanged, {"$set": {"role": role, "updated_at": now}}):
        raise ApiError(404, "not_found", "member not found")
    if was_owner and role != OWNER and _owners_left(repo) == 0:
        repo.update_one(accounts.MEMBERSHIPS, {"_id": membership["_id"], "role": role},
                        {"$set": {"role": OWNER, "updated_at": now}})
        raise _last_owner()


def remove_membership(repo: PlatformRepo, membership: Doc, now: datetime) -> None:
    """Remove a member without ever leaving the firm ownerless, even under concurrent removals.

    The membership is first marked `removing` (it no longer counts or authenticates), then the owners are counted;
    when none is left the mark is undone, otherwise the row is deleted.

    Args:
        repo: Firm-confined repo.
        membership: The active membership as loaded.
        now: Current UTC time.

    Raises:
        ApiError: 404 when the member changed meanwhile, 409 last_owner.
    """
    if not repo.update_one(accounts.MEMBERSHIPS, {"_id": membership["_id"], "status": accounts.ACTIVE},
                           {"$set": {"status": REMOVING, "updated_at": now}}):
        raise ApiError(404, "not_found", "member not found")
    if membership["role"] == OWNER and _owners_left(repo) == 0:
        repo.update_one(accounts.MEMBERSHIPS, {"_id": membership["_id"], "status": REMOVING},
                        {"$set": {"status": accounts.ACTIVE, "updated_at": now}})
        raise _last_owner()
    repo.delete_one(accounts.MEMBERSHIPS, {"_id": membership["_id"], "status": REMOVING})


def _member(request: Request, membership: Doc) -> Member:
    """Render one membership with its user's profile.

    Args:
        request: Incoming request.
        membership: Membership document.

    Returns:
        The member.
    """
    user = accounts.find_user(get_context(request).platform_db, str(membership["user_id"])) or {}
    return Member(user_id=str(membership["user_id"]), name=user.get("name"), phone=user.get("phone"),
                  email=user.get("email"), role=str(membership["role"]), status=str(membership["status"]),
                  created_at=membership["created_at"])


@router.patch("/members/{user_id}", operation_id="members_update", summary="Change a member's role")
def members_update(user_id: Annotated[str, Path(pattern=USER_ID_PATTERN)], body: MemberPatch, request: Request,
                   principal: FirmOwner) -> Member:
    """Change a member's role (audited); the last owner cannot be demoted.

    Args:
        user_id: Member's user id.
        body: New role.
        request: Incoming request.
        principal: Firm owner.

    Returns:
        The updated member.

    Raises:
        ApiError: 404 not a member of this firm, 409 last_owner.
    """
    repo = _repo(request, principal)
    membership = _active_member(repo, user_id)
    change_membership_role(repo, membership, body.role, get_context(request).clock())
    auditing.record(request, principal, "member.update", {"type": "member", "id": user_id},
                    {"role": membership["role"]}, {"role": body.role})
    return _member(request, {**membership, "role": body.role})


@router.delete("/members/{user_id}", status_code=204, operation_id="members_delete", summary="Remove a member")
def members_delete(user_id: Annotated[str, Path(pattern=USER_ID_PATTERN)], request: Request,
                   principal: FirmOwner) -> Response:
    """Remove a member (audited; access ends on their next request); the last owner cannot be removed.

    Args:
        user_id: Member's user id.
        request: Incoming request.
        principal: Firm owner.

    Returns:
        204.

    Raises:
        ApiError: 404 not a member of this firm, 409 last_owner.
    """
    repo = _repo(request, principal)
    membership = _active_member(repo, user_id)
    remove_membership(repo, membership, get_context(request).clock())
    auditing.record(request, principal, "member.remove", {"type": "member", "id": user_id},
                    {"role": membership["role"]}, None)
    return Response(status_code=204)
