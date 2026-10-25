"""Request and response models for the auth routes."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from manceps_core.emails import EMAIL_MAX, normalize_email
from manceps_core.phones import normalize_phone
from manceps_core.tenancy import TENANT_PATTERN, Role

from .scoped import LINK_TOKEN_PATTERN
from .signup_tickets import TICKET_PATTERN

FIRM_NAME_MIN, FIRM_NAME_MAX = 2, 60
SECRET_TOKEN_PATTERN = r"^(mci_)?[A-Za-z0-9_-]{43}$"  # noqa: S105 - a regex, not a secret
OTP_CODE_PATTERN = r"^[0-9]{4,10}$"

LoginState = Literal["active", "provisioning", "no_firm"]


def normalize_firm_name(value: str) -> str:
    """Collapse whitespace and enforce the firm name length (signup-api rule).

    Args:
        value: Name as typed.

    Returns:
        The normalized name.

    Raises:
        ValueError: If it is too short or too long.
    """
    value = " ".join(value.split())
    if not FIRM_NAME_MIN <= len(value) <= FIRM_NAME_MAX:
        raise ValueError(f"firm name must be {FIRM_NAME_MIN} to {FIRM_NAME_MAX} characters")
    return value


class StrictModel(BaseModel):
    """Request models refuse unknown fields (a client cannot smuggle tenant_id or role) and non-finite numbers."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class OtpStartRequest(StrictModel):
    """Send a one-time code."""

    phone: str = Field(max_length=32)

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        return normalize_phone(value)


class OtpVerifyRequest(OtpStartRequest):
    """Prove the phone with a code, or with the signup ticket a code earned; a phone with no account also needs the
    signup fields (send them with the code, or with the ticket from the 422 signup_details_required answer)."""

    code: str | None = Field(default=None, pattern=OTP_CODE_PATTERN)
    signup_ticket: str | None = Field(default=None, pattern=TICKET_PATTERN,
                                      description="From error.details.signup_ticket of a 422 signup_details_required.")
    firm_name: str | None = Field(default=None, max_length=200)
    accept_terms: Literal[True] | None = None

    @field_validator("firm_name")
    @classmethod
    def _firm_name(cls, value: str | None) -> str | None:
        return None if value is None else normalize_firm_name(value)

    @model_validator(mode="after")
    def _one_proof(self) -> OtpVerifyRequest:
        if (self.code is None) == (self.signup_ticket is None):
            raise ValueError("send either code or signup_ticket")
        if self.signup_ticket is not None and (self.firm_name is None or self.accept_terms is not True):
            raise ValueError("signup_ticket needs firm_name and accept_terms")
        return self


class SentResponse(BaseModel):
    """A code was sent."""

    sent: bool


class AcceptedResponse(BaseModel):
    """The request was accepted (whether or not anything was sent)."""

    accepted: bool


class MagicLinkStartRequest(StrictModel):
    """Email a sign-in link."""

    email: str = Field(max_length=EMAIL_MAX)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return normalize_email(value)


class SecretTokenRequest(StrictModel):
    """A one-time secret from a link (magic link or invitation)."""

    token: str = Field(pattern=SECRET_TOKEN_PATTERN)


class RefreshRequest(StrictModel):
    """Native clients send the refresh token in the body; browsers use the mc_refresh cookie."""

    refresh_token: str | None = Field(default=None, max_length=128)


class SwitchFirmRequest(StrictModel):
    """Switch the session to a firm the user belongs to (default: the newest ready one)."""

    tenant_id: str | None = Field(default=None, pattern=TENANT_PATTERN.pattern)


class ScopedExchangeRequest(StrictModel):
    """A scoped link token."""

    token: str = Field(pattern=LINK_TOKEN_PATTERN)


class TokenResponse(BaseModel):
    """Tokens after sign-in, refresh or switching firm."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - the OAuth token type name
    expires_in: int = Field(description="Access token lifetime in seconds.")
    refresh_token: str | None = Field(description="Only for native clients (X-Client: native); browsers get the "
                                                  "HttpOnly mc_refresh cookie.")
    session_id: str
    user_id: str
    tenant_id: str | None
    role: Role
    state: LoginState
    signup_token: str | None = Field(default=None, description="Signup status token after a new signup.")


class PortalTokenResponse(BaseModel):
    """A portal access token (aud=portal)."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - the OAuth token type name
    expires_in: int


class SignupStatus(BaseModel):
    """Public signup status."""

    status: Literal["pending", "provisioning", "ready", "failed"]
    tenant_id: str | None
    message: str | None = None


class SessionItem(BaseModel):
    """A live session (one per sign-in on a device)."""

    id: str
    tenant_id: str | None
    created_at: datetime
    expires_at: datetime
    ua: str
    ip: str
    current: bool
