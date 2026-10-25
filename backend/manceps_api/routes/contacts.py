"""Contacts (CRM) and facilities: list, create, read, update, delete (soft)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, Field

from manceps_core.mongo import Doc
from manceps_core.repo import contacts, fields

from ..auditing import write_context
from ..auth.models import StrictModel
from ..auth.principal import FirmDispatcher, FirmIdempotency, FirmViewer
from ..context import firm_db
from ..pagination import DEFAULT_LIMIT, CursorQuery, LimitQuery, Page, decode_cursor, page_of
from .common import (
    CODE_MAX,
    ID_MAX,
    PHONE_MAX,
    TAG_MAX,
    Code,
    Email,
    LongText,
    Name,
    Phone,
    RecordId,
    Tags,
    list_of,
    text_of,
)

router = APIRouter(prefix="/v1", tags=["contacts"])

ZIP_MAX = 10
GEO_POINT_LEN = 2

ContactKind = Literal["broker_contact", "shipper", "receiver", "facility", "other"]


class ContactFields(StrictModel):
    """Writable contact fields (consent is not writable here)."""

    company: Name | None = None
    title: Name | None = None
    phones: Annotated[list[Phone], Field(max_length=fields.MAX_CONTACT_POINTS)] | None = None
    emails: Annotated[list[Email], Field(max_length=fields.MAX_CONTACT_POINTS)] | None = None
    tags: Tags | None = None


class ContactCreate(ContactFields):
    """A new contact."""

    kind: ContactKind
    name: Name


class ContactPatch(ContactFields):
    """Contact changes; null removes an optional field."""

    kind: ContactKind | None = None
    name: Name | None = None


class Contact(BaseModel):
    """A contact."""

    id: str
    kind: str
    name: str
    company: str | None
    title: str | None
    phones: list[str]
    emails: list[str]
    tags: list[str]
    source: str
    consent: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class Location(StrictModel):
    """A point."""

    lat: float
    lng: float


class FacilityFields(StrictModel):
    """Writable facility fields."""

    address: Name | None = None
    city: Name | None = None
    state: Code | None = None
    zip: Annotated[str, Field(max_length=ZIP_MAX)] | None = None
    location: Location | None = None
    hours: Annotated[str, Field(max_length=contacts.HOURS_MAX)] | None = None
    detention_notes: LongText | None = None
    contact_ids: Annotated[list[Annotated[str, Field(max_length=ID_MAX)]],
                           Field(max_length=fields.MAX_LIST_ITEMS)] | None = None


class FacilityCreate(FacilityFields):
    """A new facility."""

    name: Name


class FacilityPatch(FacilityFields):
    """Facility changes; null removes an optional field."""

    name: Name | None = None


class Facility(BaseModel):
    """A shipper or receiver location."""

    id: str
    name: str
    address: str | None
    city: str | None
    state: str | None
    zip: str | None
    location: Location | None
    hours: str | None
    detention_notes: str | None
    contact_ids: list[str]
    created_at: datetime
    updated_at: datetime


def render_contact(doc: Doc) -> Contact:
    """Render a contact.

    Args:
        doc: Contact document.

    Returns:
        The model.
    """
    consent: Any = doc.get("consent")
    return Contact(id=str(doc["_id"]), kind=str(doc["kind"]), name=str(doc["name"]), company=text_of(doc, "company"),
                   title=text_of(doc, "title"), phones=[str(p) for p in list_of(doc, "phones")],
                   emails=[str(e) for e in list_of(doc, "emails")], tags=[str(t) for t in list_of(doc, "tags")],
                   source=str(doc.get("source") or contacts.DEFAULT_SOURCE),
                   consent=cast(dict[str, Any], consent) if isinstance(consent, dict) else None,
                   created_at=doc["created_at"], updated_at=doc["updated_at"])


def render_facility(doc: Doc) -> Facility:
    """Render a facility (GeoJSON `geo` becomes {lat, lng}).

    Args:
        doc: Facility document.

    Returns:
        The model.
    """
    coordinates = list_of(doc.get("geo") or {}, "coordinates")
    location = Location(lat=coordinates[1], lng=coordinates[0]) if len(coordinates) == GEO_POINT_LEN else None
    return Facility(id=str(doc["_id"]), name=str(doc["name"]), address=text_of(doc, "address"),
                    city=text_of(doc, "city"), state=text_of(doc, "state"), zip=text_of(doc, "zip"), location=location,
                    hours=text_of(doc, "hours"), detention_notes=text_of(doc, "detention_notes"),
                    contact_ids=[str(i) for i in list_of(doc, "contact_ids")], created_at=doc["created_at"],
                    updated_at=doc["updated_at"])


@router.get("/contacts", operation_id="contacts_list", summary="List contacts")
def contacts_list(request: Request, principal: FirmViewer, kind: ContactKind | None = None,
                  tag: Annotated[str | None, Query(max_length=TAG_MAX)] = None,
                  phone: Annotated[str | None, Query(max_length=PHONE_MAX)] = None,
                  q: Annotated[str | None, Query(max_length=fields.QUERY_MAX)] = None,
                  limit: LimitQuery = DEFAULT_LIMIT, cursor: CursorQuery = None) -> Page[Contact]:
    """List live contacts, oldest first.

    Args:
        request: Incoming request.
        principal: Firm member.
        kind: Only this kind.
        tag: Only contacts with this tag.
        phone: Only contacts with this phone (any US format).
        q: Name or company contains.
        limit: Page size.
        cursor: Cursor from the previous page.

    Returns:
        One page.

    Raises:
        ApiError: 400 invalid_cursor.
        RepoError: 422 on a malformed phone filter.
    """
    filters = {"kind": kind, "tag": tag, "phone": phone, "q": q}
    docs = contacts.list_contacts(firm_db(request, principal), filters, decode_cursor(cursor), limit)
    return page_of(docs, limit, render_contact)


@router.post("/contacts", status_code=201, operation_id="contacts_create", summary="Add a contact")
def contacts_create(body: ContactCreate, request: Request, principal: FirmDispatcher,
                    guard: FirmIdempotency) -> Contact:
    """Add a contact (audited); phones are normalized to E.164 and emails lowercased.

    Args:
        body: Contact fields.
        request: Incoming request.
        principal: Dispatcher or owner.
        guard: Idempotency guard.

    Returns:
        The contact.

    Raises:
        RepoError: 422.
    """
    doc = contacts.create_record(firm_db(request, principal), write_context(request, principal), "contact",
                                 body.model_dump(exclude_unset=True))
    contact = render_contact(doc)
    guard.save(201, contact.model_dump(mode="json"))
    return contact


@router.get("/contacts/{contact_id}", operation_id="contacts_get", summary="Get a contact")
def contacts_get(contact_id: RecordId, request: Request, principal: FirmViewer) -> Contact:
    """Return one live contact.

    Args:
        contact_id: Contact id.
        request: Incoming request.
        principal: Firm member.

    Returns:
        The contact.

    Raises:
        RepoError: 404.
    """
    return render_contact(contacts.get_record(firm_db(request, principal), "contact", contact_id))


@router.patch("/contacts/{contact_id}", operation_id="contacts_update", summary="Update a contact")
def contacts_update(contact_id: RecordId, body: ContactPatch, request: Request, principal: FirmDispatcher) -> Contact:
    """Change a contact (audited); null removes an optional field.

    Args:
        contact_id: Contact id.
        body: Changes.
        request: Incoming request.
        principal: Dispatcher or owner.

    Returns:
        The contact.

    Raises:
        RepoError: 404, 422.
    """
    doc = contacts.update_record(firm_db(request, principal), write_context(request, principal), "contact",
                                 contact_id, body.model_dump(exclude_unset=True))
    return render_contact(doc)


@router.delete("/contacts/{contact_id}", status_code=204, operation_id="contacts_delete", summary="Delete a contact")
def contacts_delete(contact_id: RecordId, request: Request, principal: FirmDispatcher) -> Response:
    """Soft-delete a contact.

    Args:
        contact_id: Contact id.
        request: Incoming request.
        principal: Dispatcher or owner.

    Returns:
        204.

    Raises:
        RepoError: 404.
    """
    contacts.delete_record(firm_db(request, principal), write_context(request, principal), "contact", contact_id)
    return Response(status_code=204)


@router.get("/facilities", operation_id="facilities_list", summary="List facilities")
def facilities_list(request: Request, principal: FirmViewer,
                    state: Annotated[str | None, Query(max_length=CODE_MAX)] = None,
                    city: Annotated[str | None, Query(max_length=fields.NAME_MAX)] = None,
                    q: Annotated[str | None, Query(max_length=fields.QUERY_MAX)] = None,
                    limit: LimitQuery = DEFAULT_LIMIT, cursor: CursorQuery = None) -> Page[Facility]:
    """List live facilities, oldest first.

    Args:
        request: Incoming request.
        principal: Firm member.
        state: Only this two-letter state.
        city: Only this city (any case).
        q: Name or address contains.
        limit: Page size.
        cursor: Cursor from the previous page.

    Returns:
        One page.

    Raises:
        ApiError: 400 invalid_cursor.
        RepoError: 422 on a malformed state.
    """
    docs = contacts.list_facilities(firm_db(request, principal), {"state": state, "city": city, "q": q},
                                    decode_cursor(cursor), limit)
    return page_of(docs, limit, render_facility)


@router.post("/facilities", status_code=201, operation_id="facilities_create", summary="Add a facility")
def facilities_create(body: FacilityCreate, request: Request, principal: FirmDispatcher,
                      guard: FirmIdempotency) -> Facility:
    """Add a facility (audited).

    Args:
        body: Facility fields.
        request: Incoming request.
        principal: Dispatcher or owner.
        guard: Idempotency guard.

    Returns:
        The facility.

    Raises:
        RepoError: 422 (including unknown contact ids).
    """
    doc = contacts.create_record(firm_db(request, principal), write_context(request, principal), "facility",
                                 body.model_dump(exclude_unset=True))
    facility = render_facility(doc)
    guard.save(201, facility.model_dump(mode="json"))
    return facility


@router.get("/facilities/{facility_id}", operation_id="facilities_get", summary="Get a facility")
def facilities_get(facility_id: RecordId, request: Request, principal: FirmViewer) -> Facility:
    """Return one live facility.

    Args:
        facility_id: Facility id.
        request: Incoming request.
        principal: Firm member.

    Returns:
        The facility.

    Raises:
        RepoError: 404.
    """
    return render_facility(contacts.get_record(firm_db(request, principal), "facility", facility_id))


@router.patch("/facilities/{facility_id}", operation_id="facilities_update", summary="Update a facility")
def facilities_update(facility_id: RecordId, body: FacilityPatch, request: Request,
                      principal: FirmDispatcher) -> Facility:
    """Change a facility (audited); null removes an optional field.

    Args:
        facility_id: Facility id.
        body: Changes.
        request: Incoming request.
        principal: Dispatcher or owner.

    Returns:
        The facility.

    Raises:
        RepoError: 404, 422.
    """
    doc = contacts.update_record(firm_db(request, principal), write_context(request, principal), "facility",
                                 facility_id, body.model_dump(exclude_unset=True))
    return render_facility(doc)


@router.delete("/facilities/{facility_id}", status_code=204, operation_id="facilities_delete",
               summary="Delete a facility")
def facilities_delete(facility_id: RecordId, request: Request, principal: FirmDispatcher) -> Response:
    """Soft-delete a facility.

    Args:
        facility_id: Facility id.
        request: Incoming request.
        principal: Dispatcher or owner.

    Returns:
        204.

    Raises:
        RepoError: 404.
    """
    contacts.delete_record(firm_db(request, principal), write_context(request, principal), "facility", facility_id)
    return Response(status_code=204)
