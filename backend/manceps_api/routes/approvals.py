"""Approvals: the "needs your yes" inbox. List, read, propose, decide (people only) and stats.

Booking a load (`accept_rate`) and signing a Rate Con (`approve_ratecon`) are always decided by the firm owner in
person; no setting or automated actor can approve them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from manceps_core.approvals import registry, service
from manceps_core.mongo import Doc

from ..auditing import write_context
from ..auth.models import StrictModel
from ..auth.principal import FirmDispatcher, FirmIdempotency, FirmViewer
from ..context import firm_db, get_context
from ..pagination import DEFAULT_LIMIT, CursorQuery, LimitQuery, Page, decode_cursor, page_of
from .common import ID_MAX, RecordId
from .load_models import Cents, Reason

router = APIRouter(prefix="/v1", tags=["approvals"])

HASH_LENGTH = 64
Kind = Literal["accept_rate", "approve_ratecon", "carrier_terms_change", "cancel_load"]
Status = Literal["pending", "approved", "denied", "expired", "applied", "apply_failed"]


class AcceptRatePayload(StrictModel):
    """accept_rate: book the load at this rate (owner decides). On a booked load it amends the rate."""

    rate_cents: Cents
    carrier_id: Annotated[str, Field(max_length=ID_MAX)] | None = None


class ApproveRateconPayload(StrictModel):
    """approve_ratecon: sign off the broker's Rate Con; its rate must equal the load's (owner decides)."""

    rate_cents: Cents
    document_ref: Annotated[str, Field(max_length=registry.DOCUMENT_REF_MAX)] | None = None


class TermsChanges(StrictModel):
    """Carrier terms to change."""

    dispatch_fee_pct: float | None = None
    rate_floor_per_mile: float | None = None
    agreement_signed: bool | None = None


class CarrierTermsPayload(StrictModel):
    """carrier_terms_change: fee, floor or agreement (owner decides; consent has its own ledger)."""

    changes: TermsChanges


class CancelLoadPayload(StrictModel):
    """cancel_load: cancel a load, including a booked one (dispatcher or owner decides)."""

    reason: Reason


Payload = AcceptRatePayload | ApproveRateconPayload | CarrierTermsPayload | CancelLoadPayload


class SubjectRef(StrictModel):
    """What the approval acts on."""

    type: Literal["load", "carrier"]
    id: Annotated[str, Field(max_length=ID_MAX)]


class ApprovalCreate(StrictModel):
    """A proposal for a person to decide."""

    model_config = {**StrictModel.model_config, "json_schema_extra": {"examples": [{
        "kind": "accept_rate", "subject_ref": {"type": "load", "id": "6718a0c2e4b0a1b2c3d4e5f6"},
        "payload": {"rate_cents": 224000}, "summary": "Commerce → SF, Tue 07:00, $2,240"}]}}

    kind: Kind
    subject_ref: SubjectRef
    payload: Payload
    summary: Annotated[str, Field(max_length=service.SUMMARY_MAX)] | None = None


class DecisionInput(StrictModel):
    """A person's decision; payload_hash must be the one shown with the approval."""

    decision: Literal["approve", "deny"]
    payload_hash: Annotated[str, Field(max_length=HASH_LENGTH)]
    note: Annotated[str, Field(max_length=service.NOTE_MAX)] | None = None


class Approval(BaseModel):
    """An approval with everything needed to show and decide it."""

    id: str
    kind: str
    status: str
    subject_ref: dict[str, Any]
    payload: dict[str, Any]
    payload_hash: str
    summary: str
    risk: str
    required_role: str
    always_human: bool = Field(description="True when no setting or automated actor may ever approve it.")
    requested_by: dict[str, Any] | None
    decided_by: dict[str, Any] | None
    decided_at: datetime | None
    decision: str | None
    note: str | None
    applied_at: datetime | None
    apply_result: dict[str, Any] | None
    expires_at: datetime
    created_at: datetime


class ApprovalStats(BaseModel):
    """Inbox counters."""

    pending: int
    median_decision_seconds: float | None


def _render(now: datetime) -> Any:
    """Build a renderer that shows expired approvals as expired.

    Args:
        now: Current time.

    Returns:
        The renderer.
    """

    def render(doc: Doc) -> Approval:
        kind = registry.KINDS.get(str(doc["kind"]))
        return Approval(
            id=str(doc["_id"]), kind=str(doc["kind"]), status=service.effective_status(doc, now),
            subject_ref=dict(doc["subject_ref"]), payload=dict(doc.get("payload") or {}),
            payload_hash=str(doc["payload_hash"]), summary=str(doc.get("summary") or ""), risk=str(doc.get("risk")),
            required_role=kind.required_role if kind else registry.OWNER,
            always_human=kind.always_human if kind else True, requested_by=doc.get("requested_by"),
            decided_by=doc.get("decided_by"), decided_at=doc.get("decided_at"), decision=doc.get("decision"),
            note=doc.get("note"), applied_at=doc.get("applied_at"), apply_result=doc.get("apply_result"),
            expires_at=doc["expires_at"], created_at=doc["created_at"])

    return render


