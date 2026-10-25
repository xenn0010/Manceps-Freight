"""Firm jobs for the minimal worker loop: queued import commits and exports in every active firm.

Phase 1 has no general job queue: each pass walks the active firms and picks up imports in `committing` and
exports in `queued` (or `running` with an expired lease). Every job step is idempotent and lease-guarded, so
several workers, or a worker restarted mid-job, never apply a row or write a file twice.
"""

from __future__ import annotations

import os
import socket

import structlog
from pymongo.errors import PyMongoError

from manceps_api.exports.run import EXPORTS, QUEUED, RETENTION, RUNNING, run_export
from manceps_api.exports.store import ExportStore, StoreError
from manceps_api.imports.commit import commit_import
from manceps_api.imports.records import COMMITTING, IMPORTS
from manceps_core import accounts
from manceps_core.clock import Clock
from manceps_core.mongo import MongoDb
from manceps_core.repo.errors import RepoError
from manceps_core.tenancy import Principal, TenantDb, TenantError

JOBS_PER_FIRM = 20
WORKER_ACTOR = "system:worker"
ACTIVE = "active"

log = structlog.get_logger(__name__)


def worker_name() -> str:
    """Name this worker process for job leases.

    Returns:
        "<host>:<pid>".
    """
    return f"{socket.gethostname()}:{os.getpid()}"


def _firm_db(tenant_db: TenantDb, tenant_id: str) -> MongoDb:
    """Open a firm database as the worker.

    Args:
        tenant_db: Firm database provider.
        tenant_id: Firm id from the platform firms row.

    Returns:
        The firm database.

    Raises:
        TenantError: If the stored id is not a valid tenant id.
    """
    worker = Principal(user_id=WORKER_ACTOR, tenant_id=tenant_id, role="system", session_id=None, kind="system")
    return tenant_db.for_principal(worker)


def _imports(db: MongoDb, clock: Clock, worker_id: str) -> int:
    """Run the firm's queued import commits.

    Args:
        db: Firm database.
        clock: Time source.
        worker_id: Lease owner name.

    Returns:
        Commits finished.
    """
    done = 0
    for job in db[IMPORTS].find({"status": COMMITTING}, {"_id": 1}, limit=JOBS_PER_FIRM).sort([("created_at", 1)]):
        try:
            done += int(commit_import(db, job["_id"], clock, worker_id))
        except (PyMongoError, RepoError, RuntimeError) as exc:
            log.error("worker.import_commit_failed", import_id=str(job["_id"]), error_type=type(exc).__name__)
    return done


def _exports(db: MongoDb, tenant_id: str, store: ExportStore, clock: Clock) -> int:
    """Run the firm's queued exports.

    Args:
        db: Firm database.
        tenant_id: Firm id.
        store: Export store.
        clock: Time source.

    Returns:
        Exports finished.
    """
    done = 0
    query = {"status": {"$in": [QUEUED, RUNNING]}}
    for job in db[EXPORTS].find(query, {"_id": 1}, limit=JOBS_PER_FIRM).sort([("created_at", 1)]):
        try:
            done += int(run_export(db, tenant_id, store, job["_id"], clock))
        except PyMongoError as exc:
            log.error("worker.export_failed", export_id=str(job["_id"]), error_type=type(exc).__name__)
    return done


def run_firm_jobs(platform_db: MongoDb, tenant_db: TenantDb, clock: Clock, store: ExportStore | None,
                  worker_id: str | None = None) -> int:
    """Run one pass of firm jobs over every active firm, then purge expired export files.

    Args:
        platform_db: Platform database.
        tenant_db: Firm database provider.
        clock: Time source.
        store: Export store, or None when exports are not configured (queued exports then wait).
        worker_id: Lease owner name (defaults to host and pid).

    Returns:
        Jobs finished in this pass.
    """
    owner = worker_id or worker_name()
    done = 0
    for firm in platform_db[accounts.FIRMS].find({"status": ACTIVE}, {"_id": 1}):
        try:
            db = _firm_db(tenant_db, str(firm["_id"]))
        except TenantError:
            log.error("worker.bad_tenant_id")
            continue
        done += _imports(db, clock, owner)
        if store is not None:
            done += _exports(db, str(firm["_id"]), store, clock)
    if store is not None:
        try:
            store.purge(clock() - RETENTION)
        except StoreError as exc:
            log.error("worker.export_purge_failed", error_type=type(exc).__name__)
    return done
