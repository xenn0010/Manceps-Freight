"""MongoDB access for hermes-freight, always scoped to the active profile's tenant."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pymongo
from pymongo.collection import Collection
from pymongo.database import Database

from . import tenant

CARRIERS = "carriers"
BROKERS = "brokers"
BROKER_CHECKS = "broker_checks"
AUDIT = "audit"


def ensure_indexes(db: Database) -> None:
    """Create the indexes the tools rely on; idempotent.

    Args:
        db: Tenant database.
    """
    db[CARRIERS].create_index("phone", unique=True)
    db[CARRIERS].create_index("mc_number", sparse=True)
    db[BROKERS].create_index("mc_number", unique=True)
    db[BROKER_CHECKS].create_index([("mc_number", pymongo.ASCENDING), ("checked_at", pymongo.DESCENDING)])
    db[BROKER_CHECKS].create_index([("dot_number", pymongo.ASCENDING), ("checked_at", pymongo.DESCENDING)])
    db[AUDIT].create_index([("at", pymongo.DESCENDING)])


def get_db() -> Database:
    """Return the active tenant's database.

    Returns:
        The database handle.

    Raises:
        tenant.TenantError: If the profile has no tenant configured.
    """
    return tenant.database(ensure_indexes)


def collection(name: str) -> Collection:
    """Return a collection from the active tenant's database.

    Args:
        name: Collection name.

    Returns:
        The collection handle.

    Raises:
        tenant.TenantError: If the profile has no tenant configured.
    """
    return get_db()[name]


def now() -> datetime:
    """Return the current UTC time.

    Returns:
        Timezone-aware UTC datetime.
    """
    return datetime.now(UTC)


def audit(event: str, **fields: Any) -> None:
    """Append an audit record; every agent write to firm data is logged.

    Args:
        event: Event name, e.g. "carrier.upsert".
        **fields: Event details. Must not contain secrets.
    """
    collection(AUDIT).insert_one({"event": event, "at": now(), **fields})


def to_jsonable(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convert a Mongo document into JSON-serializable form for tool output.

    Args:
        doc: Document or None.

    Returns:
        Copy with ObjectId and datetime values stringified, or None.
    """
    if doc is None:
        return None
    out: dict[str, Any] = {}
    for key, value in doc.items():
        if key == "_id":
            out["id"] = str(value)
        elif isinstance(value, datetime):
            out[key] = value.isoformat()
        elif isinstance(value, dict):
            out[key] = to_jsonable(value)
        elif isinstance(value, list):
            out[key] = [to_jsonable(v) if isinstance(v, dict) else v for v in value]
        else:
            out[key] = value
    return out
