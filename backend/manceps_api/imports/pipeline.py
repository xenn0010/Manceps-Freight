"""Upload, re-map and commit requests: everything an import does inside the API process.

Upload: hash and size-check the stream, replay an earlier import of the same content, sniff the type, parse rows in
batches, check each batch with the repository rules, store the rows, and only then store the import document (its
unique `idempotency_hash` decides a race between identical uploads; the loser's rows are removed). Any failure
removes the rows already written, so a refused file leaves nothing behind.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, BinaryIO

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from manceps_core.mongo import Doc, MongoDb

from ..errors import ApiError
from . import mapping as mappings
from .errors import UNPROCESSABLE, ImportFileError, RowError
from .header import ParsedRow, as_list, as_map
from .parsers import ParsedFile, parse_file
from .records import (
    COMMIT_MAX_AGE,
    COMMITTED,
    COMMITTING,
    FAILED,
    IMPORT_ROWS,
    IMPORTS,
    MAPPED,
    ROWS_TTL,
    UNDOING,
    UNDONE,
    UPLOADED,
    empty_stats,
    epoch_name,
    epoch_of,
    load_import,
    mapping_of,
    mapping_pairs,
    tally,
)
from .sniff import FileType, detect_type, hash_upload, sanitize_filename
from .validate import RowCheck, check_row, classify, parse_error_check, read_row

BATCH_ROWS = 500
VALIDATING = "validating"
VALIDATION_LOCK = timedelta(minutes=10)
CONFLICT = 409
SOURCES: Mapping[str, str] = {"vcf": "vcard", "google": "google"}
DEFAULT_SOURCE = "import"


@dataclass(frozen=True)
class Upload:
    """One uploaded file and who sent it."""

    entity: str
    filename: str
    stream: BinaryIO
    allow_sensitive: bool
    who: Mapping[str, Any]
    now: datetime
    max_bytes: int
    max_rows: int


@dataclass(frozen=True)
class _Sheet:
    """What row checks need to know about the file."""

    entity: str
    columns: Sequence[str]
    mapping: Mapping[str, str | None]
    epoch: datetime | None
    checked: bool


def _batches(rows: Iterable[ParsedRow]) -> Iterator[list[ParsedRow]]:
    """Group rows into batches of BATCH_ROWS.

    Args:
        rows: Rows in file order.

    Yields:
        Batches.
    """
    batch: list[ParsedRow] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= BATCH_ROWS:
            yield batch
            batch = []
    if batch:
        yield batch


def _check_batch(db: MongoDb, sheet: _Sheet, batch: Sequence[ParsedRow], seen: dict[str, int],
                 cache: dict[str, str | None]) -> list[tuple[int, RowCheck]]:
    """Check a batch of rows (or leave them unchecked while required fields are unmapped).

    Args:
        db: Firm database.
        sheet: File context.
        batch: Rows.
        seen: Natural keys already seen in the file.
        cache: Carrier lookups.

    Returns:
        (row number, check) per row.
    """
    checks: list[tuple[int, RowCheck]] = []
    for row in batch:
        if row.error is not None:
            checks.append((row.row_no, parse_error_check(row.error)))
        elif not sheet.checked:
            checks.append((row.row_no, RowCheck({}, [], [], None)))
        else:
            values, errors = read_row(sheet.entity, sheet.columns, sheet.mapping, row.cells or (), sheet.epoch)
            checks.append((row.row_no, check_row(db, sheet.entity, values, errors, cache)))
    if sheet.checked:
        classify(db, sheet.entity, checks, seen)
    return checks


def _store_rows(db: MongoDb, import_id: ObjectId, sheet: _Sheet, rows: Iterable[ParsedRow], now: datetime,
                allow_sensitive: bool) -> dict[str, int]:
    """Check and insert every row; return the counters.

    Args:
        db: Firm database.
        import_id: Import id the rows belong to.
        sheet: File context.
        rows: Parsed rows (iterating may raise ImportFileError, e.g. too_many_rows).
        now: Current time.
        allow_sensitive: The uploader may set carrier terms directly.

    Returns:
        Counters.
    """
    stats = empty_stats()
    seen: dict[str, int] = {}
    cache: dict[str, str | None] = {}
    for batch in _batches(rows):
        checks = _check_batch(db, sheet, batch, seen, cache)
        docs: list[Doc] = []
        for row, (_row_no, check) in zip(batch, checks, strict=True):
            _count(stats, check, allow_sensitive, sheet.checked)
            docs.append({"_id": ObjectId(), "import_id": import_id, "row_no": row.row_no, "target_id": ObjectId(),
                         "cells": None if row.cells is None else list(row.cells), **check.as_doc(), "outcome": None,
                         "expires_at": now + ROWS_TTL})
        db[IMPORT_ROWS].insert_many(docs, ordered=True)
    return stats


def _count(stats: dict[str, int], check: RowCheck, allow_sensitive: bool, checked: bool) -> None:
    """Count a row: fully when checked, only as a row otherwise.

    Args:
        stats: Counters.
        check: The row's check.
        allow_sensitive: Uploader may set terms.
        checked: Whether rows were validated.
    """
    if checked:
        tally(stats, check, allow_sensitive)
    else:
        stats["rows"] += 1


def _source(file_type: FileType, columns: Sequence[str]) -> str:
    """Name where contacts came from.

    Args:
        file_type: File type.
        columns: Headers.

    Returns:
        vcard, google or import.
    """
    if file_type == "csv" and mappings.is_google_contacts(columns):
        return SOURCES["google"]
    return SOURCES.get(file_type, DEFAULT_SOURCE)


def _new_doc(import_id: ObjectId, upload: Upload, parsed: ParsedFile, digest: str, size: int) -> Doc:
    """Build the import document (stats are filled in after the rows are stored).

    Args:
        import_id: New id.
        upload: The upload.
        parsed: Parsed file.
        digest: Content hash.
        size: File size.

    Returns:
        The document.
    """
    suggested = mappings.suggest_mapping(upload.entity, parsed.columns)
    missing = mappings.unmapped_required(upload.entity, suggested)
    return {"_id": import_id, "entity": upload.entity, "source_filename": sanitize_filename(upload.filename),
            "file_type": parsed.file_type, "size_bytes": size, "columns": list(parsed.columns),
            "header_row": parsed.header_row or None, "epoch": epoch_name(parsed.epoch),
            "source": _source(parsed.file_type, parsed.columns), "mapping": mapping_pairs(suggested),
            "suggested_mapping": mapping_pairs(suggested), "unmapped_required": missing,
            "ignored_consent_columns": mappings.consent_columns(parsed.columns),
            "status": UPLOADED if missing else MAPPED, "allow_sensitive": upload.allow_sensitive,
            "idempotency_hash": digest, "created_by": dict(upload.who), "created_at": upload.now,
            "updated_at": upload.now, "duplicate_strategy": None, "undo_until": None, "progress": None}


def ingest(db: MongoDb, upload: Upload) -> tuple[Doc, bool]:
    """Store an upload as a new import, or return the import of identical content.

    Args:
        db: Firm database.
        upload: The upload.

    Returns:
        (import document, True when it is an earlier import replayed).

    Raises:
        ImportFileError: 413 file_too_large or archive_too_large, 415 unsupported_file_type, 422 no_header,
            too_many_columns, too_many_rows, invalid_workbook or vcard_contacts_only.
    """
    digest, size = hash_upload(upload.stream, upload.entity.encode("utf-8"), upload.max_bytes)
    existing = db[IMPORTS].find_one({"idempotency_hash": digest})
    if existing is not None:
        return existing, True
    file_type = detect_type(upload.filename, upload.stream)
    if file_type == "vcf" and upload.entity != "contacts":
        raise ImportFileError(UNPROCESSABLE, "vcard_contacts_only", "vCard files can only be imported as contacts")
    parsed = parse_file(file_type, upload.stream, upload.max_rows)
    doc = _new_doc(ObjectId(), upload, parsed, digest, size)
    sheet = _Sheet(upload.entity, parsed.columns, mapping_of(doc), parsed.epoch, doc["status"] == MAPPED)
    try:
        doc["stats"] = _store_rows(db, doc["_id"], sheet, parsed.rows, upload.now, upload.allow_sensitive)
        db[IMPORTS].insert_one(doc)
    except DuplicateKeyError:
        db[IMPORT_ROWS].delete_many({"import_id": doc["_id"]})
        winner = db[IMPORTS].find_one({"idempotency_hash": digest})
        if winner is None:
            raise
        return winner, True
    except Exception:
        db[IMPORT_ROWS].delete_many({"import_id": doc["_id"]})
        raise
    return doc, False


def _claim_validation(db: MongoDb, import_id: ObjectId, now: datetime) -> Doc:
    """Lock an import for re-validation (refused once a commit started).

    Args:
        db: Firm database.
        import_id: Import id.
        now: Current time.

    Returns:
        The import as it was before the lock.

    Raises:
        ApiError: 409 import_locked when it is committing, committed or undone, or another re-map runs.
    """
    editable = {"$or": [{"status": {"$in": [UPLOADED, MAPPED]}},
                        {"status": VALIDATING, "updated_at": {"$lt": now - VALIDATION_LOCK}}]}
    before = db[IMPORTS].find_one_and_update({"_id": import_id, **editable},
                                             {"$set": {"status": VALIDATING, "updated_at": now}})
    if before is None:
        raise ApiError(CONFLICT, "import_locked", "this import can no longer be re-mapped")
    return before


def remap(db: MongoDb, raw_id: Any, proposed: Mapping[str, str | None], allow_sensitive: bool,
          now: datetime) -> Doc:
    """Apply a new mapping and re-check every row.

    Args:
        db: Firm database.
        raw_id: Import id.
        proposed: Column to field from the client.
        allow_sensitive: The caller may set carrier terms directly.
        now: Current time.

    Returns:
        The updated import.

    Raises:
        NotFound: Unknown import.
        ApiError: 422 mapping errors, 409 import_locked.
    """
    current = load_import(db, raw_id)
    complete = mappings.check_mapping(current["entity"], current["columns"], proposed)
    before = _claim_validation(db, current["_id"], now)
    sheet = _Sheet(before["entity"], before["columns"], complete, epoch_of(before), True)
    stats = _recheck_rows(db, before["_id"], sheet, allow_sensitive)
    updated = db[IMPORTS].find_one_and_update(
        {"_id": before["_id"], "status": VALIDATING},
        {"$set": {"mapping": mapping_pairs(complete), "status": MAPPED, "stats": stats, "unmapped_required": [],
                  "allow_sensitive": allow_sensitive, "updated_at": now}},
        return_document=ReturnDocument.AFTER)
    if updated is None:
        raise ApiError(CONFLICT, "import_locked", "this import was changed by another request")
    return updated


def _stored_rows(db: MongoDb, import_id: ObjectId) -> Iterator[tuple[ObjectId, ParsedRow]]:
    """Read stored rows back in file order.

    Args:
        db: Firm database.
        import_id: Import id.

    Yields:
        (row id, row as parsed).
    """
    cursor = db[IMPORT_ROWS].find({"import_id": import_id}, {"row_no": 1, "cells": 1, "errors": 1})
    for doc in cursor.sort([("row_no", 1)]):
        cells = doc.get("cells")
        if cells is None:
            yield doc["_id"], ParsedRow(int(doc["row_no"]), None, _stored_parse_error(doc))
        else:
            yield doc["_id"], ParsedRow(int(doc["row_no"]), tuple(cells), None)


def _stored_parse_error(doc: Doc) -> RowError:
    """Rebuild the reader's error of a row stored without cells.

    Args:
        doc: Stored row.

    Returns:
        The error.
    """
    first = as_map((as_list(doc.get("errors")) or [{}])[0])
    return RowError(str(first.get("code") or "malformed_row"), str(first.get("message") or "unreadable row"),
                    first.get("field"))


def _recheck_rows(db: MongoDb, import_id: ObjectId, sheet: _Sheet, allow_sensitive: bool) -> dict[str, int]:
    """Re-check every stored row with a new mapping.

    Args:
        db: Firm database.
        import_id: Import id.
        sheet: File context with the new mapping.
        allow_sensitive: The caller may set carrier terms directly.

    Returns:
        Counters.
    """
    stats = empty_stats()
    seen: dict[str, int] = {}
    cache: dict[str, str | None] = {}
    pending: list[tuple[ObjectId, ParsedRow]] = []
    for item in _stored_rows(db, import_id):
        pending.append(item)
        if len(pending) >= BATCH_ROWS:
            _write_checks(db, sheet, pending, seen, cache, stats, allow_sensitive)
            pending = []
    if pending:
        _write_checks(db, sheet, pending, seen, cache, stats, allow_sensitive)
    return stats


def _write_checks(db: MongoDb, sheet: _Sheet, pending: Sequence[tuple[ObjectId, ParsedRow]], seen: dict[str, int],
                  cache: dict[str, str | None], stats: dict[str, int], allow_sensitive: bool) -> None:
    """Check one batch of stored rows and save the results.

    Args:
        db: Firm database.
        sheet: File context.
        pending: (row id, row).
        seen: Keys seen so far.
        cache: Carrier lookups.
        stats: Counters (updated in place).
        allow_sensitive: The caller may set carrier terms directly.
    """
    checks = _check_batch(db, sheet, [row for _id, row in pending], seen, cache)
    for (row_id, _row), (_row_no, check) in zip(pending, checks, strict=True):
        tally(stats, check, allow_sensitive)
        db[IMPORT_ROWS].update_one({"_id": row_id}, {"$set": check.as_doc()})


def request_commit(db: MongoDb, raw_id: Any, strategy: str, who: Mapping[str, Any], allow_sensitive: bool,
                   now: datetime, undo_hours: int) -> tuple[Doc, bool]:
    """Queue a commit for the worker; a commit already queued or done is returned as a replay.

    Args:
        db: Firm database.
        raw_id: Import id.
        strategy: skip, update or merge.
        who: Requesting user {kind, id}.
        allow_sensitive: The requester may set carrier terms directly.
        now: Current time.
        undo_hours: Length of the undo window once committed (IMPORT_UNDO_HOURS).

    Returns:
        (import, True when the commit had already been requested).

    Raises:
        NotFound: Unknown import.
        ApiError: 409 mapping_required, import_undone, import_failed, import_busy or import_expired.
    """
    current = load_import(db, raw_id)
    _refuse_commit(current, now)
    queued = db[IMPORTS].find_one_and_update(
        {"_id": current["_id"], "status": MAPPED},
        {"$set": {"status": COMMITTING, "duplicate_strategy": strategy, "commit_requested_by": dict(who),
                  "commit_allow_sensitive": allow_sensitive, "commit_requested_at": now, "lease_until": None,
                  "undo_hours": undo_hours,
                  "progress": {"done": 0, "total": current["stats"]["rows"]}, "updated_at": now}},
        return_document=ReturnDocument.AFTER)
    if queued is not None:
        return queued, False
    latest = load_import(db, current["_id"])
    _refuse_commit(latest, now)
    return latest, True


def _refuse_commit(doc: Doc, now: datetime) -> None:
    """Refuse a commit request for an import in the wrong state.

    Args:
        doc: Import.
        now: Current time.

    Raises:
        ApiError: 409 with the reason.
    """
    status = doc["status"]
    reasons = {UPLOADED: ("mapping_required", "map the required columns before committing"),
               VALIDATING: ("import_busy", "the import is being re-checked; try again"),
               UNDOING: ("import_undone", "this import was undone"),
               UNDONE: ("import_undone", "this import was undone"),
               FAILED: ("import_failed", "this import failed; upload the file again")}
    if status in reasons:
        raise ApiError(CONFLICT, *reasons[status])
    if status == MAPPED and doc["created_at"] < now - COMMIT_MAX_AGE:
        raise ApiError(CONFLICT, "import_expired", "this upload is too old to commit; upload the file again")
    if status not in (MAPPED, COMMITTING, COMMITTED):
        raise ApiError(CONFLICT, "import_locked", "this import cannot be committed")
