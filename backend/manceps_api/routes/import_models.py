"""Request and response models for imports and exports, and the renderers that build them from stored documents."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from manceps_core.mongo import Doc

from ..auth.models import StrictModel
from ..imports.header import as_list, as_map
from ..imports.parsers import MAX_COLUMNS
from ..imports.records import CHECK_STAT_KEYS, OUTCOME_STAT_KEYS, mapping_of, preview_action

COLUMN_MAX = 120
FIELD_MAX = 64
FILTER_MAX = 100

ImportEntity = Literal["carriers", "drivers", "brokers", "contacts"]
ExportEntity = Literal["carriers", "drivers", "trucks", "brokers", "contacts", "facilities"]
Strategy = Literal["skip", "update", "merge"]
ExportFormat = Literal["csv", "xlsx"]
ReportFormat = Literal["json", "csv"]
Column = Annotated[str, Field(min_length=1, max_length=COLUMN_MAX)]
FieldName = Annotated[str, Field(min_length=1, max_length=FIELD_MAX)]
FilterText = Annotated[str, Field(min_length=1, max_length=FILTER_MAX)]


class ImportStats(BaseModel):
    """Row counters: the check (rows ... existing) and, after the commit, what happened to each row."""

    rows: int
    valid: int
    invalid: int
    duplicates_in_file: int
    needs_approval: int = Field(description="Valid rows with carrier terms the uploader may not set directly.")
    new: int
    existing: int
    created: int
    updated: int
    merged: int
    skipped: int
    rejected: int


class ImportProgress(BaseModel):
    """Commit progress."""

    done: int
    total: int


class UndoCounts(BaseModel):
    """What an undo did."""

    restored: int
    removed: int
    skipped_modified: int


class ImportOut(BaseModel):
    """An import: the file, its detected columns and mapping, counters and status."""

    id: str
    entity: str
    source_filename: str
    file_type: str
    status: str = Field(description="uploaded, validating, mapped, committing, committed, failed, undoing, undone.")
    columns: list[str]
    header_row: int | None
    mapping: dict[str, str | None]
    suggested_mapping: dict[str, str | None]
    unmapped_required: list[str]
    ignored_consent_columns: list[str] = Field(description="Consent-like columns; consent is never imported.")
    stats: ImportStats
    duplicate_strategy: str | None
    progress: ImportProgress | None
    undo: UndoCounts | None
    undo_until: datetime | None
    created_at: datetime
    committed_at: datetime | None
    error: str | None


class MappingIn(StrictModel):
    """A column-to-field mapping; columns left out are not imported."""

    mapping: Annotated[dict[Column, FieldName | None], Field(max_length=MAX_COLUMNS)]


class CommitIn(StrictModel):
    """How to treat rows that match an existing record (merge fills empty fields only)."""

    duplicate_strategy: Strategy = "update"


class RowErrorOut(BaseModel):
    """One problem with a row."""

    code: str
    message: str
    field: str | None


class PreviewRow(BaseModel):
    """A row as the commit would treat it."""

    row_no: int
    cells: dict[str, Any]
    values: dict[str, Any]
    action: str = Field(description="create, update, merge or skip.")
    reason: str | None
    errors: list[RowErrorOut]
    match_id: str | None


class PreviewOut(BaseModel):
    """The first rows of an import and the action counts over the whole file."""

    duplicate_strategy: str
    counts: dict[str, int]
    rows: list[PreviewRow]


class ReportRow(BaseModel):
    """A row's check and, after a commit or undo, what happened to it."""

    row_no: int
    action: str
    reason: str | None
    errors: list[RowErrorOut]
    match_id: str | None
    target_id: str | None
    outcome: str | None
    undo: str | None


class ExportFilters(StrictModel):
    """List filters; each entity accepts the ones its list route accepts."""

    status: FilterText | None = None
    equipment: FilterText | None = None
    tag: FilterText | None = None
    q: FilterText | None = None
    carrier_id: FilterText | None = None
    kind: FilterText | None = None
    state: FilterText | None = None
    city: FilterText | None = None


class ExportIn(StrictModel):
    """An export request."""

    entity: ExportEntity
    format: ExportFormat
    filters: ExportFilters = Field(default_factory=ExportFilters)


