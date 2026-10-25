"""Errors raised by the firm-data repositories; the API renders them as the standard error envelope."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

VALIDATION_CODE = "validation_error"
VALUE_ERROR_TYPE = "value_error"


class RepoError(Exception):
    """A refused repository operation with a stable code and safe message."""

    def __init__(self, code: str, message: str, details: Mapping[str, Any] | None = None) -> None:
        """Create the error.

        Args:
            code: Stable machine-readable code.
            message: Human-readable message (no secrets, no submitted values).
            details: Extra structured information.
        """
        super().__init__(message)
        self.code = code
        self.message = message
        self.details: dict[str, Any] = dict(details or {})


class NotFound(RepoError):
    """The record does not exist in this firm (or was deleted)."""

    def __init__(self, what: str) -> None:
        """Create the error.

        Args:
            what: Record kind, e.g. "carrier".
        """
        super().__init__("not_found", f"{what} not found")


class Conflict(RepoError):
    """The write clashes with existing data or a business rule (HTTP 409)."""


class Invalid(RepoError):
    """A field value breaks a data rule (HTTP 422, same shape as request validation errors)."""

    def __init__(self, field: str | Sequence[str | int], message: str, code: str = VALIDATION_CODE) -> None:
        """Create the error for one field.

        Args:
            field: Field name, or a path such as ("phones", 2).
            message: What is wrong, without echoing the value.
            code: Error code; validation_error unless a more specific one helps the client.
        """
        loc = [field] if isinstance(field, str) else list(field)
        super().__init__(code, message, {"errors": [{"loc": ["body", *loc], "msg": message,
                                                     "type": VALUE_ERROR_TYPE}]})
        self.field = loc