@router.get("/approvals", operation_id="approvals_list", summary="List approvals")
def approvals_list(request: Request, principal: FirmViewer, status: Status | None = None, kind: Kind | None = None,
                   subject_type: Literal["load", "carrier"] | None = None,
                   subject_id: Annotated[str | None, Query(max_length=ID_MAX)] = None,
                   limit: LimitQuery = DEFAULT_LIMIT, cursor: CursorQuery = None) -> Page[Approval]:
    """List approvals, newest first; `status=pending` is the "needs your yes" inbox.

    Args:
        request: Incoming request.
        principal: Firm member.
        status: Only this status (pending excludes expired ones).
        kind: Only this kind.
        subject_type: Only this subject type.
        subject_id: Only this subject.
        limit: Page size.
        cursor: Cursor from the previous page.

    Returns:
        One page.

    Raises:
        ApiError: 400 invalid_cursor.
    """
    now = get_context(request).clock()
    filters = {"status": status, "kind": kind, "subject_type": subject_type, "subject_id": subject_id}
    docs = service.list_approvals(firm_db(request, principal), filters, now, decode_cursor(cursor), limit)
    return page_of(docs, limit, _render(now))


@router.post("/approvals", status_code=201, operation_id="approvals_create", summary="Propose an approval")
def approvals_create(body: ApprovalCreate, request: Request, principal: FirmDispatcher,
                     guard: FirmIdempotency) -> Approval:
    """Propose an action for a person to approve (audited, emits approval.created).

    Args:
        body: Kind, subject and payload.
        request: Incoming request.
        principal: Dispatcher or owner.
        guard: Idempotency guard.

    Returns:
        The pending approval.

    Raises:
        RepoError: 404 subject not in this firm; 409 approval_pending, illegal_transition or rate_mismatch; 422.
    """
    proposal = service.Proposal(body.kind, body.subject_ref.type, body.subject_ref.id,
                                body.payload.model_dump(exclude_unset=True), body.summary)
    ctx = write_context(request, principal)
    doc = service.create(firm_db(request, principal), ctx, proposal)
    approval = _render(ctx.now())(doc)
    guard.save(201, approval.model_dump(mode="json"))
    return approval


@router.get("/approvals/stats", operation_id="approvals_stats", summary="Approval counters")
def approvals_stats(request: Request, principal: FirmViewer) -> ApprovalStats:
    """Count pending approvals and the median time to a decision (last 200 decisions).

    Args:
        request: Incoming request.
        principal: Firm member.

    Returns:
        The counters.
    """
    return ApprovalStats(**service.stats(firm_db(request, principal), get_context(request).clock()))


@router.get("/approvals/{approval_id}", operation_id="approvals_get", summary="Get an approval")
def approvals_get(approval_id: RecordId, request: Request, principal: FirmViewer) -> Approval:
    """Return one approval with its full payload and outcome.

    Args:
        approval_id: Approval id.
        request: Incoming request.
        principal: Firm member.

    Returns:
        The approval.

    Raises:
        RepoError: 404.
    """
    return _render(get_context(request).clock())(service.get(firm_db(request, principal), approval_id))


@router.post("/approvals/{approval_id}/decision", operation_id="approvals_decide", summary="Decide an approval")
def approvals_decide(approval_id: RecordId, body: DecisionInput, request: Request, principal: FirmDispatcher,
                     guard: FirmIdempotency) -> Approval:
    """Approve or deny; approving runs the action at once. Retrying an approve re-runs a failed action, never twice.

    Owners decide accept_rate, approve_ratecon and carrier_terms_change; dispatchers may decide cancel_load.

    Args:
        approval_id: Approval id.
        body: Decision, the payload_hash shown, and an optional note.
        request: Incoming request.
        principal: Dispatcher or owner (the kind's role is checked).
        guard: Idempotency guard.

    Returns:
        The approval after the decision (status applied, apply_failed or denied).

    Raises:
        RepoError: 403 forbidden, 404, 409 payload_changed, already_decided or approval_expired, 422.
    """
    ctx = write_context(request, principal)
    doc = service.decide(firm_db(request, principal), ctx, approval_id, principal, body.decision, body.payload_hash,
                         body.note)
    approval = _render(ctx.now())(doc)
    guard.save(200, approval.model_dump(mode="json"))
    return approval
