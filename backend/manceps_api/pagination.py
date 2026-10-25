"""Cursor pagination `{items, next_cursor}`: the cursor is an opaque urlsafe-base64 encoding of the last `_id`."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Callable
from typing import Annotated, Generic, TypeVar

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Query
from pydantic import BaseModel

from manceps_core.mongo import Doc

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


def page_of(docs: list[Doc], limit: int, render: Callable[[Doc], ItemT]) -> Page[ItemT]:
    """Build a page from up to limit + 1 documents sorted by `_id`.

    Args:
        docs: Documents fetched with limit + 1.
        limit: Page size.
        render: Turns a document into an item.

    Returns:
        The page; next_cursor is set when more documents follow.
    """
    page = docs[:limit]
    next_cursor = encode_cursor(page[-1]["_id"]) if len(docs) > limit else None
    return Page[ItemT](items=[render(doc) for doc in page], next_cursor=next_cursor)
