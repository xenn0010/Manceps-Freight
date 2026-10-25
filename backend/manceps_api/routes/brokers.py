"""Brokers (firm memory keyed by MC), notes, vetting checks, and FMCSA reference search."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Any, cast

from fastapi import APIRouter, Body, Path, Query, Request
from pydantic import BaseModel
from pymongo.errors import PyMongoError

from manceps_core.brokers.check import run_check
from manceps_core.brokers.reference import legal_name_for_mc, search_brokers
from manceps_core.mongo import Doc, MongoDb
from manceps_core.repo import brokers, fields

from ..auditing import write_context
from ..auth.models import StrictModel
from ..auth.principal import FirmDispatcher, FirmIdempotency, FirmViewer
from ..context import firm_db, get_context
from ..errors import ApiError
from ..pagination import DEFAULT_LIMIT, CursorQuery, LimitQuery, Page, decode_cursor, page_of
from ..ratelimit import enforce
from .common import Email, LongText, Name, Number, Tags, list_of, text_of

router = APIRouter(prefix="/v1", tags=["brokers"])

CHECKS_PER_FIRM = 60
RATE_WINDOW = timedelta(hours=1)
MC_PATTERN = r"^(?:[Mm][Cc][- ]?)?[0-9]{1,10}$"
CODE_QUERY_MAX = 32

McPath = Annotated[str, Path(pattern=MC_PATTERN, description="MC number, digits or MC-123456.")]


class BrokerFields(StrictModel):
    """Writable broker fields."""

    company: Name | None = None
    dot_number: Number | None = None
    tags: Tags | None = None
    payment_terms: Name | None = None
    credit_notes: LongText | None = None


class BrokerCreate(BrokerFields):
    """A broker to remember; the company defaults to the FMCSA legal name when known."""

    mc_number: Number


class BrokerNote(BaseModel):
    """A note about a broker."""

    at: datetime
    text: str
    by: dict[str, Any] | None
    session_id: str | None


class NoteCreate(StrictModel):
    """A new broker note."""

    text: LongText


class LastCheck(BaseModel):
    """The latest vetting verdict."""

    verdict: str
    checked_at: datetime


class Broker(BaseModel):
    """A broker the firm works with, with notes (newest first, at most 20) and the last check."""

    id: str
    mc_number: str
    dot_number: str | None
    company: str | None
    tags: list[str]
    payment_terms: str | None
    credit_notes: str | None
    notes: list[BrokerNote]
    last_check: LastCheck | None
    created_at: datetime | None
    updated_at: datetime | None


class CheckRequest(StrictModel):
    """Optional extra inputs for a vetting check."""

    email: Email | None = None
    dot_number: Number | None = None


class BrokerCheck(BaseModel):
    """A stored vetting result; failures are `unknown`, never `pass`."""

    id: str
    mc_number: str | None
    dot_number: str | None
    verdict: str
    checks: list[dict[str, Any]]
    checked_at: datetime


class ReferenceBroker(BaseModel):
    """A public FMCSA broker record."""

    dot_number: str | None
    mc_numbers: list[str]
    legal_name: str | None
    dba_name: str | None
    city: str | None
    state: str | None


class ReferenceSearch(BaseModel):
    """Reference search results; a listed phone number is not consent to contact."""

    items: list[ReferenceBroker]
    count: int
    source: str
    note: str


def _note(raw: Any) -> BrokerNote | None:
    """Render one stored note, skipping malformed entries.

    Args:
        raw: Stored note.

    Returns:
        The note, or None.
    """
    if not isinstance(raw, dict):
        return None
    note = cast(dict[str, Any], raw)
    at, by = note.get("at"), note.get("by")
    if not isinstance(at, datetime):
        return None
    author = cast(dict[str, Any], by) if isinstance(by, dict) else None
    return BrokerNote(at=at, text=str(note.get("text", "")), by=author, session_id=text_of(note, "session_id"))


def render_broker(doc: Doc, last: Doc | None) -> Broker:
    """Render a broker.

    Args:
        doc: Broker document.
        last: Latest check document, or None.

    Returns:
        The model.
    """
    notes = [note for note in (_note(raw) for raw in reversed(list_of(doc, "notes"))) if note is not None]
    last_check = LastCheck(verdict=str(last["verdict"]), checked_at=last["checked_at"]) if last else None
    return Broker(id=str(doc["_id"]), mc_number=str(doc["mc_number"]), dot_number=text_of(doc, "dot_number"),
                  company=text_of(doc, "company"), tags=[str(tag) for tag in list_of(doc, "tags")],
                  payment_terms=text_of(doc, "payment_terms"), credit_notes=text_of(doc, "credit_notes"),
                  notes=notes[:brokers.MAX_NOTES_RETURNED], last_check=last_check, created_at=doc.get("created_at"),
                  updated_at=doc.get("updated_at"))


def _reference_broker(item: dict[str, Any]) -> ReferenceBroker:
    """Render a reference record, tolerating missing fields.

    Args:
        item: Summary from search_brokers.

    Returns:
        The model.
    """
    return ReferenceBroker(dot_number=text_of(item, "dot_number"),
                           mc_numbers=[str(mc) for mc in list_of(item, "mc_numbers")],
                           legal_name=text_of(item, "legal_name"), dba_name=text_of(item, "dba_name"),
                           city=text_of(item, "city"), state=text_of(item, "state"))


def render_check(doc: Doc) -> BrokerCheck:
    """Render a stored check.

    Args:
        doc: broker_checks document.

    Returns:
        The model.
    """
    return BrokerCheck(id=str(doc["_id"]), mc_number=text_of(doc, "mc_number"), dot_number=text_of(doc, "dot_number"),
                       verdict=str(doc["verdict"]), checks=list_of(doc, "checks"), checked_at=doc["checked_at"])


def _with_last(db: MongoDb, doc: Doc) -> Broker:
    """Render a broker with its latest check.

    Args:
        db: Firm database.
        doc: Broker document.

    Returns:
        The model.
    """
    return render_broker(doc, brokers.latest_check(db, str(doc["mc_number"])))


@router.get("/brokers", operation_id="brokers_list", summary="List brokers")
def brokers_list(request: Request, principal: FirmViewer,
                 q: Annotated[str | None, Query(max_length=fields.QUERY_MAX)] = None,
                 tag: Annotated[str | None, Query(max_length=CODE_QUERY_MAX)] = None,
                 limit: LimitQuery = DEFAULT_LIMIT, cursor: CursorQuery = None) -> Page[Broker]:
    """List the firm's brokers, oldest first (notes and last check included).

    Args:
        request: Incoming request.
        principal: Firm member.
        q: Company contains, or exact MC digits.
        tag: Only brokers with this tag.
        limit: Page size.
        cursor: Cursor from the previous page.

    Returns:
        One page.

    Raises:
        ApiError: 400 invalid_cursor.
    """
    db = firm_db(request, principal)
    docs = brokers.list_brokers(db, {"q": q, "tag": tag}, decode_cursor(cursor), limit)
    return page_of(docs, limit, lambda doc: _with_last(db, doc))


@router.post("/brokers", status_code=201, operation_id="brokers_create", summary="Add a broker")
def brokers_create(body: BrokerCreate, request: Request, principal: FirmDispatcher,
                   guard: FirmIdempotency) -> Broker:
    """Add a broker by MC (audited); the company name is pulled from the FMCSA reference when not given.

    Args:
        body: Broker fields.
        request: Incoming request.
        principal: Dispatcher or owner.
        guard: Idempotency guard.

    Returns:
        The broker.

    Raises:
        RepoError: 409 duplicate_mc, 422.
    """
    values = body.model_dump(exclude_unset=True)
    if values.get("company") is None:
        values["company"] = legal_name_for_mc(get_context(request).reference_db(),
                                              brokers.normalize_mc(body.mc_number))
    doc = brokers.create_broker(firm_db(request, principal), write_context(request, principal), values)
    broker = render_broker(doc, None)
    guard.save(201, broker.model_dump(mode="json"))
    return broker


@router.get("/brokers/{mc}", operation_id="brokers_get", summary="Get a broker")
def brokers_get(mc: McPath, request: Request, principal: FirmViewer) -> Broker:
    """Return what the firm knows about a broker.

    Args:
        mc: MC number.
        request: Incoming request.
        principal: Firm member.

    Returns:
        The broker.

    Raises:
        RepoError: 404.
    """
    db = firm_db(request, principal)
    return _with_last(db, brokers.get_broker(db, mc))


@router.patch("/brokers/{mc}", operation_id="brokers_update", summary="Update a broker")
def brokers_update(mc: McPath, body: BrokerFields, request: Request, principal: FirmDispatcher) -> Broker:
    """Change a broker's company, tags, payment terms or credit notes (audited).

    Args:
        mc: MC number.
        body: Changes (null removes an optional field).
        request: Incoming request.
        principal: Dispatcher or owner.

    Returns:
        The broker.

    Raises:
        RepoError: 404, 422.
    """
    db = firm_db(request, principal)
    doc = brokers.update_broker(db, write_context(request, principal), mc, body.model_dump(exclude_unset=True))
    return _with_last(db, doc)


@router.post("/brokers/{mc}/notes", status_code=201, operation_id="broker_notes_create", summary="Add a broker note")
def broker_notes_create(mc: McPath, body: NoteCreate, request: Request, principal: FirmDispatcher) -> BrokerNote:
    """Append a note to a broker (audited).

    Args:
        mc: MC number.
        body: Note text.
        request: Incoming request.
        principal: Dispatcher or owner.

    Returns:
        The note.

    Raises:
        RepoError: 404, 422 on a blank note.
    """
    note = brokers.add_note(firm_db(request, principal), write_context(request, principal), mc, body.text)
    return BrokerNote(at=note["at"], text=str(note["text"]), by=note["by"], session_id=note["session_id"])


@router.post("/brokers/{mc}/check", operation_id="broker_checks_create", summary="Vet a broker")
def broker_checks_create(mc: McPath, request: Request, principal: FirmDispatcher,
                         body: Annotated[CheckRequest | None, Body()] = None) -> BrokerCheck:
    """Run the broker vetting checks (FMCSA status and authority, bond, email domain) and store the result.

    Lookup failures are `unknown` and the verdict is then `review` or `do_not_book`, never `looks_ok`.

    Args:
        mc: MC number of a broker of this firm.
        request: Incoming request.
        principal: Dispatcher or owner.
        body: Optional contact email and DOT number.

    Returns:
        The stored check.

    Raises:
        RepoError: 404 unknown broker.
        ApiError: 503 integration_not_configured without FMCSA_WEBKEY; 429 over the firm's hourly limit.
    """
    context, db = get_context(request), firm_db(request, principal)
    broker = brokers.get_broker(db, mc)
    lookup = context.integrations.broker_lookup
    if lookup is None:
        raise ApiError(503, "integration_not_configured", "broker vetting is not configured (FMCSA_WEBKEY)")
    enforce(context.platform_db, "broker_check_firm", str(principal.tenant_id), CHECKS_PER_FIRM, RATE_WINDOW,
            context.clock())
    request_body = body or CheckRequest()
    dot = request_body.dot_number or str(broker.get("dot_number") or "")
    result = run_check(lookup.transport, lookup.fmcsa_key, str(broker["mc_number"]), dot, request_body.email or "",
                       context.reference_db(), context.clock())
    return render_check(brokers.record_check(db, write_context(request, principal), broker, result))


@router.get("/brokers/{mc}/checks", operation_id="broker_checks_list", summary="Broker check history")
def broker_checks_list(mc: McPath, request: Request, principal: FirmViewer, limit: LimitQuery = DEFAULT_LIMIT,
                       cursor: CursorQuery = None) -> Page[BrokerCheck]:
    """List a broker's vetting results, newest first.

    Args:
        mc: MC number.
        request: Incoming request.
        principal: Firm member.
        limit: Page size.
        cursor: Cursor from the previous page.

    Returns:
        One page.

    Raises:
        RepoError: 404 unknown broker.
        ApiError: 400 invalid_cursor.
    """
    docs = brokers.list_checks(firm_db(request, principal), mc, decode_cursor(cursor), limit)
    return page_of(docs, limit, render_check)


@router.get("/reference/brokers", operation_id="reference_brokers_list", summary="Search FMCSA brokers")
def reference_brokers_list(request: Request, principal: FirmViewer,
                           mc: Annotated[str | None, Query(max_length=CODE_QUERY_MAX)] = None,
                           dot: Annotated[str | None, Query(max_length=CODE_QUERY_MAX)] = None,
                           q: Annotated[str | None, Query(max_length=fields.QUERY_MAX)] = None,
                           state: Annotated[str | None, Query(max_length=CODE_QUERY_MAX)] = None) -> ReferenceSearch:
    """Search public FMCSA broker records by MC, DOT, or name (at least 3 characters, optional state).

    Args:
        request: Incoming request.
        principal: Firm member.
        mc: MC number.
        dot: DOT number.
        q: Legal or DBA name contains.
        state: Two-letter state (with q).

    Returns:
        Up to 10 matches.

    Raises:
        RepoError: 422 without a usable query.
        ApiError: 503 reference_unavailable when the reference database cannot be read.
    """
    del principal
    try:
        result = search_brokers(get_context(request).reference_db(), mc, dot, q, state)
    except PyMongoError as exc:
        raise ApiError(503, "reference_unavailable", "FMCSA reference data is unavailable") from exc
    items = [_reference_broker(item) for item in result["items"]]
    return ReferenceSearch(items=items, count=len(items), source=str(result["source"]), note=str(result["note"]))
