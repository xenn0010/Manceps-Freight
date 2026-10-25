"""Types and renderers shared by the firm-data routes (carriers, fleet, brokers, contacts, notes)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import Path
from pydantic import BaseModel, Field

from manceps_core.emails import EMAIL_MAX
from manceps_core.mongo import Doc
from manceps_core.repo import fields
from manceps_core.tenancy import Principal

ID_MAX = 64
PHONE_MAX = 32
NUMBER_MAX = 32
CODE_MAX = 16
TAG_MAX = 64
OWNER = "owner"

RecordId = Annotated[str, Path(min_length=1, max_length=ID_MAX, description="Record id.")]
Name = Annotated[str, Field(max_length=fields.NAME_MAX)]
LongText = Annotated[str, Field(max_length=fields.MAX_NOTE_CHARS)]
Phone = Annotated[str, Field(max_length=PHONE_MAX)]
Email = Annotated[str, Field(max_length=EMAIL_MAX)]
Number = Annotated[str, Field(max_length=NUMBER_MAX)]
Code = Annotated[str, Field(max_length=CODE_MAX)]
Tag = Annotated[str, Field(max_length=TAG_MAX)]
Tags = Annotated[list[Tag], Field(max_length=fields.MAX_LIST_ITEMS)]


class ConsentState(BaseModel):
    """Consent cache (the ledger in consent_events is the truth)."""

    sms: bool
    voice: bool
    whatsapp: bool
    method: str | None
    recorded_at: datetime | None


def can_set_terms(principal: Principal) -> bool:
    """Decide whether the caller may change money and contract terms directly (otherwise an approval is needed).

    Args:
        principal: Firm principal.

    Returns:
        True for the firm owner.
    """
    return principal.role == OWNER


def consent_state(raw: Any) -> ConsentState | None:
    """Render a consent cache, tolerating plugin-written records.

    Args:
        raw: Stored consent value.

    Returns:
        The state, or None when absent.
    """
    if not isinstance(raw, dict):
        return None
    cache: dict[str, Any] = raw  # pyright: ignore[reportUnknownVariableType]
    recorded = cache.get("recorded_at")
    return ConsentState(sms=bool(cache.get("sms")), voice=bool(cache.get("voice")),
                        whatsapp=bool(cache.get("whatsapp")), method=_text(cache.get("method")),
                        recorded_at=recorded if isinstance(recorded, datetime) else None)


def _text(value: Any) -> str | None:
    """Render an optional text value.

    Args:
        value: Stored value.

    Returns:
        The text, or None.
    """
    return None if value is None else str(value)


def text_of(doc: Doc, key: str) -> str | None:
    """Read an optional text field of a document.

    Args:
        doc: Document.
        key: Field name.

    Returns:
        The text, or None.
    """
    return _text(doc.get(key))


def list_of(doc: Doc, key: str) -> list[Any]:
    """Read an optional list field of a document.

    Args:
        doc: Document.
        key: Field name.

    Returns:
        The list (empty when absent or not a list).
    """
    value = doc.get(key)
    return list(value) if isinstance(value, list) else []  # pyright: ignore[reportUnknownArgumentType]
