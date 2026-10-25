"""Scoped links for carriers (and later drivers): `mcl_<urlsafe32>` tokens stored as SHA-256 in `platform.scoped_links`.

A link is exchanged for a short portal token (aud="portal"). The firm comes from the stored link, never from the
request. Links are created through a tenant-confined `PlatformRepo`; the create and revoke routes ship with carriers.
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any, Literal

from manceps_core.accounts import new_id
from manceps_core.mongo import Doc
from manceps_core.tenancy import PlatformRepo

from .sessions import hash_token

SCOPED_LINKS = "scoped_links"
LINK_TOKEN_PREFIX = "mcl_"  # noqa: S105 - a public prefix, not a secret
LINK_TOKEN_BYTES = 32
LINK_ID_PREFIX = "lnk"
DEFAULT_LINK_DAYS = 30
LINK_TOKEN_PATTERN = r"^mcl_[A-Za-z0-9_-]{43}$"  # noqa: S105 - a regex, not a secret

SubjectType = Literal["carrier", "driver"]


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
