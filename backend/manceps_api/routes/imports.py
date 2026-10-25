"""Imports: templates, upload, status, mapping, preview, report, commit (a worker job), undo and history.

The upload is idempotent by content: the same entity and file bytes return the first import (200 with
`Idempotency-Replayed: true`) instead of creating a second one, so the route needs no Idempotency-Key. Auth and the
role are checked before the multipart body is parsed.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData, UploadFile

from manceps_core.mongo import Doc, MongoDb
from manceps_core.repo.errors import Invalid
from manceps_core.repo.store import DESCENDING, list_live
from manceps_core.tenancy import Principal

from ..auditing import write_context
from ..auth.principal import FirmDispatcher, FirmViewer
from ..context import firm_db, get_context
from ..errors import REPLAY_HEADER, ApiError
from ..exports.writer import content_disposition, csv_lines, csv_text
from ..firmzone import firm_zone
from ..imports import pipeline, records
from ..imports.schema import ENTITIES, ENTITY_SPECS
from ..imports.undo import undo_import
from ..pagination import DEFAULT_LIMIT, CursorQuery, LimitQuery, Page, decode_cursor, encode_cursor
from .common import RecordId, can_set_terms
from .import_models import (
    CommitIn,
    ImportEntity,
    ImportOut,
    MappingIn,
    PreviewOut,
    ReportFormat,
    ReportRow,
    Strategy,
    render_import,
    render_preview_row,
    render_report_row,
)

router = APIRouter(prefix="/v1", tags=["imports"])

PREVIEW_ROWS = 50
MAX_FORM_FIELDS = 4
MAX_FIELD_BYTES = 1024
CSV_MEDIA = "text/csv; charset=utf-8"
REPORT_CHUNK_ROWS = 500
REPORT_BASE_COLUMNS = ("row_no", "action", "reason", "errors", "target_id", "outcome", "undo")
NOT_MAPPED = frozenset({records.UPLOADED, pipeline.VALIDATING})
UPLOAD_BODY: dict[str, Any] = {"requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {
    "type": "object", "required": ["entity", "file"], "properties": {
        "entity": {"type": "string", "enum": list(ENTITIES)},
        "file": {"type": "string", "format": "binary",
                 "description": ".csv or .xlsx (any entity) or .vcf (contacts); max IMPORT_MAX_BYTES and "
                                "IMPORT_MAX_ROWS rows"}}}}}}}


def _who(principal: Principal) -> dict[str, str]:
    """Describe the caller for stored documents.

    Args:
        principal: Firm principal.

    Returns:
        {kind, id}.
    """
    return {"kind": principal.kind, "id": principal.user_id}


def _template(entity: str) -> str:
    """Render the header row of an entity's CSV template.

    Args:
        entity: Entity name.

    Returns:
        CSV text.
    """
    spec = ENTITY_SPECS[entity]
    return csv_text([spec.fields[name].label for name in spec.template], [])


@router.get("/imports/templates/{entity}", operation_id="imports_template", summary="Download a CSV template",
            response_class=Response, responses={200: {"content": {"text/csv": {}}}})
def imports_template(entity: ImportEntity, principal: FirmViewer) -> Response:
    """Return a CSV header row whose columns map onto the entity's fields.

    Args:
        entity: carriers, drivers, brokers or contacts.
        principal: Firm member.

    Returns:
        text/csv attachment.
    """
    return Response(_template(entity), media_type=CSV_MEDIA,
                    headers={"Content-Disposition": content_disposition(f"{entity}-template.csv")})


def _upload_parts(form: FormData) -> tuple[str, UploadFile]:
    """Check the two multipart parts.

    Args:
        form: Parsed form.

    Returns:
        (entity, file).

    Raises:
        Invalid: 422 when entity or file is missing or entity is unknown.
    """
    entity, upload = form.get("entity"), form.get("file")
    if not isinstance(entity, str) or entity not in ENTITIES:
        raise Invalid("entity", f"entity must be one of {', '.join(ENTITIES)}")
    if not isinstance(upload, UploadFile):
        raise Invalid("file", "attach the file to import")
    return entity, upload


@router.post("/imports", status_code=201, operation_id="imports_create", summary="Upload a file to import",
             openapi_extra=UPLOAD_BODY, responses={200: {"model": ImportOut, "description": "Same file again"}})
async def imports_create(request: Request, response: Response, principal: FirmDispatcher) -> ImportOut:
    """Upload a CSV, XLSX or vCard file; rows are parsed, mapped by header names and checked.

    Args:
        request: Incoming request (multipart: entity, file).
        response: Response (status 200 and the replay header for an identical earlier upload).
        principal: Dispatcher or owner.

    Returns:
        The import (status mapped, or uploaded when required columns still need a mapping).

    Raises:
        ImportFileError: 413 file_too_large, 415 unsupported_file_type, 422 too_many_rows, no_header...
    """
    context = get_context(request)
    settings = context.settings
    form = await request.form(max_files=1, max_fields=MAX_FORM_FIELDS, max_part_size=MAX_FIELD_BYTES)
    try:
        entity, upload = _upload_parts(form)
        job = pipeline.Upload(entity=entity, filename=upload.filename or "", stream=upload.file,
                              allow_sensitive=can_set_terms(principal), who=_who(principal), now=context.clock(),
                              max_bytes=settings.import_max_bytes, max_rows=settings.import_max_rows,
                              timezone=firm_zone(request, principal).key)
        doc, replayed = await run_in_threadpool(pipeline.ingest, firm_db(request, principal), job)
    finally:
        await form.close()
    if replayed:
        response.status_code = 200
        response.headers[REPLAY_HEADER] = "true"
    return render_import(doc)


@router.get("/imports", operation_id="imports_list", summary="List imports")
def imports_list(request: Request, principal: FirmViewer, limit: LimitQuery = DEFAULT_LIMIT,
                 cursor: CursorQuery = None) -> Page[ImportOut]:
    """List the firm's imports, newest first.

    Args:
        request: Incoming request.
        principal: Firm member.
        limit: Page size.
        cursor: Cursor from the previous page.

    Returns:
        One page.

    Raises:
        ApiError: 400 invalid_cursor.
    """
    docs = list_live(firm_db(request, principal), records.IMPORTS, {}, decode_cursor(cursor), limit, DESCENDING)
    page = docs[:limit]
    return Page[ImportOut](items=[render_import(doc) for doc in page],
                           next_cursor=encode_cursor(page[-1]["_id"]) if len(docs) > limit else None)


@router.get("/imports/{import_id}", operation_id="imports_get", summary="Get an import")
def imports_get(import_id: RecordId, request: Request, principal: FirmViewer) -> ImportOut:
    """Return an import: status (poll it while committing), columns, mapping and counters.

    Args:
        import_id: Import id.
        request: Incoming request.
        principal: Firm member.

    Returns:
        The import.

    Raises:
        RepoError: 404.
    """
    return render_import(records.load_import(firm_db(request, principal), import_id))


@router.put("/imports/{import_id}/mapping", operation_id="imports_map", summary="Set the column mapping")
def imports_map(import_id: RecordId, body: MappingIn, request: Request, principal: FirmDispatcher) -> ImportOut:
    """Map columns to fields and re-check every row. Consent can never be a target.

    Args:
        import_id: Import id.
        body: Column to field.
        request: Incoming request.
        principal: Dispatcher or owner.

    Returns:
        The re-checked import.

    Raises:
        ApiError: 404, 409 import_locked, 422 unknown_column, unknown_field, field_not_importable,
            duplicate_field or required_field_unmapped.
    """
    db = firm_db(request, principal)
    doc = pipeline.remap(db, import_id, body.mapping, can_set_terms(principal), get_context(request).clock())
    return render_import(doc)


def _mapped(db: MongoDb, import_id: str) -> Doc:
    """Load an import whose rows have been checked.

    Args:
        db: Firm database.
        import_id: Import id.

    Returns:
        The import.

    Raises:
        ApiError: 404, or 409 mapping_required.
    """
    doc = records.load_import(db, import_id)
    if doc["status"] in NOT_MAPPED:
        raise ApiError(409, "mapping_required", "map the required columns first")
    return doc


@router.get("/imports/{import_id}/preview", operation_id="imports_preview", summary="Preview an import")
def imports_preview(import_id: RecordId, request: Request, principal: FirmViewer,
                    duplicate_strategy: Strategy = "update") -> PreviewOut:
    """Show the first rows with the action a commit would take, and the action counts for the whole file.

    Args:
        import_id: Import id.
        request: Incoming request.
        principal: Firm member.
        duplicate_strategy: skip, update or merge for rows matching an existing record.

    Returns:
        The preview.

    Raises:
        ApiError: 404, 409 mapping_required.
    """
    db = firm_db(request, principal)
    doc = _mapped(db, import_id)
    allow = bool(doc.get("allow_sensitive"))
    rows = db[records.IMPORT_ROWS].find({"import_id": doc["_id"]}).sort([("row_no", 1)]).limit(PREVIEW_ROWS)
    return PreviewOut(duplicate_strategy=duplicate_strategy,
                      counts=records.strategy_counts(doc["stats"], duplicate_strategy),
                      rows=[render_preview_row(row, list(doc["columns"]), duplicate_strategy, allow) for row in rows])


def _report_csv(db: MongoDb, doc: Doc) -> Iterator[str]:
    """Stream the full report as escaped CSV.

    Args:
        db: Firm database.
        doc: Import.

    Yields:
        CSV text chunks.
    """
    columns = list(doc["columns"])
    strategy, allow = doc.get("duplicate_strategy") or records.DEFAULT_STRATEGY, bool(doc.get("allow_sensitive"))
    yield csv_text([*REPORT_BASE_COLUMNS, *columns], [])
    chunk: list[list[Any]] = []
    for row in db[records.IMPORT_ROWS].find({"import_id": doc["_id"]}).sort([("row_no", 1)]):
        item = render_report_row(row, strategy, allow)
        errors = "; ".join(f"{error.field or 'row'}: {error.message}" for error in item.errors)
        chunk.append([item.row_no, item.outcome or item.action, item.reason, errors, item.target_id, item.outcome,
                      item.undo, *(row.get("cells") or [None] * len(columns))])
        if len(chunk) >= REPORT_CHUNK_ROWS:
            yield csv_lines(chunk)
            chunk = []
    if chunk:
        yield csv_lines(chunk)


@router.get("/imports/{import_id}/report", operation_id="imports_report", summary="Validation and commit report",
            response_model=Page[ReportRow], responses={200: {"content": {"text/csv": {}}}})
def imports_report(import_id: RecordId, request: Request, principal: FirmViewer, format: ReportFormat = "json",
                   limit: LimitQuery = DEFAULT_LIMIT, cursor: CursorQuery = None) -> Any:
    """Every row with its errors, action and (after a commit or undo) outcome; `format=csv` for a spreadsheet.

    Args:
        import_id: Import id.
        request: Incoming request.
        principal: Firm member.
        format: json (paged) or csv (the whole file, formula-escaped).
        limit: Page size (json).
        cursor: Cursor from the previous page (json).

    Returns:
        A page of rows, or a CSV attachment.

    Raises:
        ApiError: 404, 400 invalid_cursor.
    """
    db = firm_db(request, principal)
    doc = records.load_import(db, import_id)
    if format == "csv":
        name = content_disposition(f"import-{doc['_id']}-report.csv")
        return StreamingResponse(_report_csv(db, doc), media_type=CSV_MEDIA, headers={"Content-Disposition": name})
    after = decode_cursor(cursor)
    query: dict[str, Any] = {"import_id": doc["_id"], **({"_id": {"$gt": after}} if after else {})}
    rows = list(db[records.IMPORT_ROWS].find(query).sort([("_id", 1)]).limit(limit + 1))
    strategy, allow = doc.get("duplicate_strategy") or records.DEFAULT_STRATEGY, bool(doc.get("allow_sensitive"))
    page = rows[:limit]
    return Page[ReportRow](items=[render_report_row(row, strategy, allow) for row in page],
                           next_cursor=encode_cursor(page[-1]["_id"]) if len(rows) > limit else None)


@router.post("/imports/{import_id}/commit", status_code=202, operation_id="imports_commit",
             summary="Commit an import (runs as a job)",
             responses={200: {"model": ImportOut, "description": "Commit already requested"}})
def imports_commit(import_id: RecordId, body: CommitIn, request: Request, response: Response,
                   principal: FirmDispatcher) -> ImportOut:
    """Queue the commit; poll GET /v1/imports/{id}. Asking again returns the first request (200, replayed).

    Rows with carrier fee, floor or agreement values are written only when the owner commits; for a dispatcher
    they are rejected with reason approval_required.

    Args:
        import_id: Import id.
        body: Duplicate strategy.
        request: Incoming request.
        response: Response (200 and the replay header when already requested).
        principal: Dispatcher or owner.

    Returns:
        The import (status committing).

    Raises:
        ApiError: 404, 409 mapping_required, import_undone, import_failed, import_busy or import_expired.
    """
    context = get_context(request)
    doc, replayed = pipeline.request_commit(firm_db(request, principal), import_id, body.duplicate_strategy,
                                            _who(principal), can_set_terms(principal), context.clock(),
                                            context.settings.import_undo_hours)
    if replayed:
        response.status_code = 200
        response.headers[REPLAY_HEADER] = "true"
    return render_import(doc)


@router.post("/imports/{import_id}/undo", operation_id="imports_undo", summary="Undo a committed import")
def imports_undo(import_id: RecordId, request: Request, principal: FirmDispatcher) -> ImportOut:
    """Within IMPORT_UNDO_HOURS: restore updated records and remove created ones that nothing changed since.

    Args:
        import_id: Import id.
        request: Incoming request.
        principal: Dispatcher or owner.

    Returns:
        The undone import with its undo counts.

    Raises:
        ApiError: 404, 409 undo_window_closed, already_undone, undo_in_progress or import_not_committed.
    """
    context = get_context(request)
    db = firm_db(request, principal)
    return render_import(undo_import(db, write_context(request, principal), import_id, context.clock))
