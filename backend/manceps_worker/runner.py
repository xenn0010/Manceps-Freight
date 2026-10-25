"""Minimal worker loop: activate provisioned signups (`firm_activate`), then run firm jobs (import commits and
exports, see jobs.py).

Usage (working directory backend/):
    uv run python -m manceps_worker.runner            # poll forever
    uv run python -m manceps_worker.runner --once     # one pass, then exit
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
from collections.abc import Callable, Sequence
from types import FrameType

import structlog
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from manceps_api.exports.store import ExportStore, store_from_settings
from manceps_api.logs import configure_logging
from manceps_api.settings import load_settings
from manceps_core.clock import Clock, utc_now
from manceps_core.mongo import Doc, MongoClientT, MongoDb
from manceps_core.signups import READY, SIGNUPS
from manceps_core.tenancy import TenantDb

from .firm_activate import firm_activate
from .jobs import run_firm_jobs

POLL_SECONDS = 5.0
BATCH_SIZE = 50
SERVER_SELECTION_TIMEOUT_MS = 10_000
EXIT_OK = 0

log = structlog.get_logger(__name__)


def run_once(db: MongoDb, tenant_db: TenantDb, clock: Clock = utc_now) -> int:
    """Activate every ready signup that has not been activated yet.

    A failing signup is logged and tagged with the error type; it stays eligible and is retried on the next pass.

    Args:
        db: Platform database.
        tenant_db: Firm database provider.
        clock: Time source.

    Returns:
        Number of signups activated in this pass.
    """
    query = {"status": READY, "tenant_id": {"$exists": True}, "activated_at": {"$exists": False}}
    done = 0
    for signup in db[SIGNUPS].find(query, limit=BATCH_SIZE).sort([("created_at", 1)]):
        try:
            firm_activate(db, tenant_db, signup, clock)
        except (ValueError, PyMongoError, RuntimeError) as exc:
            log.error("worker.firm_activate_failed", signup_id=signup["_id"], error_type=type(exc).__name__)
            db[SIGNUPS].update_one({"_id": signup["_id"]}, {"$set": {"activation_error": type(exc).__name__}})
            continue
        log.info("worker.firm_activated", signup_id=signup["_id"], tenant_id=signup["tenant_id"])
        done += 1
    return done


def run_pass(db: MongoDb, tenant_db: TenantDb, clock: Clock, store: ExportStore | None) -> int:
    """Run one full pass: signup activations, then firm jobs.

    Args:
        db: Platform database.
        tenant_db: Firm database provider.
        clock: Time source.
        store: Export store, or None when exports are not configured.

    Returns:
        Activations plus finished firm jobs.
    """
    activated = run_once(db, tenant_db, clock)
    try:
        return activated + run_firm_jobs(db, tenant_db, clock, store)
    except PyMongoError as exc:
        log.error("worker.firm_jobs_failed", error_type=type(exc).__name__)
        return activated


def run_loop(db: MongoDb, tenant_db: TenantDb, clock: Clock, stop: threading.Event,
             poll_seconds: float = POLL_SECONDS, on_tick: Callable[[int], None] | None = None,
             store: ExportStore | None = None) -> None:
    """Poll until `stop` is set.

    Args:
        db: Platform database.
        tenant_db: Firm database provider.
        clock: Time source.
        stop: Event that ends the loop.
        poll_seconds: Pause between passes.
        on_tick: Called with each pass's count of activations and finished jobs (used by tests and metrics).
        store: Export store, or None when exports are not configured.
    """
    while not stop.is_set():
        count = run_pass(db, tenant_db, clock, store)
        if on_tick is not None:
            on_tick(count)
        stop.wait(poll_seconds)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the worker from environment settings.

    Args:
        argv: Command-line arguments (defaults to sys.argv).

    Returns:
        0 on a clean stop.

    Raises:
        RuntimeError: If MONGODB_URI is not set.
        pydantic.ValidationError: If settings are invalid.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="run a single pass and exit")
    args = parser.parse_args(argv)
    settings = load_settings()
    if settings.mongodb_uri is None:
        raise RuntimeError("MONGODB_URI is not set")
    configure_logging(settings.log_level)
    client: MongoClientT = MongoClient[Doc](
        settings.mongodb_uri.get_secret_value(), serverSelectionTimeoutMS=SERVER_SELECTION_TIMEOUT_MS, tz_aware=True,
    )
    db, tenant_db = client[settings.platform_db], TenantDb(client)
    store = store_from_settings(settings)
    try:
        if args.once:
            run_pass(db, tenant_db, utc_now, store)
            return EXIT_OK
        stop = threading.Event()

        def _stop(_signum: int, _frame: FrameType | None) -> None:
            stop.set()

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)
        run_loop(db, tenant_db, utc_now, stop, store=store)
    finally:
        client.close()
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
