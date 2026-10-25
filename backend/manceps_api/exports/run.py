"""Export jobs: queue an export of one entity with filters, and the worker step that writes and stores the file.

Records are read through the repositories' own list functions (live records only, the same filters as the list
routes), page by page, so memory stays flat. Every value is escaped against formula injection by the writer.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument

from manceps_core.clock import Clock
from manceps_core.mongo import Doc, MongoDb
from manceps_core.repo import brokers, carriers, contacts, fleet
from manceps_core.repo.errors import RepoError

from ..imports.header import as_map
from .store import ExportStore, StoreError
from .writer import export_filename, write_csv, write_xlsx

EXPORTS = "exports"
QUEUED, RUNNING, READY, FAILED = "queued", "running", "ready", "failed"
FORMATS = ("csv", "xlsx")
PAGE_SIZE = 500
EXPORT_MAX_ROWS = 100_000
LEASE = timedelta(minutes=10)
RETENTION = timedelta(hours=24)
DOWNLOAD_URL_TTL = timedelta(minutes=5)

Lister = Callable[[MongoDb, Mapping[str, Any], ObjectId | None, int], list[Doc]]


class ExportTooLarge(RuntimeError):
    """The export would hold more than EXPORT_MAX_ROWS rows."""


@dataclass(frozen=True)
class ExportSpec:
    """How one entity is exported."""

    lister: Lister
    columns: tuple[str, ...]
    filters: frozenset[str]


def _fleet(kind: str) -> Lister:
    """Bind the fleet lister to drivers or trucks.

    Args:
        kind: driver or truck.

    Returns:
        The lister.
    """
    return lambda db, filters, after, limit: fleet.list_records(db, kind, filters, after, limit)


EXPORT_SPECS: Mapping[str, ExportSpec] = {
    "carriers": ExportSpec(carriers.list_carriers, (
        "id", "phone", "name", "company", "mc_number", "dot_number", "email", "status", "equipment", "home_base",
        "tags", "insurance_expires_at", "dispatch_fee_pct", "rate_floor_per_mile", "agreement_signed", "notes",
        "created_at", "updated_at"), frozenset({"status", "equipment", "tag", "q"})),
    "drivers": ExportSpec(_fleet("driver"), (
        "id", "carrier_id", "name", "phone", "email", "status", "license_state", "license_expires_at", "created_at",
        "updated_at"), frozenset({"carrier_id", "status"})),
    "trucks": ExportSpec(_fleet("truck"), (
        "id", "carrier_id", "unit", "equipment", "vin", "plate", "plate_state", "max_weight_lbs", "created_at",
        "updated_at"), frozenset({"carrier_id"})),
    "brokers": ExportSpec(brokers.list_brokers, (
        "id", "mc_number", "dot_number", "company", "tags", "payment_terms", "credit_notes", "last_check.verdict",
        "created_at", "updated_at"), frozenset({"q", "tag"})),
    "contacts": ExportSpec(contacts.list_contacts, (
        "id", "kind", "name", "company", "title", "phones", "emails", "tags", "source", "created_at", "updated_at"),
        frozenset({"kind", "tag", "q"})),
    "facilities": ExportSpec(contacts.list_facilities, (
        "id", "name", "address", "city", "state", "zip", "hours", "detention_notes", "created_at", "updated_at"),
        frozenset({"state", "city", "q"})),
}


def request_export(db: MongoDb, entity: str, file_format: str, filters: Mapping[str, str], who: Mapping[str, Any],
                   now: datetime) -> Doc:
    """Queue an export for the worker.

    Args:
        db: Firm database.
        entity: Entity name (a key of EXPORT_SPECS).
        file_format: csv or xlsx.
        filters: Validated filters.
        who: Requester {kind, id}.
        now: Current time.

    Returns:
        The queued export.
    """
    doc: Doc = {"_id": ObjectId(), "entity": entity, "format": file_format, "filters": dict(filters),
                "status": QUEUED, "rows": None, "filename": None, "file_key": None, "size_bytes": None,
                "error": None, "created_by": dict(who), "created_at": now, "updated_at": now,
                "expires_at": now + RETENTION, "lease_until": None}
    db[EXPORTS].insert_one(doc)
    return doc


def _value(doc: Doc, column: str) -> Any:
    """Read a column, following dotted paths ("last_check.verdict").

    Args:
        doc: Record.
        column: Column name.

    Returns:
        The value (id as text).
    """
    if column == "id":
        return str(doc["_id"])
    value: Any = doc
    for part in column.split("."):
        value = as_map(value).get(part)
    return value


def records(db: MongoDb, spec: ExportSpec, filters: Mapping[str, Any]) -> Iterator[list[Any]]:
    """Read every matching live record, page by page.

    Args:
        db: Firm database.
        spec: Export spec.
        filters: Filters.

    Yields:
        One row of values per record.

    Raises:
        ExportTooLarge: Past EXPORT_MAX_ROWS.
    """
    after: ObjectId | None = None
    count = 0
    while True:
        page = spec.lister(db, filters, after, PAGE_SIZE)
        for doc in page[:PAGE_SIZE]:
            count += 1
            if count > EXPORT_MAX_ROWS:
                raise ExportTooLarge(f"more than {EXPORT_MAX_ROWS} rows")
            yield [_value(doc, column) for column in spec.columns]
        if len(page) <= PAGE_SIZE:
            return
        after = page[PAGE_SIZE - 1]["_id"]


def _claim(db: MongoDb, export_id: ObjectId, now: datetime) -> Doc | None:
    """Take a queued export (or one whose worker died).

    Args:
        db: Firm database.
        export_id: Export id.
        now: Current time.

    Returns:
        The export, or None when there is nothing to do.
    """
    runnable = {"$or": [{"status": QUEUED}, {"status": RUNNING, "lease_until": {"$lt": now}}]}
    return db[EXPORTS].find_one_and_update({"_id": export_id, **runnable},
                                           {"$set": {"status": RUNNING, "lease_until": now + LEASE,
                                                     "updated_at": now}}, return_document=ReturnDocument.AFTER)


def _write(job: Doc, folder: Path, now: datetime, rows: Iterator[list[Any]]) -> tuple[Path, int]:
    """Write the file into a temporary folder.

    Args:
        job: Export document.
        folder: Temporary folder.
        now: Current time.
        rows: Rows to write.

    Returns:
        (file path, row count).
    """
    spec = EXPORT_SPECS[job["entity"]]
    path = folder / export_filename(job["entity"], job["format"], job["created_at"] or now)
    writer = write_xlsx if job["format"] == "xlsx" else write_csv
    return path, writer(path, spec.columns, rows)


def run_export(db: MongoDb, tenant_id: str, store: ExportStore, export_id: ObjectId, clock: Clock) -> bool:
    """Build and store one export file.

    Args:
        db: Firm database.
        tenant_id: The firm (first part of the storage key).
        store: Export store.
        export_id: Export id.
        clock: Time source.

    Returns:
        True when this call finished the export (ready or failed); False when there was nothing to do.
    """
    job = _claim(db, export_id, clock())
    if job is None:
        return False
    try:
        with tempfile.TemporaryDirectory(prefix="manceps-export-") as folder:
            path, count = _write(job, Path(folder), clock(), records(db, EXPORT_SPECS[job["entity"]], job["filters"]))
            key = f"{tenant_id}/{job['_id']}/{path.name}"
            size = store.put(key, path)
    except ExportTooLarge:
        return _fail(db, job, "too_many_rows", clock)
    except RepoError:
        return _fail(db, job, "invalid_filter", clock)
    except (StoreError, OSError):
        return _fail(db, job, "store_failed", clock)
    now = clock()
    db[EXPORTS].update_one({"_id": job["_id"], "status": RUNNING},
                           {"$set": {"status": READY, "rows": count, "filename": path.name, "file_key": key,
                                     "size_bytes": size, "ready_at": now, "updated_at": now, "lease_until": None}})
    return True


def _fail(db: MongoDb, job: Doc, reason: str, clock: Clock) -> bool:
    """Mark an export failed.

    Args:
        db: Firm database.
        job: Export document.
        reason: Error code.
        clock: Time source.

    Returns:
        True (the export is finished).
    """
    db[EXPORTS].update_one({"_id": job["_id"], "status": RUNNING},
                           {"$set": {"status": FAILED, "error": reason, "updated_at": clock(), "lease_until": None}})
    return True
