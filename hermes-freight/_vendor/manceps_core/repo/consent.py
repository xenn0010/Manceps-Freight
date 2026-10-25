"""Contact consent: the append-only `consent_events` ledger is the truth; `<subject>.consent` is a cache of it.

A grant needs the channel and how consent was given (`method`). Consent belongs to a phone number and a channel:
only ledger rows recorded for the subject's current number count, and changing the number appends `phone_changed`
revokes for the old one (`revoke_for_phone_change`).

Concurrency: each subject's rows carry a gap-free `version` (1, 2, ...) made unique by an index, so concurrent
writers are totally ordered. The cache is written with a compare-and-set on `consent_version` and on the phone it
was computed for, so a writer holding an older view of the ledger can never overwrite a newer cache: once a revoke
has returned, no concurrent write can make the cache show that consent again. `rebuild_cache` repairs a drifted
cache. The cache keeps the plugin's shape `{sms, voice, whatsapp, method, recorded_at}`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal, cast

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from ..mongo import Doc, MongoDb
from . import fields
from .errors import Conflict
from .store import WriteContext, ensure_auditable, get_by_id, ref_of

CONSENT_EVENTS = "consent_events"
CONSENT_CHANNELS = ("sms", "voice", "whatsapp")
GRANTED, REVOKED = "granted", "revoked"
METHOD_MAX = 300
EVIDENCE_MAX = 200
REVOKE_METHOD = "revoked by the firm"
PHONE_CHANGED = "phone_changed"
VERSION_FIELD = "consent_version"
MAX_APPEND_ATTEMPTS = 20
SUBJECT_COLLECTIONS: Mapping[str, str] = {"carrier": "carriers", "driver": "drivers"}
SYSTEM_REPAIR = WriteContext(who={"kind": "system", "id": "consent.rebuild_cache"})

SubjectType = Literal["carrier", "driver"]
Action = Literal["granted", "revoked"]


def _order(event: Mapping[str, Any]) -> tuple[int, Any, Any]:
    """Sort key for ledger rows: version, then time and id (rows without a version sort first).

    Args:
        event: Ledger row.

    Returns:
        The key.
    """
    return int(event.get("version") or 0), event["at"], event["_id"]


def cache_from_events(events: Iterable[Mapping[str, Any]]) -> dict[str, Any] | None:
    """Compute the consent cache from ledger rows.

    Args:
        events: Ledger rows of one subject, in any order.

    Returns:
        {sms, voice, whatsapp, method, recorded_at} from the latest row per channel, or None without rows.
    """
    ordered = sorted(events, key=_order)
    if not ordered:
        return None
    cache: dict[str, Any] = {channel: False for channel in CONSENT_CHANNELS}
    for event in ordered:
        cache[str(event["channel"])] = event["action"] == GRANTED
    latest = ordered[-1]
    cache["method"] = latest["method"]
    cache["recorded_at"] = latest["at"]
    return cache


def _row_phone(event: Mapping[str, Any]) -> Any:
    """Read the phone number a ledger row was recorded for.

    Args:
        event: Ledger row.

    Returns:
        The number, or None when the row has none.
    """
    subject = event.get("subject")
    return cast(Mapping[str, Any], subject).get("phone") if isinstance(subject, Mapping) else None


def cache_for_phone(events: Iterable[Mapping[str, Any]], phone: str | None) -> dict[str, Any] | None:
    """Compute the cache from the rows recorded for one phone number (consent never follows a number change).

    Args:
        events: Ledger rows of one subject.
        phone: The subject's current number, or None.

    Returns:
        The cache, or None when that number has no rows.
    """
    return cache_from_events(event for event in events if _row_phone(event) == phone)


def _settled(events: Iterable[Mapping[str, Any]]) -> tuple[list[Mapping[str, Any]], int]:
    """Keep the gap-free prefix of versions (a lower version may still be in flight).

    Args:
        events: Ledger rows of one subject.

    Returns:
        (rows up to the highest contiguous version, that version).
    """
    rows = sorted(events, key=_order)
    present = {int(row.get("version") or 0) for row in rows}
    settled = 0
    while settled + 1 in present:
        settled += 1
    return [row for row in rows if int(row.get("version") or 0) <= settled], settled


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


def _write_cache(db: MongoDb, subject_type: SubjectType, subject_id: ObjectId,
                 force: bool = False) -> dict[str, Any] | None:
    """Recompute a subject's cache from its ledger and store it unless a newer cache is already stored.

    Two writers with the same settled version and phone compute the same cache, so equal versions may overwrite.

    Args:
        db: Firm database.
        subject_type: carrier or driver.
        subject_id: Subject id.
        force: Repair mode: overwrite whatever is stored (the ledger is the truth).

    Returns:
        The cache computed for the subject's current number, or None when that number has no rows.
    """
    collection = db[SUBJECT_COLLECTIONS[subject_type]]
    subject = collection.find_one({"_id": subject_id}, {"phone": 1})
    if subject is None:
        return None
    phone = subject.get("phone")
    rows, version = _settled(_ledger(db, subject_type, subject_id))
    cache = cache_for_phone(rows, phone)
    not_newer = {"$or": [{VERSION_FIELD: {"$lte": version}}, {VERSION_FIELD: {"$exists": False}}]}
    update: dict[str, Any] = {"$set": {VERSION_FIELD: version}}
    if cache is None:
        update["$unset"] = {"consent": ""}
    else:
        update["$set"]["consent"] = cache
    collection.update_one({"_id": subject_id} if force else {"_id": subject_id, "phone": phone, **not_newer}, update)
    return cache


def _append(db: MongoDb, ctx: WriteContext, subject_type: SubjectType, subject: Doc, phone: str | None,
            row: Mapping[str, Any]) -> Doc:
    """Append one ledger row with the subject's next version (the unique index serializes concurrent writers).

    Args:
        db: Firm database.
        ctx: Writer.
        subject_type: carrier or driver.
        subject: The subject document.
        phone: Number the row is recorded for.
        row: channel, action, method and evidence_ref.

    Returns:
        The stored row.

    Raises:
        Conflict: consent_busy when other writers keep winning the next version.
    """
    key = {"subject.type": subject_type, "subject.id": str(subject["_id"])}
    for _attempt in range(MAX_APPEND_ATTEMPTS):
        last = db[CONSENT_EVENTS].find_one(key, {"version": 1}, sort=[("version", -1)])
        event: Doc = {"subject": {"type": subject_type, "id": str(subject["_id"]), "phone": phone}, **row,
                      "version": int((last or {}).get("version") or 0) + 1, "at": ctx.now(), "by": dict(ctx.who)}
        try:
            db[CONSENT_EVENTS].insert_one(event)
        except DuplicateKeyError:
            continue
        return event
    raise Conflict("consent_busy", "consent is being changed by another request; try again")


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
        Invalid: On an unknown channel, a grant without a method, or a stored state that cannot be audited.
        NotFound: If the subject is not live.
        Conflict: consent_busy under heavy contention.
    """
    fields.choice("channel", channel, CONSENT_CHANNELS)
    how = fields.text("method", method, METHOD_MAX, required=action == GRANTED) or REVOKE_METHOD
    evidence = fields.text("evidence_ref", evidence_ref, EVIDENCE_MAX)
    collection = SUBJECT_COLLECTIONS[subject_type]
    subject = get_by_id(db, collection, subject_id, subject_type)
    before = {"consent": subject.get("consent")}
    ensure_auditable(before)
    _append(db, ctx, subject_type, subject, subject.get("phone"),
            {"channel": channel, "action": action, "method": how, "evidence_ref": evidence})
    cache = _write_cache(db, subject_type, subject["_id"])
    verb = "grant" if action == GRANTED else "revoke"
    ctx.audit(db, f"{subject_type}.consent_{verb}", ref_of(subject_type, subject), before,
              {"consent": cache, "channel": channel})
    return get_by_id(db, collection, subject["_id"], subject_type)


