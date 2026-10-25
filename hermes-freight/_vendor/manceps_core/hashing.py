"""Canonical JSON and SHA-256 hashing for audit records, approvals and idempotency.

Canonical form: sorted keys, no whitespace, UTF-8, no NaN or Infinity. Object keys must be strings (json would turn
`{1: x}` into `{"1": x}` and hash it like `{"1": x}`). Datetimes must be timezone-aware and are rendered in ISO 8601;
ObjectIds are rendered as hex strings. Anything else that is not plain JSON is refused, so two different values can
never hash the same by accident.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from bson import ObjectId

SEPARATORS = (",", ":")


def _default(value: Any) -> str:
    """Serialize the few non-JSON types allowed in canonical JSON.

    Args:
        value: Value json could not serialize.

    Returns:
        Its canonical string form.

    Raises:
        ValueError: For a naive datetime.
        TypeError: For any other unsupported type.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("canonical JSON requires timezone-aware datetimes")
        return value.isoformat()
    if isinstance(value, ObjectId):
        return str(value)
    raise TypeError(f"type {type(value).__name__} is not allowed in canonical JSON")


def _check_keys(value: Any) -> None:
    """Refuse mappings with non-string keys anywhere in a value.

    Args:
        value: JSON-like value.

    Raises:
        TypeError: For a non-string key.
    """
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            mapping: dict[Any, Any] = item  # pyright: ignore[reportUnknownVariableType]
            if not all(isinstance(key, str) for key in mapping):
                raise TypeError("canonical JSON object keys must be strings")
            pending.extend(mapping.values())
        elif isinstance(item, list | tuple):
            pending.extend(item)  # pyright: ignore[reportUnknownArgumentType]


def canonical_json(value: Any) -> str:
    """Render a value as canonical JSON.

    Args:
        value: JSON-like value (dict, list, str, int, float, bool, None, aware datetime, ObjectId).

    Returns:
        The canonical JSON text.

    Raises:
        ValueError: For NaN/Infinity or naive datetimes.
        TypeError: For unsupported types or non-string object keys.
    """
    _check_keys(value)
    return json.dumps(value, sort_keys=True, separators=SEPARATORS, ensure_ascii=False, allow_nan=False,
                      default=_default)


def sha256_hex(value: Any) -> str:
    """Hash a value's canonical JSON.

    Args:
        value: JSON-like value.

    Returns:
        Lowercase hex SHA-256 digest.

    Raises:
        ValueError: For NaN/Infinity or naive datetimes.
        TypeError: For unsupported types.
    """
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Hash raw bytes.

    Args:
        data: Bytes to hash.

    Returns:
        Lowercase hex SHA-256 digest.
    """
    return hashlib.sha256(data).hexdigest()
