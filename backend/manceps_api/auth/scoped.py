"""Scoped links for carriers (and later drivers): `mcl_<urlsafe32>` tokens stored as SHA-256 in `platform.scoped_links`.

A link is exchanged for a short portal token (aud="portal"). The firm comes from the stored link, never from the
request. Links are created through a tenant-confined `PlatformRepo`; the create and revoke routes ship with carriers.
A link (and every portal token from it) only works while its firm is active and its subject is live: a suspended
firm or an offboarded or deleted carrier locks the portal out, and offboarding revokes the carrier's links.
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any, Literal

from bson import ObjectId

from manceps_core import accounts
from manceps_core.accounts import new_id
from manceps_core.mongo import Doc, MongoDb
from manceps_core.repo.carriers import CARRIERS, OFFBOARDED
from manceps_core.repo.fleet import DRIVERS
from manceps_core.tenancy import PlatformRepo, Principal, TenantDb

from .sessions import hash_token

SCOPED_LINKS = "scoped_links"
LINK_TOKEN_PREFIX = "mcl_"  # noqa: S105 - a public prefix, not a secret
LINK_TOKEN_BYTES = 32
LINK_ID_PREFIX = "lnk"
DEFAULT_LINK_DAYS = 30
LINK_TOKEN_PATTERN = r"^mcl_[A-Za-z0-9_-]{43}$"  # noqa: S105 - a regex, not a secret

SubjectType = Literal["carrier", "driver"]
SUBJECT_COLLECTIONS: Mapping[str, str] = {"carrier": CARRIERS, "driver": DRIVERS}


def issue_link(repo: PlatformRepo, subject_type: SubjectType, subject_id: str, created_by: Mapping[str, Any],
               now: datetime, ttl: timedelta = timedelta(days=DEFAULT_LINK_DAYS)) -> tuple[Doc, str]:
    """Create a scoped link in the repo's firm.

    Args:
        repo: Platform repo confined to the firm.
        subject_type: Who the link is for.
        subject_id: Carrier or driver id in that firm.
        created_by: Actor {kind, id}.
        now: Current UTC time.
        ttl: Link lifetime.

    Returns:
        (stored link, raw token). Only the hash is stored; the raw token is shown once.

    Raises:
        ValueError: If the subject id is empty.
    """
    if not subject_id:
        raise ValueError("scoped link subject id is empty")
    raw = LINK_TOKEN_PREFIX + secrets.token_urlsafe(LINK_TOKEN_BYTES)
    link: Doc = {"_id": new_id(LINK_ID_PREFIX), "token_hash": hash_token(raw),
                 "subject": {"type": subject_type, "id": subject_id}, "created_by": dict(created_by),
                 "created_at": now, "expires_at": now + ttl, "revoked_at": None}
    repo.insert_one(SCOPED_LINKS, link)
    return {**link, "tenant_id": repo.tenant_id}, raw


def link_is_live(link: Doc | None, now: datetime) -> bool:
    """Check a link exists, is not revoked and has not expired.

    Args:
        link: Stored link or None.
        now: Current UTC time.

    Returns:
        True when the link may be used.
    """
    if link is None or link.get("revoked_at") is not None:
        return False
    expires_at = link.get("expires_at")
    return expires_at is None or expires_at > now


def subject_id_filter(raw_id: str) -> dict[str, Any]:
    """Match a document id stored either as an ObjectId (plugin-written carriers) or as a string.

    Args:
        raw_id: Id from a verified token or stored link.

    Returns:
        The `_id` filter.
    """
    if ObjectId.is_valid(raw_id):
        return {"_id": {"$in": [ObjectId(raw_id), raw_id]}}
    return {"_id": raw_id}


def firm_is_active(platform_db: MongoDb, tenant_id: str) -> bool:
    """Check a link's firm may still use the portal.

    Args:
        platform_db: Platform database.
        tenant_id: Firm id from the stored link.

    Returns:
        True when the firm exists and is active.
    """
    firm = accounts.find_firm(platform_db, tenant_id)
    return firm is not None and firm.get("status") == accounts.ACTIVE


def subject_record(firm_db: MongoDb, subject_type: str, subject_id: str) -> Doc | None:
    """Load a link's subject while it may still use the portal.

    Args:
        firm_db: The link's firm database.
        subject_type: carrier or driver.
        subject_id: Subject id.

    Returns:
        The live, not offboarded record, or None.
    """
    collection = SUBJECT_COLLECTIONS.get(subject_type)
    if collection is None:
        return None
    query = {**subject_id_filter(subject_id), "deleted_at": None, "status": {"$ne": OFFBOARDED}}
    return firm_db[collection].find_one(query)


def revoke_subject_links(repo: PlatformRepo, subject_type: SubjectType, subject_id: str, now: datetime) -> int:
    """Revoke every live link of a subject in the repo's firm.

    Args:
        repo: Platform repo confined to the firm.
        subject_type: carrier or driver.
        subject_id: Subject id.
        now: Current UTC time.

    Returns:
        Number of links revoked.
    """
    query = {"subject.type": subject_type, "subject.id": subject_id, "revoked_at": None}
    return repo.update_many(SCOPED_LINKS, query, {"$set": {"revoked_at": now}})


def link_principal(link: Doc) -> Principal:
    """Build the scoped principal a stored link stands for (the firm comes from the link, never the request).

    Args:
        link: Stored link with tenant_id and subject.

    Returns:
        The principal (user id = subject id).

    Raises:
        TenantError: If the stored tenant id is invalid.
        ValueError: If the subject id is empty.
    """
    subject = link["subject"]
    role = "driver" if subject["type"] == "driver" else "carrier"
    return Principal(user_id=str(subject["id"]), tenant_id=str(link["tenant_id"]), role=role,
                     session_id=str(link["_id"]), kind="scoped")


def portal_allowed(platform_db: MongoDb, tenant_db: TenantDb, link: Doc) -> bool:
    """Check a live link's firm is active and its subject is live and not offboarded.

    Args:
        platform_db: Platform database.
        tenant_db: Firm database provider.
        link: Stored, live link.

    Returns:
        True when the portal may be used through this link.
    """
    principal = link_principal(link)
    if not firm_is_active(platform_db, str(principal.tenant_id)):
        return False
    firm_db = tenant_db.for_principal(principal)
    return subject_record(firm_db, str(link["subject"]["type"]), principal.user_id) is not None
