"""Carriers: list, create, read, update (terms need approval unless owner) and offboard (soft delete)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request, Response
from pydantic import AwareDatetime, BaseModel, Field

from manceps_core.mongo import Doc
from manceps_core.repo import carriers, fields

from ..auditing import write_context
from ..auth.models import StrictModel
from ..auth.principal import FirmDispatcher, FirmIdempotency, FirmOwner, FirmViewer
from ..context import firm_db
from ..pagination import DEFAULT_LIMIT, CursorQuery, LimitQuery, Page, decode_cursor, page_of
from .common import (
    ConsentState,
    Email,
    LongText,
    Name,
    Number,
    Phone,
    RecordId,
    Tags,
    can_set_terms,
    consent_state,
    list_of,
    text_of,
)

router = APIRouter(prefix="/v1", tags=["carriers"])

CONSENT_METHOD_MAX = 300
EQUIPMENT_MAX = 32

CarrierStatus = Literal["onboarding", "active", "paused", "offboarded"]
Equipment = Annotated[str, Field(max_length=EQUIPMENT_MAX)]


class Lane(StrictModel):
    """A lane the carrier likes to run."""

    origin: Name | None = None
    destination: Name | None = None


class ConsentInput(StrictModel):
    """Consent as the plugin shapes it; accepted only to explain that consent goes through the ledger."""

    sms: bool | None = None
    voice: bool | None = None
    whatsapp: bool | None = None
    method: str | None = Field(default=None, max_length=CONSENT_METHOD_MAX)


class CarrierFields(StrictModel):
    """Writable carrier fields. Fee, floor and agreement need the owner (or an approval)."""

    name: Name | None = None
    company: Name | None = None
    mc_number: Number | None = None
    dot_number: Number | None = None
    email: Email | None = None
    equipment: Annotated[list[Equipment], Field(max_length=fields.MAX_LIST_ITEMS)] | None = None
    home_base: Name | None = None
    preferred_lanes: Annotated[list[Lane], Field(max_length=fields.MAX_LIST_ITEMS)] | None = None
    avoid: Annotated[list[Name], Field(max_length=fields.MAX_LIST_ITEMS)] | None = None
    notes: LongText | None = None
    status: CarrierStatus | None = None
    tags: Tags | None = None
    insurance_expires_at: AwareDatetime | None = None
    dispatch_fee_pct: float | None = Field(default=None, description="Percent of gross; owner only, max 25.")
    rate_floor_per_mile: float | None = Field(default=None, description="Lowest all-in $/mile; owner only.")
    agreement_signed: bool | None = Field(default=None, description="Owner only.")


class CarrierCreate(CarrierFields):
    """A new carrier; the phone (any US format) is its unique key."""

    phone: Phone


class CarrierPatch(CarrierFields):
    """Carrier changes; null removes an optional field. Consent is refused here (use the consent routes)."""

    phone: Phone | None = None
    consent: ConsentInput | None = None


class Carrier(BaseModel):
    """A carrier on the firm's roster."""

    id: str
    phone: str | None
    name: str | None
    company: str | None
    mc_number: str | None
    dot_number: str | None
    email: str | None
    equipment: list[str]
    home_base: str | None
    preferred_lanes: list[dict[str, Any]]
    avoid: list[str]
    notes: str | None
    status: str
    tags: list[str]
    insurance_expires_at: datetime | None
    dispatch_fee_pct: float | None
    rate_floor_per_mile: float | None
    agreement_signed: bool | None
    consent: ConsentState | None
    created_at: datetime | None
    updated_at: datetime | None


def _number(doc: Doc, key: str) -> float | None:
    """Read an optional numeric field.

    Args:
        doc: Document.
        key: Field name.

    Returns:
        The number as a float, or None.
    """
    value = doc.get(key)
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def render_carrier(doc: Doc) -> Carrier:
    """Render a carrier, including records the plugin wrote (no status, fewer fields).

    Args:
        doc: Carrier document.

    Returns:
        The model.
    """
    agreement = doc.get("agreement_signed")
    return Carrier(id=str(doc["_id"]), phone=text_of(doc, "phone"), name=text_of(doc, "name"),
                   company=text_of(doc, "company"), mc_number=text_of(doc, "mc_number"),
                   dot_number=text_of(doc, "dot_number"), email=text_of(doc, "email"),
                   home_base=text_of(doc, "home_base"), notes=text_of(doc, "notes"),
                   dispatch_fee_pct=_number(doc, "dispatch_fee_pct"),
                   rate_floor_per_mile=_number(doc, "rate_floor_per_mile"),
                   equipment=[str(item) for item in list_of(doc, "equipment")],
                   preferred_lanes=[lane for lane in list_of(doc, "preferred_lanes") if isinstance(lane, dict)],
                   avoid=[str(item) for item in list_of(doc, "avoid")], tags=[str(t) for t in list_of(doc, "tags")],
                   status=str(doc.get("status") or carriers.DEFAULT_STATUS),
                   insurance_expires_at=doc.get("insurance_expires_at"),
                   agreement_signed=agreement if isinstance(agreement, bool) else None,
                   consent=consent_state(doc.get("consent")), created_at=doc.get("created_at"),
                   updated_at=doc.get("updated_at"))