def revoke_for_phone_change(db: MongoDb, ctx: WriteContext, subject_type: SubjectType, before: Doc) -> None:
    """Revoke, in the ledger, every channel the subject's previous number had consent for, then refresh the cache.

    Call it after the number changed; the new number starts with no consent.

    Args:
        db: Firm database.
        ctx: Writer.
        subject_type: carrier or driver.
        before: The subject as it was before the change (holds the old number).

    Raises:
        Conflict: consent_busy under heavy contention.
    """
    old_phone = before.get("phone")
    held = cache_for_phone(_ledger(db, subject_type, before["_id"]), old_phone) or {}
    granted = [channel for channel in CONSENT_CHANNELS if held.get(channel)]
    for channel in granted:
        _append(db, ctx, subject_type, before, old_phone,
                {"channel": channel, "action": REVOKED, "method": PHONE_CHANGED, "evidence_ref": None})
    cache = _write_cache(db, subject_type, before["_id"])
    if granted:
        ctx.audit(db, f"{subject_type}.consent_revoke", ref_of(subject_type, before),
                  {"consent": before.get("consent")}, {"consent": cache, "channels": granted, "reason": PHONE_CHANGED})


def phone_changes(current: Mapping[str, Any], clean: Mapping[str, Any]) -> dict[str, Any]:
    """Add the cache removal to an update that changes the number, so the write itself drops the old consent.

    Args:
        current: The subject as loaded.
        clean: Validated changes.

    Returns:
        The changes, plus `consent: None` when the phone changes.
    """
    if "phone" not in clean or clean["phone"] == current.get("phone"):
        return dict(clean)
    return {**clean, "consent": None}


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
    collection = db[SUBJECT_COLLECTIONS[subject_type]]
    before = collection.find_one({"_id": subject_id}, {"consent": 1})
    cache = _write_cache(db, subject_type, subject_id, force=True)
    previous = (before or {}).get("consent")
    if previous != cache:
        ctx.audit(db, f"{subject_type}.consent_rebuild", {"type": subject_type, "id": str(subject_id)},
                  {"consent": previous}, {"consent": cache})
    return cache
