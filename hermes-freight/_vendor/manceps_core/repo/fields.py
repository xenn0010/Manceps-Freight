"""Field validators shared by every firm-data repository (API, imports and, later, the agent use the same rules).

Tag, note and MC rules are ported from hermes-freight/brokers.py; phone and email rules are the platform's.
Validators raise `Invalid` naming the field and never echo the submitted value.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from bson import ObjectId

from ..emails import normalize_email
from ..phones import normalize_phone
from .errors import Invalid, NotFound

TAG_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
MAX_TAGS = 10
MAX_NOTE_CHARS = 1000
NAME_MAX = 200
SHORT_TEXT_MAX = 500
MAX_LIST_ITEMS = 50
MAX_CONTACT_POINTS = 10
QUERY_MAX = 100
NON_DIGITS = re.compile(r"\D")
STATE_PATTERN = re.compile(r"^[A-Z]{2}$")


def text(field: str, value: Any, max_len: int = NAME_MAX, required: bool = False) -> str | None:
    """Trim a free-text value; blank becomes None.

    Args:
        field: Field name.
        value: Raw value.
        max_len: Maximum characters after trimming.
        required: Refuse a missing or blank value.

    Returns:
        The trimmed text, or None when blank and optional.

    Raises:
        Invalid: If required and blank, or too long.
    """
    cleaned = "" if value is None else str(value).strip()
    if not cleaned:
        if required:
            raise Invalid(field, f"{field} is required")
        return None
    if len(cleaned) > max_len:
        raise Invalid(field, f"{field} is longer than {max_len} characters")
    return cleaned


def digits(field: str, value: Any) -> str:
    """Reduce an MC or DOT number to its digits (plugin rule: "MC-0123" -> "0123").

    Args:
        field: Field name.
        value: Raw value.

    Returns:
        The digits.

    Raises:
        Invalid: If there are no digits.
    """
    found = NON_DIGITS.sub("", str(value or ""))
    if not found:
        raise Invalid(field, f"{field} must contain digits")
    return found


def tags(field: str, value: Any) -> list[str]:
    """Validate tags like "slow_pay" (plugin rule): lowercase snake_case, deduplicated, sorted, at most MAX_TAGS.

    Args:
        field: Field name.
        value: Iterable of tag strings, or None.

    Returns:
        The tags.

    Raises:
        Invalid: On malformed tags or too many.
    """
    cleaned = sorted({str(tag).strip().lower() for tag in _items(field, value)})
    if len(cleaned) > MAX_TAGS:
        raise Invalid(field, f"at most {MAX_TAGS} tags")
    if any(not TAG_PATTERN.fullmatch(tag) for tag in cleaned):
        raise Invalid(field, "tags must be snake_case words of 2 to 32 characters")
    return cleaned


def phone(field: str, value: Any) -> str:
    """Normalize a US phone number to E.164.

    Args:
        field: Field name.
        value: Raw value.

    Returns:
        +1XXXXXXXXXX.

    Raises:
        Invalid: If it is not a 10-digit US number.
    """
    try:
        return normalize_phone(str(value or ""))
    except ValueError as exc:
        raise Invalid(field, str(exc)) from exc


def email(field: str, value: Any) -> str:
    """Normalize an email address.

    Args:
        field: Field name.
        value: Raw value.

    Returns:
        The lowercased address.

    Raises:
        Invalid: If it does not look like an address.
    """
    try:
        return normalize_email(str(value or ""))
    except ValueError as exc:
        raise Invalid(field, str(exc)) from exc


def phones(field: str, value: Any) -> list[str]:
    """Normalize a list of phone numbers, keeping first-seen order and dropping duplicates.

    Args:
        field: Field name.
        value: Iterable of numbers, or None.

    Returns:
        E.164 numbers.

    Raises:
        Invalid: On a bad number or more than MAX_CONTACT_POINTS.
    """
    items = _items(field, value, MAX_CONTACT_POINTS)
    return list(dict.fromkeys(phone(field, item) for item in items))


def emails(field: str, value: Any) -> list[str]:
    """Normalize a list of email addresses, keeping first-seen order and dropping duplicates.

    Args:
        field: Field name.
        value: Iterable of addresses, or None.

    Returns:
        Lowercased addresses.

    Raises:
        Invalid: On a bad address or more than MAX_CONTACT_POINTS.
    """
    items = _items(field, value, MAX_CONTACT_POINTS)
    return list(dict.fromkeys(email(field, item) for item in items))


def text_list(field: str, value: Any, max_len: int = NAME_MAX) -> list[str]:
    """Trim a list of short texts, dropping blanks.

    Args:
        field: Field name.
        value: Iterable of strings, or None.
        max_len: Maximum characters per item.

    Returns:
        The non-blank items.

    Raises:
        Invalid: On too many or too long items.
    """
    cleaned = (text(field, item, max_len) for item in _items(field, value))
    return [item for item in cleaned if item is not None]


def state(field: str, value: Any) -> str:
    """Validate a two-letter US state or province code.

    Args:
        field: Field name.
        value: Raw value.

    Returns:
        The uppercased code.

    Raises:
        Invalid: If it is not two letters.
    """
    code = str(value or "").strip().upper()
    if not STATE_PATTERN.fullmatch(code):
        raise Invalid(field, f"{field} must be a two-letter code")
    return code


def choice(field: str, value: Any, allowed: Iterable[str]) -> str:
    """Check a value is one of a fixed set.

    Args:
        field: Field name.
        value: Raw value.
        allowed: Allowed values.

    Returns:
        The value.

    Raises:
        Invalid: If it is not allowed.
    """
    options = sorted(allowed)
    if value not in options:
        raise Invalid(field, f"{field} must be one of {', '.join(options)}")
    return str(value)


def aware_datetime(field: str, value: Any) -> datetime:
    """Require a timezone-aware datetime.

    Args:
        field: Field name.
        value: Raw value.

    Returns:
        The datetime.

    Raises:
        Invalid: If it is not a timezone-aware datetime.
    """
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise Invalid(field, f"{field} must be a timezone-aware datetime")
    return value


def parse_id(raw: Any, what: str) -> ObjectId:
    """Parse a record id from a path or reference; malformed ids are simply not found.

    Args:
        raw: Id text.
        what: Record kind for the error.

    Returns:
        The ObjectId.

    Raises:
        NotFound: If the id is malformed.
    """
    if isinstance(raw, ObjectId):
        return raw
    if not isinstance(raw, str) or not ObjectId.is_valid(raw):
        raise NotFound(what)
    return ObjectId(raw)


def contains(query: str) -> dict[str, str]:
    """Build a case-insensitive substring match that treats the query literally.

    Args:
        query: Search text.

    Returns:
        A $regex condition.
    """
    return {"$regex": re.escape(query.strip()[:QUERY_MAX]), "$options": "i"}


def _items(field: str, value: Any, max_items: int = MAX_LIST_ITEMS) -> list[Any]:
    """Turn a list-like value into a bounded list.

    Args:
        field: Field name.
        value: List, tuple or None.
        max_items: Maximum items.

    Returns:
        The items.

    Raises:
        Invalid: If it is not a list or has too many items.
    """
    if value is None:
        return []
    if not isinstance(value, list | tuple | set | frozenset):
        raise Invalid(field, f"{field} must be a list")
    items: list[Any] = list(value)  # pyright: ignore[reportUnknownArgumentType]
    if len(items) > max_items:
        raise Invalid(field, f"{field} has more than {max_items} items")
    return items
