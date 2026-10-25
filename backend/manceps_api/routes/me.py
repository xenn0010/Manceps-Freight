"""The signed-in user: `GET|PATCH /v1/me`."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator, model_validator
from pymongo.errors import DuplicateKeyError

from manceps_core import accounts
from manceps_core.mongo import Doc
from manceps_core.tenancy import Principal, Role

from ..auth.models import EMAIL_MAX, StrictModel, normalize_email
from ..auth.principal import CurrentUser, unauthorized
from ..context import get_context
from ..errors import ApiError

router = APIRouter(prefix="/v1", tags=["meta"])

NAME_MAX = 100
EMAIL_TAKEN = "this email address belongs to another account"


class MeUser(BaseModel):
    """Profile fields."""

    id: str
    phone: str | None
    email: str | None
    email_verified: bool = Field(description="True once the email was confirmed through a sign-in link.")
    name: str | None
    status: str


class MeMembership(BaseModel):
    """A firm the user belongs to."""

    tenant_id: str
    firm_name: str | None
    role: str


class MeCurrent(BaseModel):
    """The firm and role of the current session."""

    tenant_id: str | None
    role: Role


class Me(BaseModel):
    """The signed-in user."""

    user: MeUser
    memberships: list[MeMembership]
    current: MeCurrent
    session_id: str | None


class MePatch(StrictModel):
    """Profile changes."""

    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX)
    email: str | None = Field(default=None, max_length=EMAIL_MAX)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        return None if value is None else normalize_email(value)

    @model_validator(mode="after")
    def _not_empty(self) -> MePatch:
        if self.name is None and self.email is None:
            raise ValueError("send at least one of name, email")
        return self


def _render(request: Request, principal: Principal, user: Doc) -> Me:
    """Build the response.

    Args:
        request: Incoming request.
        principal: Signed-in user.
        user: User document.

    Returns:
        The user, memberships and current firm (role from the live membership when there is one).
    """
    db = get_context(request).platform_db
    memberships = accounts.active_memberships(db, principal.user_id)
    role: Role = principal.role
    for membership in memberships:
        if membership["tenant_id"] == principal.tenant_id:
            role = membership["role"]
    return Me(
        user=MeUser(id=str(user["_id"]), phone=user.get("phone"), email=user.get("email"),
                    email_verified=user.get("email") is not None and user.get("email_verified_at") is not None,
                    name=user.get("name"), status=str(user.get("status"))),
        memberships=[MeMembership(tenant_id=str(item["tenant_id"]), firm_name=item.get("firm_name"),
                                  role=str(item["role"])) for item in memberships],
        current=MeCurrent(tenant_id=principal.tenant_id, role=role),
        session_id=principal.session_id,
    )


def _user(request: Request, principal: Principal) -> Doc:
    """Load the caller's user document.

    Args:
        request: Incoming request.
        principal: Signed-in user.

    Returns:
        The user.

    Raises:
        ApiError: 401 if the user vanished.
    """
    user = accounts.find_user(get_context(request).platform_db, principal.user_id)
    if user is None:
        raise unauthorized("session_revoked", "this session has ended; please sign in again")
    return user


@router.get("/me", operation_id="me_get", summary="The signed-in user")
def me_get(request: Request, principal: CurrentUser) -> Me:
    """Return the signed-in user, their firms and the current firm.

    Args:
        request: Incoming request.
        principal: Signed-in user.

    Returns:
        The user.
    """
    return _render(request, principal, _user(request, principal))


@router.patch("/me", operation_id="me_update", summary="Update my profile")
def me_update(body: MePatch, request: Request, principal: CurrentUser) -> Me:
    """Change the caller's name or email (emails are unique across users). A new email is unverified until a
    sign-in link sent to it is used, and only a verified email can accept an invitation.

    Args:
        body: Fields to change.
        request: Incoming request.
        principal: Signed-in user.

    Returns:
        The updated user.

    Raises:
        ApiError: 409 email_taken.
    """
    db = get_context(request).platform_db
    changes: dict[str, Any] = body.model_dump(exclude_none=True)
    if "email" in changes and db[accounts.USERS].find_one({"email": changes["email"],
                                                           "_id": {"$ne": principal.user_id}}):
        raise ApiError(409, "email_taken", EMAIL_TAKEN)
    update: dict[str, Any] = {"$set": changes}
    if "email" in changes and changes["email"] != _user(request, principal).get("email"):
        update["$unset"] = {"email_verified_at": ""}
    try:
        db[accounts.USERS].update_one({"_id": principal.user_id}, update)
    except DuplicateKeyError as exc:
        raise ApiError(409, "email_taken", EMAIL_TAKEN) from exc
    return _render(request, principal, _user(request, principal))
