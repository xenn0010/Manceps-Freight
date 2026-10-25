"""Cursor pagination `{items, next_cursor}`: the cursor is an opaque urlsafe-base64 encoding of the last `_id`."""

from __future__ import annotations

import base64
import binascii
from typing import Annotated, Generic, TypeVar

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Query
from pydantic import BaseModel

from .errors import ApiError

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
MAX_CURSOR_CHARS = 128

ItemT = TypeVar("ItemT")

LimitQuery = Annotated[int, Query(ge=1, le=MAX_LIMIT, description="Maximum items per page.")]
CursorQuery = Annotated[str | None, Query(max_length=MAX_CURSOR_CHARS, description="next_cursor from the last page.")]


class Page(BaseModel, Generic[ItemT]):
    """One page of results."""

    items: list[ItemT]
    next_cursor: str | None


def encode_cursor(object_id: ObjectId) -> str:
    """Encode the last item's id as a cursor.

    Args:
        object_id: Last `_id` on the page.

    Returns:
        Opaque cursor text.
    """
    return base64.urlsafe_b64encode(object_id.binary).decode("ascii").rstrip("=")


def decode_cursor(cursor: str | None) -> ObjectId | None:
    """Decode a cursor back into an ObjectId.

    Args:
        cursor: Cursor from a previous page, or None for the first page.

    Returns:
        The ObjectId, or None for the first page.

    Raises:
        ApiError: 400 invalid_cursor if the cursor is malformed.
    """
    if cursor is None:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        return ObjectId(raw)
    except (binascii.Error, ValueError, InvalidId, TypeError) as exc:
        raise ApiError(400, "invalid_cursor", "the cursor is not valid") from exc
