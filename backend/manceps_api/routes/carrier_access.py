"""Carrier consent (ledger first, then cache) and scoped carrier links (`mcl_` tokens for the carrier portal)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Path, Request, Response
from pydantic import BaseModel, Field

from manceps_core.repo import carriers, consent
from manceps_core.repo.errors import Conflict
from manceps_core.tenancy import PlatformRepo

from .. import auditing
from ..auth.models import StrictModel
from ..auth.principal import FirmDispatcher, FirmIdempotency
from ..auth.scoped import DEFAULT_LINK_DAYS, SCOPED_LINKS, issue_link
from ..context import firm_db, get_context
from ..errors import ApiError
from .carriers import Carrier, render_carrier
from .common import ID_MAX, RecordId, can_set_terms

router = APIRouter(prefix="/v1", tags=["carriers"])

MAX_LINK_DAYS = 90
PORTAL_LINK_PATH = "/portal"
SCOPED_LINK_REF = "scoped_link"

ConsentChannel = Literal["sms", "voice", "whatsapp"]


class ConsentGrant(StrictModel):
    """Record that the carrier agreed to be contacted on a channel, and how (required)."""

    channel: ConsentChannel
    method: str = Field(max_length=consent.METHOD_MAX,
                        description="How consent was given, with date, e.g. 'signed dispatch agreement 2026-10-24'.")
    evidence_ref: str | None = Field(default=None, max_length=consent.EVIDENCE_MAX,
                                     description="Reference to stored evidence, e.g. a document id.")


class LinkCreate(StrictModel):
    """Options for a new carrier link."""

    ttl_days: int = Field(default=DEFAULT_LINK_DAYS, ge=1, le=MAX_LINK_DAYS)


class LinkCreated(BaseModel):
    """A new carrier link; `token` is shown once (null on an idempotent replay, where it is not stored)."""

    id: str
    carrier_id: str
    token: str | None
    url: str | None
    created_at: datetime
    expires_at: datetime


@router.post("/carriers/{carrier_id}/consent", operation_id="carrier_consent_grant", summary="Record consent")
def carrier_consent_grant(carrier_id: RecordId, body: ConsentGrant, request: Request,
                          principal: FirmDispatcher) -> Carrier:
    """Append a grant to the consent ledger, then refresh the carrier's consent cache from the ledger.

    Granting consent is a terms change: only the owner records it directly; a dispatcher gets 409
    approval_required (details.approval_kind = carrier_terms_change). Revoking is never gated.

    Args:
        carrier_id: Carrier id.
        body: Channel, method and optional evidence.
        request: Incoming request.
        principal: Dispatcher or owner.

    Returns:
        The carrier with its refreshed consent.

    Raises:
        RepoError: 404 unknown carrier, 409 approval_required for a dispatcher, 422 blank method.
    """
    if not can_set_terms(principal):
        raise Conflict("approval_required", "recording a carrier's consent needs the owner's approval",
                       {"approval_kind": carriers.APPROVAL_KIND, "fields": ["consent"]})
    doc = consent.record_consent(firm_db(request, principal), auditing.write_context(request, principal), "carrier",
                                 carrier_id, body.channel, consent.GRANTED, body.method, body.evidence_ref)
    return render_carrier(doc)


@router.delete("/carriers/{carrier_id}/consent/{channel}", operation_id="carrier_consent_revoke",
               summary="Revoke consent")
def carrier_consent_revoke(carrier_id: RecordId, channel: Annotated[ConsentChannel, Path()], request: Request,
                           principal: FirmDispatcher) -> Carrier:
    """Append a revoke to the consent ledger, then refresh the carrier's consent cache (immediate for any
    dispatcher or owner: a STOP never waits for an approval).

    Args:
        carrier_id: Carrier id.
        channel: Channel to revoke.
        request: Incoming request.
        principal: Dispatcher or owner.

    Returns:
        The carrier with its refreshed consent.

    Raises:
        RepoError: 404 unknown carrier.
    """
    doc = consent.record_consent(firm_db(request, principal), auditing.write_context(request, principal), "carrier",
                                 carrier_id, channel, consent.REVOKED, None)
    return render_carrier(doc)


@router.post("/carriers/{carrier_id}/links", status_code=201, operation_id="carrier_links_create",
             summary="Create a carrier portal link")
def carrier_links_create(carrier_id: RecordId, request: Request, principal: FirmDispatcher,
                         guard: FirmIdempotency, body: Annotated[LinkCreate | None, Body()] = None) -> LinkCreated:
    """Create a scoped link for the carrier portal; the token is returned once and stored only as a hash.

    Args:
        carrier_id: Carrier id.
        request: Incoming request.
        principal: Dispatcher or owner.
        guard: Idempotency guard (Idempotency-Key header optional).
        body: Optional lifetime (default 30 days, at most 90).

    Returns:
        The link with its token and portal URL.

    Raises:
        RepoError: 404 unknown carrier.
    """
    context = get_context(request)
    carrier = carriers.get_carrier(firm_db(request, principal), carrier_id)
    ttl = timedelta(days=(body or LinkCreate()).ttl_days)
    link, raw = issue_link(PlatformRepo.for_principal(context.platform_db, principal), "carrier",
                           str(carrier["_id"]), {"kind": principal.kind, "id": principal.user_id}, context.clock(), ttl)
    auditing.record(request, principal, "carrier.link_create", {"type": SCOPED_LINK_REF, "id": link["_id"]}, None,
                    {"carrier_id": str(carrier["_id"]), "expires_at": link["expires_at"]})
    base = context.settings.public_base_url
    created = LinkCreated(id=str(link["_id"]), carrier_id=str(carrier["_id"]), token=raw,
                          url=f"{base.rstrip('/')}{PORTAL_LINK_PATH}?token={raw}" if base else None,
                          created_at=link["created_at"], expires_at=link["expires_at"])
    guard.save(201, created.model_copy(update={"token": None, "url": None}).model_dump(mode="json"))
    return created


@router.delete("/carriers/{carrier_id}/links/{link_id}", status_code=204, operation_id="carrier_links_delete",
               summary="Revoke a carrier portal link")
def carrier_links_delete(carrier_id: RecordId, link_id: Annotated[str, Path(min_length=1, max_length=ID_MAX)],
                         request: Request, principal: FirmDispatcher) -> Response:
    """Revoke a carrier's link; portal tokens issued from it stop working on their next request.

    Args:
        carrier_id: Carrier id.
        link_id: Link id.
        request: Incoming request.
        principal: Dispatcher or owner.

    Returns:
        204.

    Raises:
        RepoError: 404 unknown carrier.
        ApiError: 404 when the link is not a live link of this carrier.
    """
    context = get_context(request)
    carrier = carriers.get_carrier(firm_db(request, principal), carrier_id)
    query = {"_id": link_id, "subject.type": "carrier", "subject.id": str(carrier["_id"]), "revoked_at": None}
    matched = PlatformRepo.for_principal(context.platform_db, principal).update_one(
        SCOPED_LINKS, query, {"$set": {"revoked_at": context.clock()}})
    if matched == 0:
        raise ApiError(404, "not_found", "link not found")
    auditing.record(request, principal, "carrier.link_revoke", {"type": SCOPED_LINK_REF, "id": link_id},
                    {"revoked_at": None}, {"revoked_at": context.clock()})
    return Response(status_code=204)
