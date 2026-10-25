"""Index specifications for firm and platform databases.

Each index is created with `name=` equal to the driver's default name ("field_1_other_-1"), so the hermes-freight
plugin's and signup API's own `create_index` calls for the same keys and options are no-ops, never conflicts.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeAlias

import pymongo

from .mongo import MongoDb

ASC = pymongo.ASCENDING
DESC = pymongo.DESCENDING
TEXT = pymongo.TEXT
GEO_2DSPHERE = pymongo.GEOSPHERE
HOUR_SECONDS = 3600
DAY_SECONDS = 24 * HOUR_SECONDS
EVENTS_TTL_SECONDS = 30 * DAY_SECONDS
IDEMPOTENCY_TTL_SECONDS = DAY_SECONDS
RATE_LIMIT_TTL_SECONDS = DAY_SECONDS
SIGNUP_ATTEMPT_TTL_SECONDS = DAY_SECONDS
INVITATION_TTL_AFTER_EXPIRY_SECONDS = 7 * DAY_SECONDS
SESSION_TTL_AFTER_EXPIRY_SECONDS = 30 * DAY_SECONDS
MAGIC_LINK_TTL_AFTER_EXPIRY_SECONDS = HOUR_SECONDS
SIGNUP_TICKET_TTL_AFTER_EXPIRY_SECONDS = HOUR_SECONDS
EXPIRE_AT_FIELD_TIME = 0

KeyDirection: TypeAlias = int | str


@dataclass(frozen=True)
class IndexSpec:
    """One index: ordered keys plus options."""

    keys: tuple[tuple[str, KeyDirection], ...]
    unique: bool = False
    sparse: bool = False
    expire_after_seconds: int | None = None

    @property
    def name(self) -> str:
        """Return the driver's default name for these keys.

        Returns:
            Name like "mc_number_1_checked_at_-1".
        """
        return "_".join(f"{field}_{direction}" for field, direction in self.keys)

    def options(self) -> dict[str, Any]:
        """Return create_index keyword options, only those that are set.

        Returns:
            Options including the explicit name.
        """
        options: dict[str, Any] = {"name": self.name}
        if self.unique:
            options["unique"] = True
        if self.sparse:
            options["sparse"] = True
        if self.expire_after_seconds is not None:
            options["expireAfterSeconds"] = self.expire_after_seconds
        return options


def _idx(*keys: tuple[str, KeyDirection], unique: bool = False, sparse: bool = False,
         ttl: int | None = None) -> IndexSpec:
    """Shorthand for an IndexSpec.

    Args:
        *keys: (field, direction) pairs.
        unique: Unique index.
        sparse: Sparse index.
        ttl: expireAfterSeconds, or None.

    Returns:
        The spec.
    """
    return IndexSpec(tuple(keys), unique=unique, sparse=sparse, expire_after_seconds=ttl)


FIRM_INDEXES: Mapping[str, tuple[IndexSpec, ...]] = {
    # carriers, brokers, broker_checks and audit's at_-1 are exactly the plugin's store.ensure_indexes.
    "carriers": (_idx(("phone", ASC), unique=True), _idx(("mc_number", ASC), sparse=True),
                 _idx(("status", ASC)), _idx(("insurance_expires_at", ASC))),
    "drivers": (_idx(("phone", ASC), unique=True, sparse=True), _idx(("carrier_id", ASC))),
    "trucks": (_idx(("carrier_id", ASC)), _idx(("vin", ASC), unique=True, sparse=True)),
    "brokers": (_idx(("mc_number", ASC), unique=True),),
    "broker_checks": (_idx(("mc_number", ASC), ("checked_at", DESC)), _idx(("dot_number", ASC), ("checked_at", DESC))),
    "contacts": (_idx(("kind", ASC)), _idx(("phones", ASC)), _idx(("emails", ASC)),
                 _idx(("name", TEXT), ("company", TEXT))),
    "facilities": (_idx(("geo", GEO_2DSPHERE)), _idx(("state", ASC), ("city", ASC))),
    "notes": (_idx(("ref.type", ASC), ("ref.id", ASC), ("created_at", ASC)),),
    "consent_events": (_idx(("subject.phone", ASC), ("channel", ASC), ("at", ASC)),
                       _idx(("subject.type", ASC), ("subject.id", ASC), ("at", ASC)),
                       _idx(("subject.type", ASC), ("subject.id", ASC), ("version", ASC), unique=True)),
    "loads": (_idx(("ref", ASC), unique=True), _idx(("status", ASC), ("updated_at", ASC)),
              _idx(("carrier_id", ASC), ("status", ASC)), _idx(("broker_mc", ASC)), _idx(("stops.window_start", ASC)),
              _idx(("truck_id", ASC), ("status", ASC)), _idx(("driver_id", ASC)), _idx(("booked_at", ASC))),
    "load_events": (_idx(("load_id", ASC), ("at", ASC)), _idx(("load_id", ASC), ("_id", ASC))),
    "approvals": (_idx(("status", ASC), ("created_at", ASC)), _idx(("subject_ref.type", ASC), ("subject_ref.id", ASC)),
                  _idx(("kind", ASC), ("subject_ref.id", ASC), ("status", ASC)), _idx(("decided_at", DESC))),
    "imports": (_idx(("status", ASC), ("created_at", ASC)), _idx(("idempotency_hash", ASC), unique=True)),
    "import_rows": (_idx(("import_id", ASC), ("row_no", ASC)), _idx(("expires_at", ASC), ttl=EXPIRE_AT_FIELD_TIME)),
    "exports": (_idx(("expires_at", ASC), ttl=EXPIRE_AT_FIELD_TIME), _idx(("status", ASC), ("created_at", ASC))),
    "events": (_idx(("seq", ASC), unique=True), _idx(("at", ASC), ttl=EVENTS_TTL_SECONDS)),
    "audit": (_idx(("at", DESC)), _idx(("ref.type", ASC), ("ref.id", ASC), ("at", DESC))),
}

PLATFORM_INDEXES: Mapping[str, tuple[IndexSpec, ...]] = {
    # signups and signup_attempts are exactly signup-api store.ensure_indexes / signup_worker.ensure_indexes.
    "signups": (_idx(("phone", ASC), unique=True), _idx(("tenant_id", ASC), unique=True, sparse=True),
                _idx(("status", ASC), ("created_at", ASC))),
    "signup_attempts": (_idx(("at", ASC), ttl=SIGNUP_ATTEMPT_TTL_SECONDS),
                        _idx(("kind", ASC), ("key", ASC), ("at", ASC))),
    "users": (_idx(("phone", ASC), unique=True, sparse=True), _idx(("email", ASC), unique=True, sparse=True)),
    "memberships": (_idx(("user_id", ASC), ("tenant_id", ASC), unique=True), _idx(("tenant_id", ASC))),
    "invitations": (_idx(("token_hash", ASC), unique=True),
                    _idx(("expires_at", ASC), ttl=INVITATION_TTL_AFTER_EXPIRY_SECONDS)),
    "sessions": (_idx(("token_hash", ASC), unique=True), _idx(("user_id", ASC), ("revoked_at", ASC)),
                 _idx(("expires_at", ASC), ttl=SESSION_TTL_AFTER_EXPIRY_SECONDS)),
    "magic_links": (_idx(("token_hash", ASC), unique=True),
                    _idx(("expires_at", ASC), ttl=MAGIC_LINK_TTL_AFTER_EXPIRY_SECONDS)),
    "scoped_links": (_idx(("token_hash", ASC), unique=True), _idx(("tenant_id", ASC), ("subject.id", ASC))),
    "firms": (_idx(("slug", ASC), unique=True), _idx(("status", ASC))),
    "signup_tickets": (_idx(("token_hash", ASC), unique=True),
                       _idx(("expires_at", ASC), ttl=SIGNUP_TICKET_TTL_AFTER_EXPIRY_SECONDS)),
    "idempotency_keys": (_idx(("tenant_id", ASC), ("user_id", ASC), ("key", ASC), ("route", ASC), unique=True),
                         _idx(("created_at", ASC), ttl=IDEMPOTENCY_TTL_SECONDS)),
    "rate_limits": (_idx(("kind", ASC), ("key", ASC), ("at", ASC)), _idx(("at", ASC), ttl=RATE_LIMIT_TTL_SECONDS)),
}


# Indexes replaced by a stricter spec; dropped on startup so the old constraint cannot keep refusing writes.
RETIRED_PLATFORM_INDEXES: Mapping[str, tuple[str, ...]] = {
    "idempotency_keys": ("tenant_id_1_key_1_route_1",),
}


def _drop_retired(db: MongoDb, retired: Mapping[str, tuple[str, ...]]) -> None:
    """Drop retired indexes that still exist; idempotent.

    Args:
        db: Database.
        retired: Collection name to index names.

    Raises:
        pymongo.errors.PyMongoError: If the server is unreachable or refuses the drop.
    """
    for collection, names in retired.items():
        existing = db[collection].index_information()
        for name in names:
            if name in existing:
                db[collection].drop_index(name)


def _ensure(db: MongoDb, specs: Mapping[str, tuple[IndexSpec, ...]]) -> None:
    """Create every index in a spec map; idempotent.

    Args:
        db: Database.
        specs: Collection name to index specs.

    Raises:
        pymongo.errors.PyMongoError: If the server rejects an index or is unreachable.
    """
    for collection, indexes in specs.items():
        for spec in indexes:
            db[collection].create_index(list(spec.keys), **spec.options())


def ensure_firm_indexes(db: MongoDb) -> None:
    """Create every firm-database index; idempotent.

    Args:
        db: A `firm_<tenant>` database.

    Raises:
        pymongo.errors.PyMongoError: If the server rejects an index or is unreachable.
    """
    _ensure(db, FIRM_INDEXES)


def ensure_platform_indexes(db: MongoDb) -> None:
    """Create every platform-database index; idempotent.

    Args:
        db: The `platform` database.

    Raises:
        pymongo.errors.PyMongoError: If the server rejects an index or is unreachable.
    """
    _drop_retired(db, RETIRED_PLATFORM_INDEXES)
    _ensure(db, PLATFORM_INDEXES)