@router.get("/carriers", operation_id="carriers_list", summary="List carriers")
def carriers_list(request: Request, principal: FirmViewer, status: CarrierStatus | None = None,
                  equipment: Annotated[str | None, Query(max_length=EQUIPMENT_MAX)] = None,
                  tag: Annotated[str | None, Query(max_length=EQUIPMENT_MAX)] = None,
                  q: Annotated[str | None, Query(max_length=fields.QUERY_MAX)] = None,
                  limit: LimitQuery = DEFAULT_LIMIT, cursor: CursorQuery = None) -> Page[Carrier]:
    """List the firm's live carriers, oldest first.

    Args:
        request: Incoming request.
        principal: Firm member.
        status: Only this status.
        equipment: Only carriers with this equipment.
        tag: Only carriers with this tag.
        q: Name or company contains.
        limit: Page size.
        cursor: Cursor from the previous page.

    Returns:
        One page.

    Raises:
        ApiError: 400 invalid_cursor.
    """
    filters = {"status": status, "equipment": equipment, "tag": tag, "q": q}
    docs = carriers.list_carriers(firm_db(request, principal), filters, decode_cursor(cursor), limit)
    return page_of(docs, limit, render_carrier)


@router.post("/carriers", status_code=201, operation_id="carriers_create", summary="Add a carrier")
def carriers_create(body: CarrierCreate, request: Request, principal: FirmDispatcher,
                    guard: FirmIdempotency) -> Carrier:
    """Add a carrier (audited). A dispatcher sending fee, floor or agreement gets 409 approval_required.

    Args:
        body: Carrier fields.
        request: Incoming request.
        principal: Dispatcher or owner.
        guard: Idempotency guard (Idempotency-Key header optional).

    Returns:
        The carrier.

    Raises:
        RepoError: 409 duplicate_phone or approval_required, 422 on invalid values.
    """
    doc = carriers.create_carrier(firm_db(request, principal), write_context(request, principal),
                                  body.model_dump(exclude_unset=True), can_set_terms(principal))
    carrier = render_carrier(doc)
    guard.save(201, carrier.model_dump(mode="json"))
    return carrier


@router.get("/carriers/{carrier_id}", operation_id="carriers_get", summary="Get a carrier")
def carriers_get(carrier_id: RecordId, request: Request, principal: FirmViewer) -> Carrier:
    """Return one live carrier with its consent summary.

    Args:
        carrier_id: Carrier id.
        request: Incoming request.
        principal: Firm member.

    Returns:
        The carrier.

    Raises:
        RepoError: 404 when it is not a live carrier of this firm.
    """
    return render_carrier(carriers.get_carrier(firm_db(request, principal), carrier_id))


@router.patch("/carriers/{carrier_id}", operation_id="carriers_update", summary="Update a carrier")
def carriers_update(carrier_id: RecordId, body: CarrierPatch, request: Request, principal: FirmDispatcher) -> Carrier:
    """Change a carrier (audited with before and after hashes).

    Fee, floor, agreement and consent are sensitive: a dispatcher gets 409 approval_required
    (details.approval_kind = carrier_terms_change); the owner writes fee, floor and agreement directly; consent
    always goes through POST /v1/carriers/{id}/consent (422 use_consent_endpoint).

    Args:
        carrier_id: Carrier id.
        body: Changes.
        request: Incoming request.
        principal: Dispatcher or owner.

    Returns:
        The updated carrier.

    Raises:
        RepoError: 404, 409 approval_required or duplicate_phone, 422.
    """
    doc = carriers.update_carrier(firm_db(request, principal), write_context(request, principal), carrier_id,
                                  body.model_dump(exclude_unset=True), can_set_terms(principal))
    return render_carrier(doc)


@router.delete("/carriers/{carrier_id}", status_code=204, operation_id="carriers_delete", summary="Offboard a carrier")
def carriers_delete(carrier_id: RecordId, request: Request, principal: FirmOwner) -> Response:
    """Offboard (soft-delete) a carrier; its phone number can be added again later.

    Args:
        carrier_id: Carrier id.
        request: Incoming request.
        principal: Firm owner.

    Returns:
        204.

    Raises:
        RepoError: 404, or 409 carrier_has_open_loads.
    """
    carriers.delete_carrier(firm_db(request, principal), write_context(request, principal), carrier_id)
    return Response(status_code=204)
