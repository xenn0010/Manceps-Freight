"""Broker memory keyed by MC number (plugin-compatible: unique `mc_number`, `notes[]`, `tags[]`) and check history.

Notes are appended to the broker's `notes` array exactly like the plugin's `broker_remember` (`{at, text,
session_id}`, plus `by`). Vetting results go to `broker_checks` (the plugin's collection and shape) and the latest
verdict is copied to `brokers.last_check`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from bson import ObjectId
from pymongo import DESCENDING, ReturnDocument

from ..mongo import Doc, MongoDb
from . import fields
from .errors import Invalid, NotFound
from .store import LIVE, WriteContext, find_live, insert, list_live, ref_of, update

BROKERS = "brokers"
BROKER_CHECKS = "broker_checks"
REF_TYPE = "broker"
MAX_NOTES_RETURNED = 20
PAYMENT_TERMS_MAX = 200
DUPLICATE_MC = ("duplicate_mc", "this broker is already in your firm")

Rule = Callable[[str, Any], Any]
RULES: Mapping[str, Rule] = {
    "mc_number": fields.digits,
    "dot_number": fields.digits,
    "company": fields.text,
    "tags": fields.tags,
    "payment_terms": lambda field, value: fields.text(field, value, PAYMENT_TERMS_MAX),
    "credit_notes": lambda field, value: fields.text(field, value, fields.MAX_NOTE_CHARS),
}
REQUIRED = frozenset({"mc_number"})


def normalize_mc(raw: Any) -> str:
    """Normalize an MC number to digits (plugin rule).

    Args:
        raw: MC number in any format, e.g. "MC-123456".

    Returns:
        The digits.

    Raises:
        Invalid: If there are no digits.
    """
    return fields.digits("mc_number", raw)


def _validate(changes: Mapping[str, Any]) -> dict[str, Any]:
    """Validate broker fields; None is kept (remove on update) except for the MC number.

    Args:
        changes: Proposed values.

    Returns:
        Cleaned values.

    Raises:
        Invalid: On unknown fields or bad values.
    """
    clean: dict[str, Any] = {}
    for name, value in changes.items():
        rule = RULES.get(name)
        if rule is None:
            raise Invalid(name, "this field cannot be written here")
        if value is None and name in REQUIRED:
            raise Invalid(name, f"{name} is required")
        clean[name] = None if value is None else rule(name, value)
    return clean


def create_broker(db: MongoDb, ctx: WriteContext, values: Mapping[str, Any]) -> Doc:
    """Add a broker to the firm's memory.

    Args:
        db: Firm database.
        ctx: Writer.
        values: Fields; mc_number is required.

    Returns:
        The stored broker.

    Raises:
        Invalid: On a missing MC or bad values.
        Conflict: duplicate_mc.
    """
    if values.get("mc_number") is None:
        raise Invalid("mc_number", "mc_number is required")
    clean = {key: value for key, value in _validate(values).items() if value is not None}
    return insert(db, ctx, BROKERS, REF_TYPE, {"tags": [], "notes": [], **clean}, DUPLICATE_MC)


def get_broker(db: MongoDb, mc: Any) -> Doc:
    """Load a live broker by MC.

    Args:
        db: Firm database.
        mc: MC number in any format.

    Returns:
        The broker.

    Raises:
        NotFound: If the firm has no such broker.
    """
    try:
        digits = normalize_mc(mc)
    except Invalid as exc:
        raise NotFound(REF_TYPE) from exc
    return find_live(db, BROKERS, {"mc_number": digits}, REF_TYPE)


def update_broker(db: MongoDb, ctx: WriteContext, mc: Any, changes: Mapping[str, Any]) -> Doc:
    """Change a broker's company, tags, payment terms or credit notes.

    Args:
        db: Firm database.
        ctx: Writer.
        mc: MC number.
        changes: Proposed fields (None removes an optional field).

    Returns:
        The updated broker.

    Raises:
        NotFound: If the broker is not live.
        Invalid: On bad values, an empty change, or an attempt to change the MC.
    """
    if not changes:
        raise Invalid("body", "send at least one field to change")
    if "mc_number" in changes:
        raise Invalid("mc_number", "the MC number identifies the broker and cannot change")
    current = get_broker(db, mc)
    return update(db, ctx, BROKERS, REF_TYPE, current, _validate(changes))


def add_note(db: MongoDb, ctx: WriteContext, mc: Any, text: str) -> dict[str, Any]:
    """Append a note to a broker (plugin shape).

    Args:
        db: Firm database.
        ctx: Writer.
        mc: MC number.
        text: Note text (at most MAX_NOTE_CHARS).

    Returns:
        The stored note.

    Raises:
        NotFound: If the broker is not live.
        Invalid: On a blank or too long note.
    """
    body = fields.text("text", text, fields.MAX_NOTE_CHARS, required=True)
    current = get_broker(db, mc)
    note = {"at": ctx.now(), "text": body, "session_id": ctx.session_id, "by": dict(ctx.who)}
    after = db[BROKERS].find_one_and_update({"_id": current["_id"], **LIVE},
                                            {"$push": {"notes": note}, "$set": {"updated_at": note["at"]}},
                                            return_document=ReturnDocument.AFTER)
    if after is None:
        raise NotFound(REF_TYPE)
    ctx.audit(db, "broker.note", ref_of(REF_TYPE, current), current, after)
    return note


def record_check(db: MongoDb, ctx: WriteContext, broker: Doc, result: Mapping[str, Any]) -> Doc:
    """Store a vetting result and copy its verdict to the broker.

    Args:
        db: Firm database.
        ctx: Writer.
        broker: The live broker that was checked.
        result: run_check output.

    Returns:
        The stored check.
    """
    now = ctx.now()
    stored: Doc = {**result, "mc_number": broker["mc_number"], "checked_at": now, "session_id": ctx.session_id,
                   "by": dict(ctx.who)}
    db[BROKER_CHECKS].insert_one(stored)
    last_check = {"verdict": result["verdict"], "checked_at": now}
    db[BROKERS].update_one({"_id": broker["_id"]}, {"$set": {"last_check": last_check, "updated_at": now}})
    ctx.audit(db, "broker.check", ref_of(REF_TYPE, broker), None, {"verdict": result["verdict"]})
    return stored


def latest_check(db: MongoDb, mc: str) -> Doc | None:
    """Return the newest check for an MC (including checks the plugin ran).

    Args:
        db: Firm database.
        mc: MC digits.

    Returns:
        The check, or None.
    """
    return db[BROKER_CHECKS].find_one({"mc_number": mc}, sort=[("checked_at", DESCENDING)])


def list_checks(db: MongoDb, mc: Any, after: ObjectId | None, limit: int) -> list[Doc]:
    """List a broker's checks, newest first.

    Args:
        db: Firm database.
        mc: MC number.
        after: Cursor id.
        limit: Page size.

    Returns:
        Up to limit + 1 checks.

    Raises:
        NotFound: If the firm has no such broker.
    """
    broker = get_broker(db, mc)
    query: dict[str, Any] = {"mc_number": broker["mc_number"]}
    if after is not None:
        query["_id"] = {"$lt": after}
    return list(db[BROKER_CHECKS].find(query, limit=limit + 1).sort([("_id", DESCENDING)]))


def list_brokers(db: MongoDb, filters: Mapping[str, Any], after: ObjectId | None, limit: int) -> list[Doc]:
    """List live brokers, oldest first.

    Args:
        db: Firm database.
        filters: Optional q (company contains, or MC digits) and tag.
        after: Cursor id.
        limit: Page size.

    Returns:
        Up to limit + 1 brokers.
    """
    query: dict[str, Any] = {}
    if filters.get("tag"):
        query["tags"] = filters["tag"]
    if filters.get("q"):
        query["$or"] = [{"company": fields.contains(filters["q"])}, {"mc_number": str(filters["q"]).strip()}]
    return list_live(db, BROKERS, query, after, limit)
