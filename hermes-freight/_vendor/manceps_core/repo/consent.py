"""Contact consent: the append-only `consent_events` ledger is the truth; `<subject>.consent` is a cache of it.

A grant needs the channel and how consent was given (`method`). Every grant or revoke first appends a ledger row,
then recomputes the subject's cache from the whole ledger, so the cache always equals the ledger after a write.
`rebuild_cache` repairs a cache that drifted (for example one written by an old plugin version).
The cache keeps the plugin's shape `{sms, voice, whatsapp, method, recorded_at}`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal

from bson import ObjectId

from ..mongo import Doc, MongoDb
from . import fields
from .store import WriteContext, get_by_id, ref_of

CONSENT_EVENTS = "consent_events"
CONSENT_CHANNELS = ("sms", "voice", "whatsapp")
GRANTED, REVOKED = "granted", "revoked"
METHOD_MAX = 300
EVIDENCE_MAX = 200
REVOKE_METHOD = "revoked by the firm"
SUBJECT_COLLECTIONS: Mapping[str, str] = {"carrier": "carriers", "driver": "drivers"}
SYSTEM_REPAIR = WriteContext(who={"kind": "system", "id": "consent.rebuild_cache"})

SubjectType = Literal["carrier", "driver"]
Action = Literal["granted", "revoked"]


def cache_from_events(events: Iterable[Mapping[str, Any]]) -> dict[str, Any] | None:
    """Compute the consent cache from ledger rows.

    Args:
        events: Ledger rows of one subject, in any order.

    Returns:
        {sms, voice, whatsapp, method, recorded_at} from the latest row per channel, or None without rows.
    """
    ordered = sorted(events, key=lambda event: (event["at"], event["_id"]))
    if not ordered:
        return None
    cache: dict[str, Any] = {channel: False for channel in CONSENT_CHANNELS}
    for event in ordered:
        cache[str(event["channel"])] = event["action"] == GRANTED
    latest = ordered[-1]
    cache["method"] = latest["method"]
    cache["recorded_at"] = latest["at"]
    return cache


def _ledger(db: MongoDb, subject_type: SubjectType, subject_id: ObjectId) -> list[Doc]:
    """Read a subject's ledger rows.

    Args:
        db: Firm database.
        subject_type: carrier or driver.
        subject_id: Subject id.

    Returns:
        The rows.
    """
    return list(db[CONSENT_EVENTS].find({"subject.type": subject_type, "subject.id": str(subject_id)}))


def _write_cache(db: MongoDb, subject_type: SubjectType, subject_id: ObjectId) -> dict[str, Any] | None:
    """Recompute and store a subject's cache from its ledger.

    Args:
        db: Firm database.
        subject_type: carrier or driver.
        subject_id: Subject id.

    Returns:
        The cache, or None when the ledger is empty (the field is removed).
    """
    cache = cache_from_events(_ledger(db, subject_type, subject_id))
    update: dict[str, Any] = {"$set": {"consent": cache}} if cache is not None else {"$unset": {"consent": ""}}
    db[SUBJECT_COLLECTIONS[subject_type]].update_one({"_id": subject_id}, update)
    return cache


def record_consent(db: MongoDb, ctx: WriteContext, subject_type: SubjectType, subject_id: Any, channel: str,
                   action: Action, method: str | None, evidence_ref: str | None = None) -> Doc:
    """Append a grant or revoke to the ledger, then refresh the subject's cache from the ledger.

    Args:
        db: Firm database.
        ctx: Writer.
        subject_type: carrier or driver.
        subject_id: Subject id.
        channel: sms, voice or whatsapp.
        action: granted or revoked.
        method: How consent was given (required for a grant; defaults to REVOKE_METHOD for a revoke).
        evidence_ref: Optional reference to stored evidence (document id, recording id).

    Returns:
        The subject after the cache refresh.

    Raises:
        Invalid: On an unknown channel or a grant without a method.
        NotFound: If the subject is not live.
    """
    fields.choice("channel", channel, CONSENT_CHANNELS)
    how = fields.text("method", method, METHOD_MAX, required=action == GRANTED) or REVOKE_METHOD
    evidence = fields.text("evidence_ref", evidence_ref, EVIDENCE_MAX)
    collection = SUBJECT_COLLECTIONS[subject_type]
    subject = get_by_id(db, collection, subject_id, subject_type)
    event: Doc = {"subject": {"type": subject_type, "id": str(subject["_id"]), "phone": subject.get("phone")},
                  "channel": channel, "action": action, "method": how, "evidence_ref": evidence,
                  "at": ctx.now(), "by": dict(ctx.who)}
    db[CONSENT_EVENTS].insert_one(event)
    cache = _write_cache(db, subject_type, subject["_id"])
    verb = "grant" if action == GRANTED else "revoke"
    ctx.audit(db, f"{subject_type}.consent_{verb}", ref_of(subject_type, subject),
              {"consent": subject.get("consent")}, {"consent": cache, "channel": channel})
    return get_by_id(db, collection, subject["_id"], subject_type)


def rebuild_cache(db: MongoDb, subject_type: SubjectType, subject_id: ObjectId,
                  ctx: WriteContext = SYSTEM_REPAIR) -> dict[str, Any] | None:
    """Repair a subject's consent cache from the ledger (audited when it changes anything).

    Args:
        db: Firm database.
        subject_type: carrier or driver.
        subject_id: Subject id.
        ctx: Writer recorded in the audit log.

    Returns:
        The rebuilt cache, or None when the ledger is empty.

    Raises:
        KeyError: If the subject type is unknown.
    """
    collection = SUBJECT_COLLECTIONS[subject_type]
    before = db[collection].find_one({"_id": subject_id}, {"consent": 1})
    cache = _write_cache(db, subject_type, subject_id)
    previous = (before or {}).get("consent")
    if previous != cache:
        ctx.audit(db, f"{subject_type}.consent_rebuild", {"type": subject_type, "id": str(subject_id)},
                  {"consent": previous}, {"consent": cache})
    return cache
