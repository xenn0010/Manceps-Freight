"""Approval lifecycle: create a proposal, decide it (a person only), apply it exactly once.

Statuses: pending -> approved -> applied | apply_failed, pending -> denied, pending -> expired. A pending approval
past `expires_at` reads as expired and cannot be decided. `payload_hash = sha256(canonical_json({kind, subject_ref,
payload}))`; the decider sends it back, so a person can only approve exactly what they were shown.

Exactly once: the decision is a conditional update on `status: pending`; `applied_at` and `apply_failed` are set
with conditional updates on `applied_at: None`; and every action is idempotent, so a retried decision re-runs the
action without repeating its effect.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument

from .. import events
from ..hashing import sha256_hex
from ..mongo import Doc, MongoDb
from ..repo import carriers
from ..repo.errors import Conflict, Forbidden, Invalid, NotFound, RepoError
from ..repo.fields import parse_id
from ..repo.store import DESCENDING, WriteContext
from ..tenancy import Principal
from .actions import ACTIONS
from .registry import CARRIER, ROLE_RANK, Kind, kind_of, load_subject

APPROVALS = "approvals"
REF_TYPE = "approval"
PENDING, APPROVED, DENIED, EXPIRED = "pending", "approved", "denied", "expired"
APPLIED, APPLY_FAILED = "applied", "apply_failed"
APPROVE, DENY = "approve", "deny"
HUMAN = "user"
DEFAULT_TTL = timedelta(hours=48)
SUMMARY_MAX = 500
NOTE_MAX = 1000
STATS_SAMPLE = 200
RETRYABLE = frozenset({APPROVED, APPLY_FAILED})


@dataclass(frozen=True)
class Proposal:
    """A requested approval."""

    kind: str
    subject_type: str
    subject_id: str
    payload: Mapping[str, Any]
    summary: str | None = None


def payload_hash(kind: str, subject_ref: Mapping[str, Any], payload: Mapping[str, Any]) -> str:
    """Hash what a person approves.

    Args:
        kind: Kind name.
        subject_ref: {type, id}.
        payload: Normalized payload.

    Returns:
        Hex SHA-256 of the canonical JSON.
    """
    return sha256_hex({"kind": kind, "subject_ref": dict(subject_ref), "payload": dict(payload)})


def _subject(db: MongoDb, kind: Kind, proposal: Proposal) -> Doc:
    """Load the subject the proposal names, in this firm only.

    Args:
        db: Firm database.
        kind: Kind.
        proposal: Proposal.

    Returns:
        The subject document.

    Raises:
        Invalid: When the subject type does not fit the kind.
        NotFound: When the subject is not a live record of this firm.
    """
    if proposal.subject_type != kind.subject_type:
        raise Invalid(["subject_ref", "type"], f"{kind.name} applies to a {kind.subject_type}")
    if kind.subject_type == CARRIER:
        return carriers.get_carrier(db, proposal.subject_id)
    return load_subject(db, proposal.subject_id)


def _summary(kind: Kind, subject: Mapping[str, Any], payload: Mapping[str, Any], given: str | None) -> str:
    """Build the one-line summary shown on the approval card.

    Args:
        kind: Kind.
        subject: Subject document.
        payload: Normalized payload.
        given: Caller's summary, or None.

    Returns:
        The summary.

    Raises:
        Invalid: If the given summary is too long.
    """
    if given is not None and given.strip():
        if len(given.strip()) > SUMMARY_MAX:
            raise Invalid("summary", f"summary is longer than {SUMMARY_MAX} characters")
        return given.strip()
    name = subject.get("ref") or subject.get("name") or subject.get("company") or str(subject["_id"])
    if "rate_cents" in payload:
        return f"{kind.name.replace('_', ' ')}: ${int(payload['rate_cents']) / 100:,.2f} for {name}"
    return f"{kind.name.replace('_', ' ')}: {name}"


def create(db: MongoDb, ctx: WriteContext, proposal: Proposal, ttl: timedelta = DEFAULT_TTL) -> Doc:
    """Create a pending approval (audited, emits approval.created).

    Args:
        db: Firm database.
        ctx: Writer (the requester).
        proposal: What is proposed.
        ttl: How long it may be decided.

    Returns:
        The stored approval.

    Raises:
        Invalid: On an unknown kind, a wrong subject type or a bad payload.
        NotFound: When the subject is not in this firm.
        Conflict: approval_pending when the same kind is already pending for the subject, or a precondition fails.
    """
    kind = kind_of(proposal.kind)
    subject = _subject(db, kind, proposal)
    payload = kind.check(db, subject, proposal.payload)
    ref = {"type": kind.subject_type, "id": str(subject["_id"])}
    now = ctx.now()
    open_one = db[APPROVALS].find_one({"kind": kind.name, "subject_ref": ref, "status": PENDING,
                                       "expires_at": {"$gt": now}})
    if open_one is not None:
        raise Conflict("approval_pending", "this is already waiting for a decision",
                       {"approval_id": str(open_one["_id"])})
    doc: Doc = {"_id": ObjectId(), "kind": kind.name, "status": PENDING, "subject_ref": ref, "payload": payload,
                "payload_hash": payload_hash(kind.name, ref, payload), "risk": kind.risk,
                "summary": _summary(kind, subject, payload, proposal.summary), "requested_by": dict(ctx.who),
                "decided_by": None, "decided_at": None, "decision": None, "note": None, "applied_at": None,
                "apply_result": None, "expires_at": now + ttl, "created_at": now, "updated_at": now}
    db[APPROVALS].insert_one(doc)
    _announce(db, ctx, doc, "approval.created", "approval.create", None)
    return doc


def _announce(db: MongoDb, ctx: WriteContext, doc: Doc, event: str, what: str, before: Doc | None) -> None:
    """Emit an approval event and audit the change.

    Args:
        db: Firm database.
        ctx: Writer.
        doc: Approval after the change.
        event: Event type.
        what: Audit event name.
        before: Approval before the change, or None.
    """
    events.emit(db, event, {"type": REF_TYPE, "id": str(doc["_id"])},
                {"approval_id": str(doc["_id"]), "kind": doc["kind"], "status": doc["status"],
                 "subject_ref": doc["subject_ref"]}, ctx.clock)
    ctx.audit(db, what, {"type": REF_TYPE, "id": str(doc["_id"])}, before, doc)


def get(db: MongoDb, approval_id: Any) -> Doc:
    """Load an approval of this firm.

    Args:
        db: Firm database.
        approval_id: Id text.

    Returns:
        The approval.

    Raises:
        NotFound: If absent or malformed.
    """
    doc = db[APPROVALS].find_one({"_id": parse_id(approval_id, REF_TYPE)})
    if doc is None:
        raise NotFound(REF_TYPE)
    return doc


def effective_status(doc: Mapping[str, Any], now: datetime) -> str:
    """Read an approval's status, with an undecided one past its expiry shown as expired.

    Args:
        doc: Approval.
        now: Current time.

    Returns:
        The status.
    """
    if doc.get("status") == PENDING and doc["expires_at"] <= now:
        return EXPIRED
    return str(doc.get("status"))


def check_decider(kind: Kind, decider: Principal) -> None:
    """Admit only a person with the kind's role.

    Args:
        kind: Kind.
        decider: Caller.

    Raises:
        Forbidden: 403 human_required or forbidden.
    """
    if decider.kind != HUMAN:
        raise Forbidden("human_required", "only a person can decide an approval", {"kind": kind.name})
    if ROLE_RANK.get(decider.role, 0) < ROLE_RANK[kind.required_role]:
        raise Forbidden("forbidden", f"deciding {kind.name} requires the {kind.required_role} role",
                        {"required_role": kind.required_role})


def _record_decision(db: MongoDb, ctx: WriteContext, doc: Doc, decider: Principal, decision: str,
                     note: str | None) -> Doc | None:
    """Store a decision on a pending approval with one conditional update.

    Args:
        db: Firm database.
        ctx: Writer.
        doc: Approval as loaded.
        decider: The person.
        decision: approve or deny.
        note: Optional note.

    Returns:
        The approval after the decision, or None when another decision won the race.
    """
    now = ctx.now()
    decided = db[APPROVALS].find_one_and_update(
        {"_id": doc["_id"], "status": PENDING},
        {"$set": {"status": APPROVED if decision == APPROVE else DENIED, "decision": decision, "note": note,
                  "decided_by": {"kind": decider.kind, "id": decider.user_id, "role": decider.role},
                  "decided_at": now, "updated_at": now}},
        return_document=ReturnDocument.AFTER)
    if decided is not None:
        _announce(db, ctx, decided, "approval.decided", "approval.decide", doc)
    return decided


def _expire(db: MongoDb, ctx: WriteContext, doc: Doc) -> None:
    """Mark a pending approval past its expiry as expired.

    Args:
        db: Firm database.
        ctx: Writer.
        doc: Approval.
    """
    expired = db[APPROVALS].find_one_and_update({"_id": doc["_id"], "status": PENDING},
                                                {"$set": {"status": EXPIRED, "updated_at": ctx.now()}},
                                                return_document=ReturnDocument.AFTER)
    if expired is not None:
        _announce(db, ctx, expired, "approval.expired", "approval.expire", doc)


def decide(db: MongoDb, ctx: WriteContext, approval_id: Any, decider: Principal, decision: str, hash_seen: str,
           note: str | None) -> Doc:
    """Decide an approval and, on approve, apply it. Retrying an approve re-runs a failed or unfinished apply.

    Args:
        db: Firm database.
        ctx: Writer (the decider).
        approval_id: Approval id.
        decider: The person deciding.
        decision: approve or deny.
        hash_seen: The payload_hash the person was shown.
        note: Optional note.

    Returns:
        The approval after the decision (and the apply, if any).

    Raises:
        NotFound: Unknown approval.
        Forbidden: human_required or forbidden.
        Invalid: On an unknown decision or a too-long note.
        Conflict: payload_changed, already_decided or approval_expired.
    """
    if decider.kind != HUMAN:
        raise Forbidden("human_required", "only a person can decide an approval")
    if decision not in (APPROVE, DENY):
        raise Invalid("decision", "decision must be approve or deny")
    if note is not None and len(note) > NOTE_MAX:
        raise Invalid("note", f"note is longer than {NOTE_MAX} characters")
    doc = get(db, approval_id)
    check_decider(kind_of(str(doc["kind"])), decider)
    if hash_seen != doc["payload_hash"]:
        raise Conflict("payload_changed", "this approval changed since you saw it; reload it",
                       {"payload_hash": doc["payload_hash"]})
    if effective_status(doc, ctx.now()) == EXPIRED:
        _expire(db, ctx, doc)
        raise Conflict("approval_expired", "this approval expired; ask for a new one")
    if doc["status"] == PENDING:
        decided = _record_decision(db, ctx, doc, decider, decision, note)
        doc = decided if decided is not None else get(db, doc["_id"])
        if decided is not None:
            return apply(db, ctx, decided) if decision == APPROVE else decided
    if doc["status"] in RETRYABLE and doc.get("decision") == APPROVE == decision and doc.get("applied_at") is None:
        return apply(db, ctx, doc)
    raise Conflict("already_decided", "this approval was already decided", {"status": doc["status"]})


def _actor(ctx: WriteContext, approval: Doc) -> WriteContext:
    """Describe writes made by applying an approval.

    Args:
        ctx: Request writer.
        approval: The approval.

    Returns:
        A context whose actor is the approval and the person who decided it.
    """
    who = {"kind": "approval", "id": str(approval["_id"]), "decided_by": approval["decided_by"]["id"]}
    return WriteContext(who=who, request_id=ctx.request_id, session_id=ctx.session_id, clock=ctx.clock)


def apply(db: MongoDb, ctx: WriteContext, approval: Doc) -> Doc:
    """Run an approved approval's action once and record the outcome.

    Args:
        db: Firm database.
        ctx: Request writer.
        approval: An approval decided approve.

    Returns:
        The approval after the outcome is recorded.
    """
    try:
        result = ACTIONS[str(approval["kind"])](db, _actor(ctx, approval), approval)
    except RepoError as exc:
        failure = {"error": exc.code, "message": exc.message, "details": exc.details}
        failed = db[APPROVALS].find_one_and_update(
            {"_id": approval["_id"], "applied_at": None},
            {"$set": {"status": APPLY_FAILED, "apply_result": failure, "updated_at": ctx.now()}},
            return_document=ReturnDocument.AFTER)
        if failed is None:
            return get(db, approval["_id"])
        _announce(db, ctx, failed, "approval.apply_failed", "approval.apply_failed", approval)
        return failed
    now = ctx.now()
    applied = db[APPROVALS].find_one_and_update(
        {"_id": approval["_id"], "applied_at": None},
        {"$set": {"status": APPLIED, "applied_at": now, "apply_result": result, "updated_at": now}},
        return_document=ReturnDocument.AFTER)
    if applied is None:
        return get(db, approval["_id"])
    _announce(db, ctx, applied, "approval.applied", "approval.apply", approval)
    return applied


def list_approvals(db: MongoDb, filters: Mapping[str, Any], now: datetime, after: ObjectId | None,
                   limit: int) -> list[Doc]:
    """List approvals, newest first.

    Args:
        db: Firm database.
        filters: Optional status (pending excludes expired ones; expired includes them), kind, subject_type,
            subject_id.
        now: Current time.
        after: Cursor id.
        limit: Page size.

    Returns:
        Up to limit + 1 approvals.
    """
    query: dict[str, Any] = {}
    status = filters.get("status")
    if status == PENDING:
        query.update({"status": PENDING, "expires_at": {"$gt": now}})
    elif status == EXPIRED:
        query["$or"] = [{"status": EXPIRED}, {"status": PENDING, "expires_at": {"$lte": now}}]
    elif status:
        query["status"] = status
    for key, field in (("kind", "kind"), ("subject_type", "subject_ref.type"), ("subject_id", "subject_ref.id")):
        if filters.get(key):
            query[field] = filters[key]
    if after is not None:
        query["_id"] = {"$lt": after}
    return list(db[APPROVALS].find(query, limit=limit + 1).sort([("_id", DESCENDING)]))


def stats(db: MongoDb, now: datetime) -> dict[str, Any]:
    """Count pending approvals and the median time to a decision.

    Args:
        db: Firm database.
        now: Current time.

    Returns:
        {pending, median_decision_seconds} (None when nothing was decided yet).
    """
    pending = db[APPROVALS].count_documents({"status": PENDING, "expires_at": {"$gt": now}})
    decided = db[APPROVALS].find({"decided_at": {"$ne": None}}, {"decided_at": 1, "created_at": 1},
                                 limit=STATS_SAMPLE).sort([("decided_at", DESCENDING)])
    seconds = [(doc["decided_at"] - doc["created_at"]).total_seconds() for doc in decided]
    return {"pending": pending, "median_decision_seconds": statistics.median(seconds) if seconds else None}
