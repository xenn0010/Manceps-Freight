"""Broker memory: what this firm has learned about each broker, scoped to the tenant."""

from __future__ import annotations

import json
import re
from typing import Any

import pymongo
import pymongo.errors

from . import store

MAX_NOTE_CHARS = 1000
MAX_NOTES_RETURNED = 20
MAX_TAGS = 10
TAG_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


def _mc(raw: Any) -> str:
    """Normalize an MC number to digits.

    Args:
        raw: MC number in any format, e.g. "MC-123456".

    Returns:
        Digits only.

    Raises:
        ValueError: If no digits are present.
    """
    digits = re.sub(r"\D", "", str(raw or ""))
    if not digits:
        raise ValueError("mc_number is required")
    return digits


def _tags(raw: Any) -> list[str]:
    """Validate tags like "slow_pay" or "good_detention".

    Args:
        raw: List of tag strings or None.

    Returns:
        Deduplicated, validated tags.

    Raises:
        ValueError: On malformed tags or too many tags.
    """
    tags = sorted({str(t).strip().lower() for t in (raw or [])})
    if len(tags) > MAX_TAGS:
        raise ValueError(f"at most {MAX_TAGS} tags")
    bad = [t for t in tags if not TAG_PATTERN.fullmatch(t)]
    if bad:
        raise ValueError(f"tags must be snake_case words: {bad}")
    return tags


def broker_remember(args: dict[str, Any], **kwargs: Any) -> str:
    """Record a note and tags about a broker for future negotiations.

    Args:
        args: {"mc_number": str, "note": str, "tags": [str], "company": str}.
        **kwargs: Hermes context (session_id is recorded).

    Returns:
        JSON with the updated broker memory or an error.
    """
    try:
        mc = _mc(args.get("mc_number"))
        note = str(args.get("note", "")).strip()
        if not note:
            raise ValueError("note is required")
        if len(note) > MAX_NOTE_CHARS:
            raise ValueError(f"note longer than {MAX_NOTE_CHARS} characters")
        tags = _tags(args.get("tags"))
        stamp = store.now()
        update: dict[str, Any] = {
            "$push": {"notes": {"at": stamp, "text": note, "session_id": kwargs.get("session_id")}},
            "$addToSet": {"tags": {"$each": tags}},
            "$set": {"updated_at": stamp},
            "$setOnInsert": {"mc_number": mc, "created_at": stamp},
        }
        if args.get("company"):
            update["$set"]["company"] = str(args["company"]).strip()
        doc = store.collection(store.BROKERS).find_one_and_update(
            {"mc_number": mc}, update, upsert=True, return_document=pymongo.ReturnDocument.AFTER
        )
        store.audit("broker.remember", mc_number=mc, tags=tags, session_id=kwargs.get("session_id"))
        return json.dumps({"broker": store.to_jsonable(doc)})
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    except (RuntimeError, pymongo.errors.PyMongoError) as exc:
        return json.dumps({"error": f"database unavailable: {exc}"})


def broker_recall(args: dict[str, Any], **kwargs: Any) -> str:
    """Return what the firm knows about a broker, plus the latest vetting result.

    Args:
        args: {"mc_number": str}.
        **kwargs: Hermes context (unused).

    Returns:
        JSON with notes (newest first), tags, and the last broker_check verdict.
    """
    try:
        mc = _mc(args.get("mc_number"))
        doc = store.collection(store.BROKERS).find_one({"mc_number": mc})
        last = store.collection(store.BROKER_CHECKS).find_one(
            {"mc_number": mc}, {"verdict": 1, "checked_at": 1}, sort=[("checked_at", pymongo.DESCENDING)]
        )
        memory = store.to_jsonable(doc) or {"mc_number": mc, "notes": [], "tags": []}
        memory["notes"] = list(reversed(memory.get("notes") or []))[:MAX_NOTES_RETURNED]
        return json.dumps({"known": doc is not None, "broker": memory, "last_check": store.to_jsonable(last)})
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    except (RuntimeError, pymongo.errors.PyMongoError) as exc:
        return json.dumps({"error": f"database unavailable: {exc}"})
