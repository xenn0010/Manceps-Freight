"""Provision firms from the web signup queue (Atlas `platform.signups`).

The public signup API only verifies the dispatcher's phone and queues a request; this
worker runs on the gateway host, so the host never accepts inbound connections. Each
signup is claimed atomically, so concurrent workers never provision it twice, and a
claim left behind by a crashed worker is retried after STALE_CLAIM.

Run as the operator on the gateway host:
    python3 signup_worker.py --shared-credentials        # poll forever
    python3 signup_worker.py --shared-credentials --once # drain the queue once
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pymongo
import pymongo.errors
from pymongo.database import Database

PLATFORM_DB = "platform"
SIGNUPS = "signups"
MAX_ATTEMPTS = 3
STALE_CLAIM = timedelta(minutes=15)
POLL_SECONDS = 5
MAX_SUFFIX = 50
MAX_TENANT_CHARS = 32
MIN_TENANT_CHARS = 3
ERROR_CHARS = 500
SLUG_PREFIX = "firm"

Provisioner = Callable[[str, str], Any]
Taken = Callable[[str], bool]


def _load(name: str, filename: str) -> ModuleType:
    """Import a sibling script or plugin module by path.

    Args:
        name: Module name to register.
        filename: Path relative to this file.

    Returns:
        The loaded module.

    Raises:
        RuntimeError: If the file cannot be loaded.
    """
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parent / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


provisioning = _load("hermes_freight_provision", "provision_tenant.py")
tenant = provisioning.tenant


def slugify(firm_name: str) -> str:
    """Turn a firm name into a valid tenant id.

    Args:
        firm_name: Name typed by the dispatcher.

    Returns:
        Lowercase slug that passes tenant.validate_tenant_id.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", firm_name.lower()).strip("-")
    if not slug:
        return SLUG_PREFIX
    if not slug[0].isalpha() or len(slug) < MIN_TENANT_CHARS:
        slug = f"{SLUG_PREFIX}-{slug}"
    return slug[:MAX_TENANT_CHARS].rstrip("-")


def ensure_indexes(db: Database) -> None:
    """Create the queue's indexes; idempotent. Shared with the signup API.

    Args:
        db: Platform database.
    """
    db[SIGNUPS].create_index("phone", unique=True)
    db[SIGNUPS].create_index("tenant_id", unique=True, sparse=True)
    db[SIGNUPS].create_index([("status", pymongo.ASCENDING), ("created_at", pymongo.ASCENDING)])


def claim(db: Database, now: datetime) -> dict[str, Any] | None:
    """Atomically take the oldest pending signup, or one whose claim went stale.

    Args:
        db: Platform database.
        now: Current UTC time.

    Returns:
        The claimed signup, or None when the queue is empty.
    """
    stale = {"status": "provisioning", "claimed_at": {"$lt": now - STALE_CLAIM}}
    return db[SIGNUPS].find_one_and_update(
        {"$or": [{"status": "pending"}, stale]},
        {"$set": {"status": "provisioning", "claimed_at": now}, "$inc": {"attempts": 1}},
        sort=[("created_at", pymongo.ASCENDING)],
        return_document=pymongo.ReturnDocument.AFTER,
    )


def assign_tenant_id(db: Database, signup: dict[str, Any], taken: Taken) -> str:
    """Reserve a unique tenant id for a signup, reusing one from an earlier attempt.

    Args:
        db: Platform database.
        signup: Claimed signup.
        taken: Returns True when a tenant id already exists outside the queue.

    Returns:
        The reserved tenant id.

    Raises:
        RuntimeError: If no free id exists within MAX_SUFFIX tries.
    """
    if signup.get("tenant_id"):
        return signup["tenant_id"]
    base = slugify(str(signup.get("firm_name", "")))
    for n in range(1, MAX_SUFFIX + 1):
        suffix = "" if n == 1 else f"-{n}"
        candidate = base[:MAX_TENANT_CHARS - len(suffix)].rstrip("-") + suffix
        if taken(candidate):
            continue
        try:
            db[SIGNUPS].update_one({"_id": signup["_id"]}, {"$set": {"tenant_id": candidate}})
        except pymongo.errors.DuplicateKeyError:
            continue
        return candidate
    raise RuntimeError(f"no free tenant id for {base!r}")


def process_one(db: Database, provision: Provisioner, taken: Taken, now: datetime | None = None) -> str | None:
    """Claim and provision one signup, recording the outcome on the queue document.

    Args:
        db: Platform database.
        provision: Called with (tenant_id, dispatcher_phone); raises on failure.
        taken: Returns True when a tenant id already exists outside the queue.
        now: Current UTC time (tests); defaults to the clock.

    Returns:
        The processed signup id, or None when nothing was waiting.
    """
    signup = claim(db, now or datetime.now(UTC))
    if signup is None:
        return None
    try:
        tenant_id = assign_tenant_id(db, signup, taken)
        provision(tenant_id, signup["phone"])
    except (RuntimeError, OSError, ValueError, pymongo.errors.PyMongoError) as exc:
        status = "failed" if signup["attempts"] >= MAX_ATTEMPTS else "pending"
        db[SIGNUPS].update_one({"_id": signup["_id"]},
                               {"$set": {"status": status, "error": str(exc)[:ERROR_CHARS]}})
        print(f"signup {signup['_id']} attempt {signup['attempts']} failed: {exc}", file=sys.stderr)
        return signup["_id"]
    db[SIGNUPS].update_one({"_id": signup["_id"]},
                           {"$set": {"status": "ready", "ready_at": datetime.now(UTC)}, "$unset": {"error": ""}})
    print(f"signup {signup['_id']} provisioned as {tenant_id}", flush=True)
    return signup["_id"]


def operator_uri() -> str:
    """Read the operator's MONGODB_URI from the environment or Hermes .env.

    Returns:
        Connection string.

    Raises:
        RuntimeError: If it is not configured.
    """
    uri = os.environ.get("MONGODB_URI") or provisioning.read_env(provisioning.HERMES_HOME / ".env").get("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI not set")
    return uri


def main() -> int:
    """Poll the signup queue and provision firms.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description="Provision firms from the web signup queue")
    parser.add_argument("--shared-credentials", action="store_true")
    parser.add_argument("--once", action="store_true", help="drain the queue, then exit")
    args = parser.parse_args()

    def run(tenant_id: str, phone: str) -> None:
        provisioning.provision(tenant_id, phone, shared_credentials=args.shared_credentials)

    def taken(tenant_id: str) -> bool:
        return (provisioning.HERMES_HOME / "profiles" / tenant_id).exists()

    try:
        db = pymongo.MongoClient(operator_uri(), serverSelectionTimeoutMS=20000, tz_aware=True)[PLATFORM_DB]
        ensure_indexes(db)
        while True:
            if process_one(db, run, taken) is None:
                if args.once:
                    return 0
                time.sleep(POLL_SECONDS)
    except (RuntimeError, pymongo.errors.PyMongoError) as exc:
        print(f"signup worker stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