class ExportOut(BaseModel):
    """An export job and, when ready, where to download it."""

    id: str
    entity: str
    format: str
    filters: dict[str, str]
    status: str = Field(description="queued, running, ready or failed.")
    rows: int | None
    filename: str | None
    size_bytes: int | None
    error: str | None
    download_url: str | None = Field(description="Ready exports only; requires the same bearer token.")
    created_at: datetime
    ready_at: datetime | None
    expires_at: datetime


def _id(value: Any) -> str | None:
    """Render an optional id.

    Args:
        value: Stored id.

    Returns:
        Its text, or None.
    """
    return None if value is None else str(value)


def render_import(doc: Mapping[str, Any]) -> ImportOut:
    """Render an import document.

    Args:
        doc: Stored import.

    Returns:
        The model.
    """
    stored = as_map(doc.get("stats"))
    stats = {key: int(stored.get(key, 0)) for key in CHECK_STAT_KEYS + OUTCOME_STAT_KEYS}
    progress, undo = as_map(doc.get("progress")), as_map(doc.get("undo"))
    return ImportOut(id=str(doc["_id"]), entity=doc["entity"], source_filename=doc["source_filename"],
                     file_type=doc["file_type"], status=doc["status"], columns=list(doc["columns"]),
                     header_row=doc.get("header_row"), mapping=mapping_of(doc),
                     suggested_mapping=mapping_of(doc, "suggested_mapping"),
                     unmapped_required=list(doc.get("unmapped_required") or []),
                     ignored_consent_columns=list(doc.get("ignored_consent_columns") or []),
                     stats=ImportStats(**stats), duplicate_strategy=doc.get("duplicate_strategy"),
                     progress=ImportProgress(**progress) if progress else None,
                     undo=UndoCounts(**undo) if undo else None, undo_until=doc.get("undo_until"),
                     created_at=doc["created_at"], committed_at=doc.get("committed_at"), error=doc.get("error"))


def _errors(row: Doc) -> list[RowErrorOut]:
    """Render a row's errors.

    Args:
        row: Import row.

    Returns:
        The errors.
    """
    items = [as_map(item) for item in as_list(row.get("errors"))]
    return [RowErrorOut(code=str(item.get("code")), message=str(item.get("message")), field=item.get("field"))
            for item in items]


def render_preview_row(row: Doc, columns: list[str], strategy: str, allow_sensitive: bool) -> PreviewRow:
    """Render a row for the preview.

    Args:
        row: Import row.
        columns: Column names.
        strategy: Duplicate strategy.
        allow_sensitive: Whether carrier terms may be written directly.

    Returns:
        The model.
    """
    action, reason = preview_action(row, strategy, allow_sensitive)
    cells = dict(zip(columns, row.get("cells") or [None] * len(columns), strict=False))
    return PreviewRow(row_no=int(row["row_no"]), cells=cells, values=dict(row.get("values") or {}), action=action,
                      reason=reason, errors=_errors(row), match_id=_id(row.get("match_id")))


def render_report_row(row: Doc, strategy: str, allow_sensitive: bool) -> ReportRow:
    """Render a row for the report (the commit outcome wins over the preview action once it exists).

    Args:
        row: Import row.
        strategy: Duplicate strategy.
        allow_sensitive: Whether carrier terms may be written directly.

    Returns:
        The model.
    """
    action, reason = preview_action(row, strategy, allow_sensitive)
    outcome = as_map(row.get("outcome"))
    return ReportRow(row_no=int(row["row_no"]), action=action, reason=outcome.get("reason") if outcome else reason,
                     errors=_errors(row), match_id=_id(row.get("match_id")), target_id=_id(outcome.get("target_id")),
                     outcome=outcome.get("action"), undo=row.get("undo"))


def render_export(doc: Mapping[str, Any], download_url: str | None) -> ExportOut:
    """Render an export document.

    Args:
        doc: Stored export.
        download_url: Where to download it, or None.

    Returns:
        The model.
    """
    return ExportOut(id=str(doc["_id"]), entity=doc["entity"], format=doc["format"],
                     filters={str(key): str(value) for key, value in as_map(doc.get("filters")).items()},
                     status=doc["status"], rows=doc.get("rows"), filename=doc.get("filename"),
                     size_bytes=doc.get("size_bytes"), error=doc.get("error"), download_url=download_url,
                     created_at=doc["created_at"], ready_at=doc.get("ready_at"), expires_at=doc["expires_at"])
