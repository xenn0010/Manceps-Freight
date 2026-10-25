"""Turn raw spreadsheet cells into field values before the repository validators see them.

Spreadsheets hand us numbers where we expect text (MC 123456.0, phone 2145550199.0), Excel serial dates, "Yes"/"No"
flags and lists packed into one cell ("Dry Van; Reefer", Google's "a ::: b"). Each kind here either returns a clean
value, None for an empty cell, or raises CoerceError; the repository then applies the product rules.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from openpyxl.utils.datetime import CALENDAR_WINDOWS_1900

from .header import as_list, cell_text

KINDS = frozenset({"text", "digits", "phone", "email", "number", "bool", "date", "list", "slug_list"})
TRUE_WORDS = frozenset({"yes", "y", "true", "t", "1", "x", "signed", "on"})
FALSE_WORDS = frozenset({"no", "n", "false", "f", "0", "off", "unsigned"})
NUMBER_NOISE = re.compile(r"[\s$,%]")
LIST_SEPARATORS = re.compile(r"\s*(?::::|[,;|/\n])\s*")
SLUG_NOISE = re.compile(r"[^a-z0-9]+")
DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d", "%m-%d-%Y", "%d %b %Y", "%b %d, %Y")
MIN_SERIAL = 1.0
MAX_SERIAL = 2_958_465.0  # 9999-12-31 in the 1900 system
MAX_LIST_ITEMS = 50
LOTUS_LEAP_DAY = 60


class CoerceError(ValueError):
    """A cell cannot be read as the field's kind."""


def _number(value: Any) -> float | None:
    """Read a finite number; "$2,500.50" and "12%" are accepted.

    Args:
        value: Cell.

    Returns:
        The number, or None for an empty cell.

    Raises:
        CoerceError: If it is not a finite number.
    """
    if isinstance(value, bool) or isinstance(value, datetime | date | list):
        raise CoerceError("expected a number")
    if isinstance(value, int | float):
        number = float(value)
    else:
        text = NUMBER_NOISE.sub("", cell_text(value))
        if not text:
            return None
        try:
            number = float(text)
        except ValueError as exc:
            raise CoerceError("expected a number") from exc
    if not math.isfinite(number):
        raise CoerceError("expected a finite number")
    return number


def _bool(value: Any) -> bool | None:
    """Read a yes/no flag.

    Args:
        value: Cell.

    Returns:
        The flag, or None for an empty cell.

    Raises:
        CoerceError: If it is not a recognizable yes or no.
    """
    if isinstance(value, bool):
        return value
    text = cell_text(value).lower()
    if not text:
        return None
    if text in TRUE_WORDS:
        return True
    if text in FALSE_WORDS:
        return False
    raise CoerceError("expected yes or no")


def _serial(number: float, epoch: datetime | None) -> datetime:
    """Convert an Excel serial date with the workbook's epoch.

    Args:
        number: Serial day number.
        epoch: Workbook epoch (1900 or 1904 system), or None for the 1900 system.

    Returns:
        Aware UTC datetime.

    Raises:
        CoerceError: If the serial is outside the representable range.
    """
    if not MIN_SERIAL <= number <= MAX_SERIAL:
        raise CoerceError("expected a date")
    base = epoch or CALENDAR_WINDOWS_1900
    if base == CALENDAR_WINDOWS_1900 and number < LOTUS_LEAP_DAY:
        number += 1  # Excel counts the non-existent 1900-02-29 (Lotus 1-2-3 compatibility)
    try:
        return (base + timedelta(days=number)).replace(tzinfo=UTC)
    except OverflowError as exc:
        raise CoerceError("expected a date") from exc


def _date(value: Any, epoch: datetime | None) -> datetime | None:
    """Read a date: a datetime cell, an Excel serial, or text such as 2026-11-30 or 11/30/2026.

    Args:
        value: Cell.
        epoch: Workbook epoch for serial numbers.

    Returns:
        Aware UTC datetime, or None for an empty cell.

    Raises:
        CoerceError: If it is not a date.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if isinstance(value, bool) or isinstance(value, list):
        raise CoerceError("expected a date")
    if isinstance(value, int | float):
        return _serial(float(value), epoch)
    text = cell_text(value)
    if not text:
        return None
    if text.replace(".", "", 1).isdigit():
        return _serial(float(text), epoch)
    for pattern in DATE_FORMATS:
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise CoerceError("expected a date such as 2026-11-30")


def _list(value: Any) -> list[str] | None:
    """Split a multi-value cell; a cell that is already a list is trimmed.

    Args:
        value: Cell.

    Returns:
        Non-empty items, or None when there are none.

    Raises:
        CoerceError: On more than MAX_LIST_ITEMS items.
    """
    items: list[str] = [cell_text(item) for item in as_list(value)] if isinstance(value, list) else \
        LIST_SEPARATORS.split(cell_text(value))
    kept = [item for item in items if item]
    if len(kept) > MAX_LIST_ITEMS:
        raise CoerceError(f"at most {MAX_LIST_ITEMS} values")
    return kept or None


def _slugs(value: Any) -> list[str] | None:
    """Split a cell into snake_case words ("Dry Van" -> dry_van), the shape of equipment types and tags.

    Args:
        value: Cell.

    Returns:
        Slugs, or None when empty.

    Raises:
        CoerceError: On too many items.
    """
    items = _list(value) or []
    slugs = [SLUG_NOISE.sub("_", item.lower()).strip("_") for item in items]
    kept = list(dict.fromkeys(slug for slug in slugs if slug))
    return kept or None


def coerce(kind: str, value: Any, epoch: datetime | None) -> Any:
    """Read one cell as a field kind.

    Args:
        kind: One of KINDS.
        value: Raw cell (str, int, float, bool, datetime, list or None).
        epoch: Workbook epoch for serial dates (None for CSV and the 1900 system).

    Returns:
        The value, or None for an empty cell.

    Raises:
        CoerceError: If the cell cannot be read as that kind.
        KeyError: For an unknown kind (a programming error).
    """
    if kind in ("text", "digits", "phone", "email"):
        return cell_text(value) or None
    if kind == "number":
        return _number(value)
    if kind == "bool":
        return _bool(value)
    if kind == "date":
        return _date(value, epoch)
    if kind == "list":
        return _list(value)
    if kind == "slug_list":
        return _slugs(value)
    raise KeyError(kind)
