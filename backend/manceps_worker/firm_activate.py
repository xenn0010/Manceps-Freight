"""`firm_activate`: turn a provisioned (`ready`) signup into an active firm with an owner membership.

Every step is an upsert or a conditional write, so running the handler twice (or after a crash half-way) converges
on the same state. The signup is marked `activated_at` last; until then the runner keeps retrying it.
"""

from __future__ import annotations

from pymongo import ReturnDocument

from manceps_core import accounts, audit
from manceps_core.clock import Clock, utc_now
from manceps_core.indexes import ensure_firm_indexes
from manceps_core.mongo import Doc, MongoDb
from manceps_core.signups import READY, SIGNUPS
from manceps_core.tenancy import Principal, TenantDb, TenantError, validate_tenant_id

DEFAULT_PLAN = "trial"
DEFAULT_TIMEZONE = "America/Chicago"
OWNER_ROLE = "owner"
SYSTEM_ACTOR = "system:firm_activate"
ACTIVATED_EVENT = "firm.activated"


def _owner_user_id(db: MongoDb, signup: Doc, now_clock: Clock) -> str:
    """Return the signup's user, creating one by phone for rows queued by the old signup API.

    Args:
        db: Platform database.
        signup: Signup document.
        now_clock: Time source.

    Returns:
        The owner's user id.
    """
    if signup.get("user_id"):
        return str(signup["user_id"])
    existing = db[accounts.USERS].find_one({"phone": signup["phone"]})
    if existing is not None:
        return str(existing["_id"])
    return str(accounts.create_user(db, now_clock(), phone=str(signup["phone"]))["_id"])


def _validated_tenant(signup: Doc) -> str:
    """Check the signup is ready and carries a valid tenant id.

    Args:
        signup: Signup document.

    Returns:
        The tenant id.

    Raises:
        ValueError: If the signup is not ready or its tenant id is missing or invalid.
    """
    if signup.get("status") != READY:
        raise ValueError(f"signup {signup.get('_id')!r} is not ready")
    try:
        return validate_tenant_id(str(signup.get("tenant_id") or ""))
    except TenantError as exc:
        raise ValueError(f"signup {signup.get('_id')!r} has an invalid tenant id") from exc


def _upsert_firm(db: MongoDb, tenant_id: str, signup: Doc, owner_id: str, clock: Clock) -> bool:
    """Create the firm row if it does not exist.

    Args:
        db: Platform database.
        tenant_id: Firm id.
        signup: Signup document.
        owner_id: Owner user id.
        clock: Time source.

    Returns:
        True when the firm row was created by this call.
    """
    before = db[accounts.FIRMS].find_one_and_update(
        {"_id": tenant_id},
        {"$setOnInsert": {"name": signup.get("firm_name") or tenant_id, "slug": tenant_id, "status": "active",
                          "plan": DEFAULT_PLAN, "timezone": DEFAULT_TIMEZONE, "owner_user_id": owner_id,
                          "created_at": clock(), "signup_id": signup["_id"]}},
        upsert=True, return_document=ReturnDocument.BEFORE,
    )
    return before is None


def firm_activate(db: MongoDb, tenant_db: TenantDb, signup: Doc, clock: Clock = utc_now) -> bool:
    """Activate the firm for a ready signup; idempotent.

    Args:
        db: Platform database.
        tenant_db: Firm database provider.
        signup: A signup with status "ready" and a tenant id.
        clock: Time source.

    Returns:
        True when this call created the firm, False when it already existed.

    Raises:
        ValueError: If the signup is not ready or has no valid tenant id.
        pymongo.errors.PyMongoError: On database failure (the runner retries on its next poll).
    """
    tenant_id = _validated_tenant(signup)
    owner_id = _owner_user_id(db, signup, clock)
    created = _upsert_firm(db, tenant_id, signup, owner_id, clock)
    db[accounts.MEMBERSHIPS].update_one(
        {"user_id": owner_id, "tenant_id": tenant_id},
        {"$setOnInsert": {"role": OWNER_ROLE, "status": accounts.ACTIVE, "created_at": clock(),
                          "updated_at": clock()}},
        upsert=True,
    )
    system = Principal(user_id=SYSTEM_ACTOR, tenant_id=tenant_id, role="system", session_id=None, kind="system")
    firm_db = tenant_db.for_principal(system)
    ensure_firm_indexes(firm_db)
    if firm_db[audit.AUDIT].count_documents({"event": ACTIVATED_EVENT}, limit=1) == 0:
        audit.write(firm_db, {"kind": "system", "id": SYSTEM_ACTOR}, ACTIVATED_EVENT,
                    {"type": "firm", "id": tenant_id}, None, None, None, {"owner_user_id": owner_id}, clock)
    db[SIGNUPS].update_one({"_id": signup["_id"], "activated_at": {"$exists": False}},
                           {"$set": {"activated_at": clock()}, "$unset": {"activation_error": ""}})
    return created
