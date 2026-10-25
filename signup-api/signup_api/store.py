"""The signup queue and rate limits in the Atlas `platform` database.

The queue document shape and indexes are shared with hermes-freight's
deploy/signup_worker.py, which claims pending signups and provisions them.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Any

import pymongo
import pymongo.errors
from pymongo.database import Database

PLATFORM_DB = "platform"
SIGNUPS = "signups"
ATTEMPTS = "signup_attempts"
TERMS_VERSION = "2026-10-25"
TOKEN_BYTES = 24
RATE_WINDOW = timedelta(hours=1)
ATTEMPT_TTL_SECONDS = 24 * 3600
START_PER_PHONE = 3
START_PER_IP = 10
VERIFY_PER_PHONE = 10
FAILED = "failed"


class AlreadySignedUp(RuntimeError):
    """This phone already has a firm, or one is being set up."""


def ensure_indexes(db: Database) -> None:
    """Create queue and rate-limit indexes; idempotent. Must match signup_worker.ensure_indexes.

    Args:
        db: Platform database.
    """
    db[SIGNUPS].create_index("phone", unique=True)
    db[SIGNUPS].create_index("tenant_id", unique=True, sparse=True)
    db[SIGNUPS].create_index([("status", pymongo.ASCENDING), ("created_at", pymongo.ASCENDING)])
    db[ATTEMPTS].create_index("at", expireAfterSeconds=ATTEMPT_TTL_SECONDS)
    db[ATTEMPTS].create_index([("kind", pymongo.ASCENDING), ("key", pymongo.ASCENDING), ("at", pymongo.ASCENDING)])


def allow(db: Database, kind: str, key: str, limit: int, now: datetime) -> bool:
    """Count an attempt against a rolling one-hour limit.

    Args:
        db: Platform database.
        kind: Limit name, e.g. "start_phone".
        key: What is limited, e.g. the phone or client IP.
        limit: Attempts allowed per window.
        now: Current UTC time.

    Returns:
        False when the limit is already reached (the attempt is not recorded).
    """
    recent = db[ATTEMPTS].count_documents({"kind": kind, "key": key, "at": {"$gte": now - RATE_WINDOW}})
    if recent >= limit:
        return False
    db[ATTEMPTS].insert_one({"kind": kind, "key": key, "at": now})
    return True


def has_active_signup(db: Database, phone: str) -> bool:
    """Check whether a phone already has a firm queued, in progress, or live.

    Args:
        db: Platform database.
        phone: E.164 number.

    Returns:
        True unless the phone has no signup or only a failed one.
    """
    return db[SIGNUPS].count_documents({"phone": phone, "status": {"$ne": FAILED}}, limit=1) > 0


def enqueue(db: Database, phone: str, firm_name: str, client_ip: str, now: datetime) -> str:
    """Queue a verified signup for the provisioning worker.

    Args:
        db: Platform database.
        phone: Verified E.164 number.
        firm_name: Firm name as typed.
        client_ip: Requesting IP, kept as signup evidence.
        now: Current UTC time.

    Returns:
        Unguessable status token.

    Raises:
        AlreadySignedUp: If the phone already has a non-failed signup.
    """
    db[SIGNUPS].delete_many({"phone": phone, "status": FAILED})
    token = secrets.token_urlsafe(TOKEN_BYTES)
    try:
        db[SIGNUPS].insert_one({
            "_id": token, "phone": phone, "firm_name": firm_name, "status": "pending", "attempts": 0,
            "created_at": now, "terms_version": TERMS_VERSION, "terms_accepted_at": now, "client_ip": client_ip,
        })
    except pymongo.errors.DuplicateKeyError as exc:
        raise AlreadySignedUp(phone) from exc
    return token


def status(db: Database, token: str) -> dict[str, Any] | None:
    """Look up a signup's public status.

    Args:
        db: Platform database.
        token: Status token from enqueue.

    Returns:
        The signup's status and tenant id, or None for an unknown token.
    """
    return db[SIGNUPS].find_one({"_id": token}, {"status": 1, "tenant_id": 1})
