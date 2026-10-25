"""Exports: queue a CSV or XLSX export of one entity (a worker job), poll it, and download the file.

Without a configured ExportStore (production before object storage is set up) every export route answers 503
`exports_not_configured`. Downloads need the same bearer token as the API; `download_url` points at the
authenticated download route for the filesystem store, or at a short-lived presigned URL for object storage.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import BinaryIO

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from manceps_core.mongo import Doc
from manceps_core.repo import fields
from manceps_core.repo.errors import Invalid
from manceps_core.repo.store import get_by_id

from ..auth.principal import FirmDispatcher, FirmIdempotency, FirmViewer
from ..context import AppContext, firm_db, get_context
from ..errors import ApiError
from ..exports.run import DOWNLOAD_URL_TTL, EXPORT_SPECS, EXPORTS, READY, request_export
from ..exports.store import ExportStore, StoreError
from ..exports.writer import content_disposition
from .common import RecordId
from .import_models import ExportIn, ExportOut, render_export

router = APIRouter(prefix="/v1", tags=["exports"])

CHUNK_BYTES = 64 * 1024
MEDIA_TYPES = {"csv": "text/csv; charset=utf-8",
               "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def _store(context: AppContext) -> ExportStore:
    """Return the export store or refuse.

    Args:
        context: Application context.

    Returns:
        The store.

    Raises:
        ApiError: 503 exports_not_configured.
    """
    if context.export_store is None:
        raise ApiError(503, "exports_not_configured", "exports are not configured on this server")
    return context.export_store


def _filters(body: ExportIn) -> dict[str, str]:
    """Check the filters are ones the entity's list route accepts.

    Args:
        body: Request.

    Returns:
        The filters that were set.

    Raises:
        Invalid: 422 filter_not_allowed, or a malformed state code.
    """
    chosen = body.filters.model_dump(exclude_none=True)
    allowed = EXPORT_SPECS[body.entity].filters
    for name in chosen:
        if name not in allowed:
            raise Invalid(["filters", name], f"{body.entity} exports cannot filter on {name}", "filter_not_allowed")
    if "state" in chosen:
        chosen["state"] = fields.state("filters.state", chosen["state"])
    return chosen


def _download_url(context: AppContext, doc: Doc) -> str | None:
    """Say where a ready export can be downloaded.

    Args:
        context: Application context.
        doc: Export.

    Returns:
        A presigned URL, the authenticated download route, or None when not ready or expired.
    """
    if doc["status"] != READY or context.clock() > doc["expires_at"] or context.export_store is None:
        return None
    direct = context.export_store.url_for(doc["file_key"], DOWNLOAD_URL_TTL)
    if direct is not None:
        return direct
    path = f"/v1/exports/{doc['_id']}/download"
    base = context.settings.public_base_url
    return f"{base.rstrip('/')}{path}" if base else path


@router.post("/exports", status_code=202, operation_id="exports_create", summary="Export records (runs as a job)")
def exports_create(body: ExportIn, request: Request, principal: FirmDispatcher, guard: FirmIdempotency) -> ExportOut:
    """Queue a CSV or XLSX export of live records with the entity's list filters; poll GET /v1/exports/{id}.

    Args:
        body: Entity, format and filters.
        request: Incoming request.
        principal: Dispatcher or owner.
        guard: Idempotency guard (Idempotency-Key header optional).

    Returns:
        The queued export.

    Raises:
        ApiError: 503 exports_not_configured.
        RepoError: 422 filter_not_allowed.
    """
    context = get_context(request)
    _store(context)
    doc = request_export(firm_db(request, principal), body.entity, body.format, _filters(body),
                         {"kind": principal.kind, "id": principal.user_id}, context.clock())
    export = render_export(doc, None)
    guard.save(202, export.model_dump(mode="json"))
    return export


@router.get("/exports/{export_id}", operation_id="exports_get", summary="Get an export")
def exports_get(export_id: RecordId, request: Request, principal: FirmViewer) -> ExportOut:
    """Return an export's status and, once ready, its download URL.

    Args:
        export_id: Export id.
        request: Incoming request.
        principal: Firm member.

    Returns:
        The export.

    Raises:
        RepoError: 404.
    """
    context = get_context(request)
    doc = get_by_id(firm_db(request, principal), EXPORTS, export_id, "export")
    return render_export(doc, _download_url(context, doc))


def _chunks(handle: BinaryIO) -> Iterator[bytes]:
    """Stream a file and close it.

    Args:
        handle: Open file.

    Yields:
        Byte chunks.
    """
    with handle:
        while chunk := handle.read(CHUNK_BYTES):
            yield chunk


@router.get("/exports/{export_id}/download", operation_id="exports_download", summary="Download an export",
            response_class=StreamingResponse,
            responses={200: {"content": {"text/csv": {}, MEDIA_TYPES["xlsx"]: {}}}})
def exports_download(export_id: RecordId, request: Request, principal: FirmViewer) -> StreamingResponse:
    """Stream a ready export file.

    Args:
        export_id: Export id.
        request: Incoming request.
        principal: Firm member.

    Returns:
        The file as an attachment.

    Raises:
        ApiError: 404, 409 export_not_ready, 410 export_expired, 503 exports_not_configured.
    """
    context = get_context(request)
    doc = get_by_id(firm_db(request, principal), EXPORTS, export_id, "export")
    store = _store(context)
    if doc["status"] != READY:
        raise ApiError(409, "export_not_ready", "this export is not ready yet")
    if context.clock() > doc["expires_at"]:
        raise ApiError(410, "export_expired", "this export has expired; export again")
    try:
        handle = store.open(doc["file_key"])
    except StoreError as exc:
        raise ApiError(410, "export_expired", "this export file is no longer available") from exc
    return StreamingResponse(_chunks(handle), media_type=MEDIA_TYPES[doc["format"]],
                             headers={"Content-Disposition": content_disposition(doc["filename"])})
