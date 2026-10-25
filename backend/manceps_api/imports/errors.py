"""Errors raised while reading an uploaded file; the API renders them as the standard envelope."""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import ApiError

UNSUPPORTED_MEDIA_TYPE = 415
PAYLOAD_TOO_LARGE = 413
UNPROCESSABLE = 422


class ImportFileError(ApiError):
    """The file as a whole cannot be imported (wrong type, too large, too many rows, no header...)."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        """Create the error.

        Args:
            status_code: 413, 415 or 422.
            code: Stable error code.
            message: Safe message (never echoes file content).
        """
        super().__init__(status_code, code, message)


@dataclass(frozen=True)
class RowError:
    """One problem with one row or field; stored with the row and shown in the preview and report."""

    code: str
    message: str
    field: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        """Render for storage and the API.

        Returns:
            {code, message, field}.
        """
        return {"code": self.code, "message": self.message, "field": self.field}
