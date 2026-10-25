"""The signup queue in `platform.signups`, ported from signup-api's store (same document shape plus `user_id`).

hermes-freight's deploy/signup_worker.py claims `pending` rows, provisions them, and sets `status="ready"` with a
`tenant_id`; the platform worker's `firm_activate` then creates the firm row and marks `activated_at`.
"""

from __future__ import annotations

import secrets
from datetime import datetime

from pymongo.errors import DuplicateKeyError

from .mongo import Doc, MongoDb

SIGNUPS = "signups"
TERMS_VERSION = "2026-10-25"
TOKEN_BYTES = 24
PENDING = "pending"
READY = "ready"
FAILED = "failed"


class AlreadySignedUp(RuntimeError):
    """This phone already has a firm, or one is being set up."""


def enqueue(db: MongoDb, phone: str, firm_name: str, client_ip: str, user_id: str, now: datetime) -> str:
    """Queue a verified signup for the provisioning worker.

    Args:
        db: Platform database.
        phone: Verified E.164 number.
        firm_name: Firm name as typed (whitespace-normalized).
        client_ip: Requesting IP, kept as signup evidence.
        user_id: The user who signed up and will own the firm.
        now: Current UTC time.

    Returns:
        Unguessable status token (the signup `_id`).

    Raises:
        AlreadySignedUp: If the phone already has a non-failed signup.
    """
    db[SIGNUPS].delete_many({"phone": phone, "status": FAILED})
    token = secrets.token_urlsafe(TOKEN_BYTES)
    try:
        db[SIGNUPS].insert_one({
            "_id": token, "phone": phone, "firm_name": firm_name, "status": PENDING, "attempts": 0,
            "created_at": now, "terms_version": TERMS_VERSION, "terms_accepted_at": now, "client_ip": client_ip,
            "user_id": user_id,
        })
    except DuplicateKeyError as exc:
        raise AlreadySignedUp(phone) from exc
    return token


def find_status(db: MongoDb, token: str) -> Doc | None:
    """Look up a signup's public fields by its token.

    Args:
        db: Platform database.
        token: Status token from enqueue.

    Returns:
        The signup's status and tenant id, or None for an unknown token.
    """
    return db[SIGNUPS].find_one({"_id": token}, {"status": 1, "tenant_id": 1})


def latest_for_user(db: MongoDb, user_id: str) -> Doc | None:
    """Return the user's most recent signup.

    Args:
        db: Platform database.
        user_id: User id.

    Returns:
        The signup or None.
    """
    return db[SIGNUPS].find_one({"user_id": user_id}, sort=[("created_at", -1)])


def has_open_signup(db: MongoDb, user_id: str) -> bool:
    """Check whether the user has a signup that is not failed.

    Args:
        db: Platform database.
        user_id: User id.

    Returns:
        True when a firm is queued, being provisioned, or ready.
    """
    return db[SIGNUPS].count_documents({"user_id": user_id, "status": {"$ne": FAILED}}, limit=1) > 0
