"""FastAPI app: start phone verification, verify and queue the firm, poll status.

Every path fails closed: without a verifier no signup can start, a verifier outage is
a 502, and only an approved code queues a firm.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from typing import Any, Literal

import pymongo
from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from pymongo.database import Database

from . import store
from .verify import Verifier, VerifyError, from_env

US_COUNTRY_CODE = "1"
US_NATIONAL_DIGITS = 10
FIRM_NAME_MIN, FIRM_NAME_MAX = 2, 60
SERVER_SELECTION_TIMEOUT_MS = 10000
FAILED_MESSAGE = "We could not set up your firm. Please try signing up again."


def normalize_phone(raw: str) -> str:
    """Normalize a US phone number to E.164.

    Args:
        raw: Number in any common US format.

    Returns:
        The number as +1XXXXXXXXXX.

    Raises:
        ValueError: If it is not a 10-digit US number.
    """
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == US_NATIONAL_DIGITS + 1 and digits.startswith(US_COUNTRY_CODE):
        digits = digits[1:]
    if len(digits) != US_NATIONAL_DIGITS:
        raise ValueError("enter a 10-digit US phone number")
    return f"+{US_COUNTRY_CODE}{digits}"


class StartRequest(BaseModel):
    """Step 1: who is signing up."""

    phone: str
    firm_name: str
    accept_terms: Literal[True]

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        return normalize_phone(value)

    @field_validator("firm_name")
    @classmethod
    def _firm_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not FIRM_NAME_MIN <= len(value) <= FIRM_NAME_MAX:
            raise ValueError(f"firm name must be {FIRM_NAME_MIN} to {FIRM_NAME_MAX} characters")
        return value


class VerifyRequest(StartRequest):
    """Step 2: the code from the SMS, with the same details as step 1."""

    code: str = Field(pattern=r"^\d{4,10}$")


def _client_ip(request: Request, trust_proxy: bool) -> str:
    """Identify the caller for rate limiting.

    Args:
        request: Incoming request.
        trust_proxy: Use X-Forwarded-For (only behind a proxy that sets it, e.g. Vercel).

    Returns:
        Client IP, or "unknown".
    """
    forwarded = request.headers.get("x-forwarded-for", "") if trust_proxy else ""
    if forwarded.strip():
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _require(verifier: Verifier | None) -> Verifier:
    """Refuse signups while no phone verifier is configured.

    Args:
        verifier: Configured verifier or None.

    Returns:
        The verifier.

    Raises:
        HTTPException: 503 when it is missing.
    """
    if verifier is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "sign-up is temporarily unavailable")
    return verifier


def _reject_existing(db: Database, phone: str) -> None:
    """Raise 409 when the phone already has a firm.

    Args:
        db: Platform database.
        phone: E.164 number.

    Raises:
        HTTPException: 409 on an existing signup.
    """
    if store.has_active_signup(db, phone):
        raise HTTPException(status.HTTP_409_CONFLICT, "a firm already exists for this phone number")


def _limit(db: Database, kind: str, key: str, limit: int) -> None:
    """Apply a rate limit.

    Args:
        db: Platform database.
        kind: Limit name.
        key: What is limited (phone or client IP).
        limit: Attempts allowed per window.

    Raises:
        HTTPException: 429 when exceeded.
    """
    if not store.allow(db, kind, key, limit, datetime.now(UTC)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many attempts; try again in an hour")


def create_app(db: Database, verifier: Verifier | None, trust_proxy: bool = False) -> FastAPI:
    """Build the signup API.

    Args:
        db: Platform database (indexes must exist).
        verifier: Phone verifier, or None to keep signups closed.
        trust_proxy: Trust X-Forwarded-For for the client IP.

    Returns:
        The FastAPI application.
    """
    app = FastAPI(title="hermes-freight signup", docs_url=None, redoc_url=None, openapi_url=None)

    @app.post("/signup/start")
    def start(body: StartRequest, request: Request) -> dict[str, bool]:
        sender = _require(verifier)
        _reject_existing(db, body.phone)
        _limit(db, "start_ip", _client_ip(request, trust_proxy), store.START_PER_IP)
        _limit(db, "start_phone", body.phone, store.START_PER_PHONE)
        try:
            sender.send(body.phone)
        except VerifyError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "could not send the code; try again") from exc
        return {"sent": True}

    @app.post("/signup/verify", status_code=status.HTTP_202_ACCEPTED)
    def verify(body: VerifyRequest, request: Request) -> dict[str, str]:
        checker = _require(verifier)
        _reject_existing(db, body.phone)
        _limit(db, "verify_phone", body.phone, store.VERIFY_PER_PHONE)
        try:
            approved = checker.check(body.phone, body.code)
        except VerifyError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "could not check the code; try again") from exc
        if not approved:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "wrong or expired code")
        try:
            token = store.enqueue(db, body.phone, body.firm_name, _client_ip(request, trust_proxy),
                                  datetime.now(UTC))
        except store.AlreadySignedUp as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, "a firm already exists for this phone number") from exc
        return {"token": token, "status": "pending"}

    @app.get("/signup/status/{token}")
    def signup_status(token: str) -> dict[str, Any]:
        doc = store.status(db, token)
        if doc is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown signup")
        if doc["status"] == store.FAILED:
            return {"status": store.FAILED, "message": FAILED_MESSAGE}
        out: dict[str, Any] = {"status": doc["status"]}
        if doc["status"] == "ready":
            out["tenant_id"] = doc.get("tenant_id")
        return out

    return app


def create_app_from_env() -> FastAPI:
    """Build the app from SIGNUP_MONGODB_URI, SIGNUP_TRUST_PROXY, and the Twilio variables.

    Returns:
        The FastAPI application.

    Raises:
        RuntimeError: If SIGNUP_MONGODB_URI is not set.
    """
    uri = os.environ.get("SIGNUP_MONGODB_URI", "").strip()
    if not uri:
        raise RuntimeError("SIGNUP_MONGODB_URI is not set")
    client: pymongo.MongoClient = pymongo.MongoClient(uri, serverSelectionTimeoutMS=SERVER_SELECTION_TIMEOUT_MS,
                                                      tz_aware=True)
    db = client[store.PLATFORM_DB]
    store.ensure_indexes(db)
    return create_app(db, from_env(), trust_proxy=os.environ.get("SIGNUP_TRUST_PROXY") == "1")
