"""Notes on any firm record, and the firm's tag vocabulary."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from manceps_core.mongo import Doc
from manceps_core.repo import notes

from ..auditing import write_context
from ..auth.models import StrictModel
from ..auth.principal import FirmDispatcher, FirmViewer
from ..context import firm_db
from ..pagination import DEFAULT_LIMIT, CursorQuery, LimitQuery, Page, decode_cursor, page_of
from .common import CODE_MAX, ID_MAX, LongText

router = APIRouter(prefix="/v1", tags=["notes"])

RefType = Annotated[str, Field(max_length=CODE_MAX, description="carrier, driver, truck, contact, facility or load.")]
RefId = Annotated[str, Field(max_length=ID_MAX)]


class NoteRef(StrictModel):
    """The record a note is about (broker notes use POST /v1/brokers/{mc}/notes)."""

    type: RefType
    id: RefId


class NoteCreate(StrictModel):
    """A new note."""

    ref: NoteRef
    text: LongText
    pinned: bool = False


class Note(BaseModel):
    """A note."""

    id: str
    ref: dict[str, str]
    text: str
    pinned: bool
    author: dict[str, Any]
    created_at: datetime


class TagCount(BaseModel):
    """How often a tag is used, overall and per record kind."""

    tag: str
    count: int
    by_entity: dict[str, int]


class TagList(BaseModel):
    """The firm's tag vocabulary, most used first."""

    items: list[TagCount]


def render_note(doc: Doc) -> Note:
    """Render a note.

    Args:
        doc: Note document.

    Returns:
        The model.
    """
    return Note(id=str(doc["_id"]), ref={"type": str(doc["ref"]["type"]), "id": str(doc["ref"]["id"])},
                text=str(doc["text"]), pinned=bool(doc.get("pinned")), author=dict(doc.get("author") or {}),
                created_at=doc["created_at"])


@router.get("/notes", operation_id="notes_list", summary="List notes of a record")
def notes_list(request: Request, principal: FirmViewer, ref_type: Annotated[str, Query(max_length=CODE_MAX)],
               ref_id: Annotated[str, Query(max_length=ID_MAX)], limit: LimitQuery = DEFAULT_LIMIT,
               cursor: CursorQuery = None) -> Page[Note]:
    """List the notes of one record of this firm, oldest first.

    Args:
        request: Incoming request.
        principal: Firm member.
        ref_type: Record kind.
        ref_id: Record id.
        limit: Page size.
        cursor: Cursor from the previous page.

    Returns:
        One page.

    Raises:
        RepoError: 404 unknown record, 422 unsupported kind.
        ApiError: 400 invalid_cursor.
    """
    docs = notes.list_notes(firm_db(request, principal), ref_type, ref_id, decode_cursor(cursor), limit)
    return page_of(docs, limit, render_note)


@router.post("/notes", status_code=201, operation_id="notes_create", summary="Add a note")
def notes_create(body: NoteCreate, request: Request, principal: FirmDispatcher) -> Note:
    """Attach a note to a record of this firm (audited; the caller is the author).

    Args:
        body: Subject, text and pin flag.
        request: Incoming request.
        principal: Dispatcher or owner.

    Returns:
        The note.

    Raises:
        RepoError: 404 unknown record, 422 blank text or unsupported kind.
    """
    doc = notes.create_note(firm_db(request, principal), write_context(request, principal), body.ref.type,
                            body.ref.id, body.text, body.pinned)
    return render_note(doc)


@router.get("/tags", operation_id="tags_list", summary="Tag vocabulary")
def tags_list(request: Request, principal: FirmViewer) -> TagList:
    """Count tag use across live carriers, brokers and contacts.

    Args:
        request: Incoming request.
        principal: Firm member.

    Returns:
        Tags with counts, most used first.
    """
    return TagList(items=[TagCount.model_validate(item) for item in notes.tag_counts(firm_db(request, principal))])
