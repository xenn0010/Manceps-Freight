"""Platform accounts: users, their memberships across firms, and firm rows.

Users and memberships are keyed by the user, not by a firm, so lookups here filter by `user_id` (taken from an
authenticated principal) or by a verified credential (phone, email). Per-firm member management goes through
`PlatformRepo`, which confines every query to one tenant.
"""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from pymongo import ReturnDocument

from .mongo import Doc, MongoDb

USERS = "users"
MEMBERSHIPS = "memberships"
FIRMS = "firms"
ID_BYTES = 12
ACTIVE = "active"
USER_PREFIX = "usr"


def new_id(prefix: str) -> str:
    """Make an unguessable, prefixed string id.

    Args:
        prefix: Short type prefix, e.g. "usr" or "ses".

    Returns:
        Id like "usr_3f9a...".
    """
    return f"{prefix}_{secrets.token_hex(ID_BYTES)}"


def create_user(db: MongoDb, now: datetime, phone: str | None = None, email: str | None = None,
                name: str | None = None) -> Doc:
    """Insert a new active user. Absent identifiers are omitted so the sparse unique indexes ignore them.

    Args:
        db: Platform database.
        now: Current UTC time.
        phone: Verified E.164 phone, or None.
        email: Lowercased email, or None.
        name: Display name, or None.

    Returns:
        The stored user.

    Raises:
        ValueError: If neither phone nor email is given.
        pymongo.errors.DuplicateKeyError: If the phone or email already belongs to a user.
    """
    if phone is None and email is None:
        raise ValueError("a user needs a phone or an email")
    user: Doc = {"_id": new_id(USER_PREFIX), "status": ACTIVE, "token_epoch": 0, "created_at": now,
                 "last_login_at": None}
    optional: dict[str, Any] = {"phone": phone, "email": email, "name": name}
    user.update({key: value for key, value in optional.items() if value is not None})
    db[USERS].insert_one(dict(user))
    return user


def find_user(db: MongoDb, user_id: str) -> Doc | None:
    """Load a user by id.

    Args:
        db: Platform database.
        user_id: User id from a verified token or record.

    Returns:
        The user or None.
    """
    return db[USERS].find_one({"_id": user_id})


def bump_epoch(db: MongoDb, user_id: str) -> int:
    """Increment a user's token epoch, invalidating every access token issued before.

    Args:
        db: Platform database.
        user_id: User id.

    Returns:
        The new epoch.

    Raises:
        LookupError: If the user does not exist.
    """
    doc = db[USERS].find_one_and_update({"_id": user_id}, {"$inc": {"token_epoch": 1}},
                                        return_document=ReturnDocument.AFTER)
    if doc is None:
        raise LookupError(f"user {user_id!r} not found")
    return int(doc["token_epoch"])


def find_firm(db: MongoDb, tenant_id: str) -> Doc | None:
    """Load a firm row.

    Args:
        db: Platform database.
        tenant_id: Firm id from a verified principal or membership.

    Returns:
        The firm or None.
    """
    return db[FIRMS].find_one({"_id": tenant_id})


def find_membership(db: MongoDb, user_id: str, tenant_id: str) -> Doc | None:
    """Load a user's active membership in one firm.

    Args:
        db: Platform database.
        user_id: User id.
        tenant_id: Firm id.

    Returns:
        The membership or None.
    """
    return db[MEMBERSHIPS].find_one({"user_id": user_id, "tenant_id": tenant_id, "status": ACTIVE})


def active_memberships(db: MongoDb, user_id: str) -> list[Doc]:
    """List a user's active memberships in active firms, oldest first, each with its firm name.

    Args:
        db: Platform database.
        user_id: User id.

    Returns:
        Membership documents with an added `firm_name`.
    """
    found: list[Doc] = []
    for membership in db[MEMBERSHIPS].find({"user_id": user_id, "status": ACTIVE}).sort([("created_at", 1)]):
        firm = find_firm(db, str(membership["tenant_id"]))
        if firm is not None and firm.get("status") == ACTIVE:
            found.append({**membership, "firm_name": firm.get("name")})
    return found


def default_membership(db: MongoDb, user: Doc) -> Doc | None:
    """Pick the firm a login lands in: the last one used if still valid, else the oldest active membership.

    Args:
        db: Platform database.
        user: User document.

    Returns:
        The membership or None when the user has no active firm.
    """
    memberships = active_memberships(db, str(user["_id"]))
    last = user.get("last_tenant_id")
    for membership in memberships:
        if membership["tenant_id"] == last:
            return membership
    return memberships[0] if memberships else None
