"""Refresh sessions in `platform.sessions`: hashed rotating refresh tokens grouped into families.

Using a refresh token marks its row `rotated_to` the new row (a conditional update, so two concurrent uses cannot
both win). Presenting a token that was already rotated revokes the whole family: the token was stolen or replayed.
The claim also requires the row to be unrevoked, and each session records the user's token epoch, so a refresh
racing logout, logout-all or reuse revocation can never leave a live successor behind.
Sessions belong to a user, so every lookup filters by the user id from a verified token or by the token hash.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from manceps_core.accounts import new_id
from manceps_core.hashing import sha256_bytes
from manceps_core.mongo import Doc, MongoDb

SESSIONS = "sessions"
REFRESH_BYTES = 32
SESSION_PREFIX = "ses"
FAMILY_PREFIX = "fam"


class RefreshError(Exception):
    """A refresh token was rejected."""

    def __init__(self, code: str, message: str) -> None:
        """Create the error.

        Args:
            code: invalid_refresh or refresh_reuse.
            message: Safe explanation.
        """
        super().__init__(message)
        self.code = code
        self.message = message


def hash_token(raw: str) -> str:
    """Hash a bearer secret for storage and lookup.

    Args:
        raw: Token text.

    Returns:
        Hex SHA-256 of its UTF-8 bytes.
    """
    return sha256_bytes(raw.encode("utf-8"))


def create_session(db: MongoDb, user_id: str, tenant_id: str | None, now: datetime, ttl: timedelta,
                   ua: str, ip: str, epoch: int, family_id: str | None = None) -> tuple[Doc, str]:
    """Start a session (or the next link of a family) and return its one-time refresh token.

    Args:
        db: Platform database.
        user_id: Owner of the session.
        tenant_id: Firm the session's access tokens are for, or None.
        now: Current UTC time.
        ttl: Refresh token lifetime.
        ua: User agent (bounded).
        ip: Client IP.
        epoch: The user's token epoch when the family started; a later logout-all makes it stale.
        family_id: Existing family when rotating, None for a new login.

    Returns:
        (stored session, raw refresh token). Only the hash is stored.
    """
    raw = secrets.token_urlsafe(REFRESH_BYTES)
    session: Doc = {
        "_id": new_id(SESSION_PREFIX), "user_id": user_id, "tenant_id": tenant_id,
        "family_id": family_id or new_id(FAMILY_PREFIX), "token_hash": hash_token(raw), "rotated_to": None,
        "created_at": now, "expires_at": now + ttl, "revoked_at": None, "ua": ua, "ip": ip, "epoch": epoch,
    }
    db[SESSIONS].insert_one(dict(session))
    return session, raw


def revoke_family(db: MongoDb, family_id: str, now: datetime) -> int:
    """Revoke every session in a family.

    Args:
        db: Platform database.
        family_id: Family id.
        now: Current UTC time.

    Returns:
        Number of sessions revoked.
    """
    return db[SESSIONS].update_many({"family_id": family_id, "revoked_at": None},
                                    {"$set": {"revoked_at": now}}).modified_count


def revoke_user(db: MongoDb, user_id: str, now: datetime) -> int:
    """Revoke every session of a user.

    Args:
        db: Platform database.
        user_id: User id.
        now: Current UTC time.

    Returns:
        Number of sessions revoked.
    """
    return db[SESSIONS].update_many({"user_id": user_id, "revoked_at": None},
                                    {"$set": {"revoked_at": now}}).modified_count


def rotate(db: MongoDb, raw: str, now: datetime, ttl: timedelta, ua: str, ip: str) -> tuple[Doc, str]:
    """Exchange a refresh token for the next one in its family.

    Args:
        db: Platform database.
        raw: Presented refresh token.
        now: Current UTC time.
        ttl: Lifetime of the new refresh token.
        ua: User agent.
        ip: Client IP.

    Returns:
        (new session, new raw refresh token).

    Raises:
        RefreshError: invalid_refresh for unknown, revoked or expired tokens (including one revoked while this call
            ran); refresh_reuse (after revoking the family) for a token that was already rotated.
    """
    current = db[SESSIONS].find_one({"token_hash": hash_token(raw)})
    if current is None or current["revoked_at"] is not None or current["expires_at"] <= now:
        raise RefreshError("invalid_refresh", "the refresh token is not valid")
    if current["rotated_to"] is not None:
        revoke_family(db, str(current["family_id"]), now)
        raise RefreshError("refresh_reuse", "the refresh token was already used; please sign in again")
    successor, new_raw = create_session(db, str(current["user_id"]), current["tenant_id"], now, ttl, ua, ip,
                                        int(current.get("epoch") or 0), family_id=str(current["family_id"]))
    claimed = db[SESSIONS].update_one({"_id": current["_id"], "rotated_to": None, "revoked_at": None},
                                      {"$set": {"rotated_to": successor["_id"], "rotated_at": now}})
    if claimed.modified_count == 0:
        db[SESSIONS].delete_one({"_id": successor["_id"]})
        revoke_family(db, str(current["family_id"]), now)
        latest = db[SESSIONS].find_one({"_id": current["_id"]}, {"rotated_to": 1})
        if latest is None or latest.get("rotated_to") is None:
            raise RefreshError("invalid_refresh", "the refresh token is not valid")
        raise RefreshError("refresh_reuse", "the refresh token was already used; please sign in again")
    return successor, new_raw


def find_session(db: MongoDb, session_id: str) -> Doc | None:
    """Load a session by id.

    Args:
        db: Platform database.
        session_id: Session id from a verified token.

    Returns:
        The session or None.
    """
    return db[SESSIONS].find_one({"_id": session_id})


def active_sessions(db: MongoDb, user_id: str, now: datetime) -> list[Doc]:
    """List a user's live sessions: the newest, unrevoked, unexpired row of each family.

    Args:
        db: Platform database.
        user_id: User id.
        now: Current UTC time.

    Returns:
        Sessions, newest first.
    """
    query = {"user_id": user_id, "revoked_at": None, "rotated_to": None, "expires_at": {"$gt": now}}
    return list(db[SESSIONS].find(query).sort([("created_at", -1)]))
