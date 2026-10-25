"""Carrier roster tools: the firm's own owner-operators and their dispatch terms."""

from __future__ import annotations

import json
import re
from typing import Any

import pymongo.errors
from pymongo import ReturnDocument

from . import store

EQUIPMENT_TYPES = frozenset({"dry_van", "reefer", "flatbed", "step_deck", "power_only", "box_truck", "hotshot"})
CONSENT_CHANNELS = ("sms", "voice", "whatsapp")
MAX_FEE_PCT = 25.0
MAX_LIST = 100
US_COUNTRY_CODE = "1"
US_NATIONAL_DIGITS = 10

# Fields the agent may write; anything else in the call is rejected.
WRITABLE = frozenset({
    "name", "company", "mc_number", "dot_number", "equipment", "dispatch_fee_pct",
    "rate_floor_per_mile", "home_base", "preferred_lanes", "avoid", "notes",
    "agreement_signed", "consent",
})


def normalize_phone(raw: str) -> str:
    """Normalize a US phone number to E.164.

    Args:
        raw: Phone number in any common US format.

    Returns:
        The number as +1XXXXXXXXXX.

    Raises:
        ValueError: If it is not a 10-digit US number.
    """
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == US_NATIONAL_DIGITS + 1 and digits.startswith(US_COUNTRY_CODE):
        digits = digits[1:]
    if len(digits) != US_NATIONAL_DIGITS:
        raise ValueError(f"not a US phone number: {raw!r}")
    return f"+{US_COUNTRY_CODE}{digits}"


def _validate(fields: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize writable carrier fields.

    Args:
        fields: Proposed field values.

    Returns:
        Cleaned fields.

    Raises:
        ValueError: On unknown fields or out-of-range values.
    """
    unknown = set(fields) - WRITABLE
    if unknown:
        raise ValueError(f"unknown fields: {sorted(unknown)}")
    clean = dict(fields)
    if "equipment" in clean:
        bad = set(clean["equipment"]) - EQUIPMENT_TYPES
        if bad:
            raise ValueError(f"unknown equipment {sorted(bad)}; allowed: {sorted(EQUIPMENT_TYPES)}")
    if "dispatch_fee_pct" in clean and not 0 < float(clean["dispatch_fee_pct"]) <= MAX_FEE_PCT:
        raise ValueError(f"dispatch_fee_pct must be in (0, {MAX_FEE_PCT}]")
    if "rate_floor_per_mile" in clean and float(clean["rate_floor_per_mile"]) <= 0:
        raise ValueError("rate_floor_per_mile must be positive")
    if "consent" in clean:
        clean["consent"] = _validate_consent(clean["consent"])
    for key in ("mc_number", "dot_number"):
        if key in clean:
            clean[key] = re.sub(r"\D", "", str(clean[key]))
    return clean


def _validate_consent(consent: dict[str, Any]) -> dict[str, Any]:
    """Validate a consent record; consent needs a channel flag and how it was given.

    Args:
        consent: Mapping of channel -> bool plus a required "method" string.

    Returns:
        Consent record stamped with the recording time.

    Raises:
        ValueError: If channels are unknown or the method is missing.
    """
    unknown = set(consent) - set(CONSENT_CHANNELS) - {"method"}
    if unknown:
        raise ValueError(f"unknown consent keys: {sorted(unknown)}")
    if not str(consent.get("method", "")).strip():
        raise ValueError("consent.method is required (e.g. 'signed dispatch agreement 2026-10-24')")
    record: dict[str, Any] = {ch: bool(consent.get(ch, False)) for ch in CONSENT_CHANNELS}
    record["method"] = str(consent["method"]).strip()
    record["recorded_at"] = store.now()
    return record


def carrier_upsert(args: dict[str, Any], **kwargs: Any) -> str:
    """Create or update a carrier keyed by phone number.

    Args:
        args: {"phone": str, "fields": {...writable fields...}}.
        **kwargs: Hermes context (session_id is recorded in the audit log).

    Returns:
        JSON with the stored carrier or an error.
    """
    try:
        phone = normalize_phone(str(args.get("phone", "")))
        fields = _validate(dict(args.get("fields") or {}))
        stamp = store.now()
        doc = store.collection(store.CARRIERS).find_one_and_update(
            {"phone": phone},
            {"$set": {**fields, "updated_at": stamp}, "$setOnInsert": {"phone": phone, "created_at": stamp}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        store.audit("carrier.upsert", phone=phone, fields=sorted(fields), session_id=kwargs.get("session_id"))
        return json.dumps({"carrier": store.to_jsonable(doc)})
    except (ValueError, TypeError) as exc:
        return json.dumps({"error": str(exc)})
    except (RuntimeError, pymongo.errors.PyMongoError) as exc:
        return json.dumps({"error": f"database unavailable: {exc}"})


def carrier_get(args: dict[str, Any], **kwargs: Any) -> str:
    """Fetch one carrier by phone or MC number.

    Args:
        args: {"phone": str} or {"mc_number": str}.
        **kwargs: Hermes context (unused).

    Returns:
        JSON with the carrier, or found=false.
    """
    try:
        if args.get("phone"):
            query: dict[str, Any] = {"phone": normalize_phone(str(args["phone"]))}
        elif args.get("mc_number"):
            query = {"mc_number": re.sub(r"\D", "", str(args["mc_number"]))}
        else:
            return json.dumps({"error": "give phone or mc_number"})
        doc = store.collection(store.CARRIERS).find_one(query)
        return json.dumps({"found": doc is not None, "carrier": store.to_jsonable(doc)})
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    except (RuntimeError, pymongo.errors.PyMongoError) as exc:
        return json.dumps({"error": f"database unavailable: {exc}"})


def carrier_list(args: dict[str, Any], **kwargs: Any) -> str:
    """List carriers, optionally filtered by equipment type.

    Args:
        args: {"equipment": str} optional.
        **kwargs: Hermes context (unused).

    Returns:
        JSON with a list of carriers.
    """
    try:
        query: dict[str, Any] = {}
        if args.get("equipment"):
            query["equipment"] = str(args["equipment"])
        cursor = store.collection(store.CARRIERS).find(query).sort("name", 1).limit(MAX_LIST)
        return json.dumps({"carriers": [store.to_jsonable(d) for d in cursor]})
    except (RuntimeError, pymongo.errors.PyMongoError) as exc:
        return json.dumps({"error": f"database unavailable: {exc}"})


def consented(phone: str, channel: str) -> bool:
    """Return True only if the roster records consent for this number and channel.

    Args:
        phone: Phone number in any US format.
        channel: One of CONSENT_CHANNELS.

    Returns:
        Whether consent is on file. Any lookup failure returns False (fail closed).
    """
    try:
        doc = store.collection(store.CARRIERS).find_one({"phone": normalize_phone(phone)}, {"consent": 1})
    except (ValueError, RuntimeError, pymongo.errors.PyMongoError):
        return False
    return bool(doc and (doc.get("consent") or {}).get(channel))
