"""Header row detection and column naming shared by the CSV and XLSX readers.

The header is the first row (within the first HEADER_SCAN_ROWS) with at least MIN_HEADER_CELLS non-empty cells, so
title rows and blank lines above it are skipped. Column names are trimmed, blanks become "Column N", and repeated
names (compared case-insensitively) get " 2", " 3"... so every column has a unique, non-empty name.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeAlias, cast

from .errors import RowError

Cell: TypeAlias = str | int | float | bool | datetime | list[str] | None

HEADER_SCAN_ROWS = 20
MIN_HEADER_CELLS = 2
COLUMN_NAME_MAX = 100
BLANK_COLUMN = "Column {}"
WHITESPACE_RUN = re.compile(r"\s+")
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True)
class ParsedRow:
    """One data row of an uploaded file: its cells, or a row-level error (never both)."""

    row_no: int
    cells: tuple[Cell, ...] | None
    error: RowError | None


def cell_text(cell: Cell) -> str:
    """Render a cell as trimmed text (integral floats lose their ".0").

    Args:
        cell: Cell value.

    Returns:
        The text ("" for None).
    """
    if cell is None:
        return ""
    if isinstance(cell, float) and cell.is_integer():
        return str(int(cell))
    if isinstance(cell, list):
        return ", ".join(cell)
    if isinstance(cell, datetime):
        return cell.isoformat()
    return str(cell).strip()


def is_filled(cell: Cell) -> bool:
    """Tell whether a cell holds a value.

    Args:
        cell: Cell value.

    Returns:
        True unless it is None, blank text or an empty list.
    """
    return bool(cell_text(cell))


def find_header(rows: Sequence[Sequence[Cell]]) -> int | None:
    """Find the header row.

    Args:
        rows: The first rows of the sheet.

    Returns:
        Index of the first row with at least MIN_HEADER_CELLS filled cells within HEADER_SCAN_ROWS, or None.
    """
    for index, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        if sum(1 for cell in row if is_filled(cell)) >= MIN_HEADER_CELLS:
            return index
    return None


def column_names(cells: Sequence[Cell]) -> tuple[str, ...]:
    """Name every column of the header row uniquely.

    Args:
        cells: Header row.

    Returns:
        One unique, non-empty name per cell.
    """
    names: list[str] = []
    taken: set[str] = set()
    for index, cell in enumerate(cells):
        text = WHITESPACE_RUN.sub(" ", CONTROL_CHARS.sub(" ", cell_text(cell))).strip()
        base = text[:COLUMN_NAME_MAX].strip() or BLANK_COLUMN.format(index + 1)
        name, copy = base, 1
        while name.lower() in taken:
            copy += 1
            name = f"{base} {copy}"
        taken.add(name.lower())
        names.append(name)
    return tuple(names)


def trim_trailing(cells: Sequence[Cell]) -> list[Cell]:
    """Drop empty cells at the end of a row (spreadsheets pad rows to the widest one).

    Args:
        cells: Row.

    Returns:
        The row without trailing empty cells.
    """
    trimmed = list(cells)
    while trimmed and not is_filled(trimmed[-1]):
        trimmed.pop()
    return trimmed


def as_map(value: Any) -> dict[str, Any]:
    """Read a stored sub-document as a mapping.

    Args:
        value: Stored value.

    Returns:
        The mapping, or an empty one when the value is not a mapping.
    """
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    """Read a stored array.

    Args:
        value: Stored value.

    Returns:
        The list, or an empty one when the value is not a list.
    """
    return cast(list[Any], value) if isinstance(value, list) else []
