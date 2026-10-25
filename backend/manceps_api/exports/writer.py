"""Spreadsheet output that is safe to open: formula-injection escaping, CSV and XLSX writers, safe file names.

A cell whose text starts with `=`, `+`, `-`, `@`, a tab or a carriage return could run as a formula in Excel, Sheets
or LibreOffice, so it is written with a leading single quote (OWASP CSV injection guidance). The same escaping is
applied to every exported value, including import reports.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
ESCAPE_PREFIX = "'"
TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
HEADER_UNSAFE = re.compile(r'[^A-Za-z0-9._ -]+')
SHEET_TITLE = "Export"


def escape_cell(value: Any) -> Any:
    """Neutralize spreadsheet formulas in text cells.

    Args:
        value: Cell value.

    Returns:
        The value, with a leading quote when it is text starting with a formula character.
    """
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return ESCAPE_PREFIX + value
    return value


def render_value(value: Any) -> Any:
    """Turn a stored value into a spreadsheet cell (lists joined, datetimes in ISO 8601, ids as text).

    Args:
        value: Stored value.

    Returns:
        A str, number, bool or None, escaped.
    """
    if isinstance(value, list):
        rendered = "; ".join(str(render_value(item)) for item in value)  # pyright: ignore[reportUnknownVariableType]
        return escape_cell(rendered)
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, bool | int | float):
        return value
    return escape_cell(str(value))


def write_csv(path: Path, header: Sequence[str], rows: Iterable[Sequence[Any]]) -> int:
    """Write a UTF-8 CSV file (with BOM, so Excel reads accents correctly).

    Args:
        path: Target file.
        header: Column names.
        rows: Rows of values (escaped here).

    Returns:
        Number of data rows.
    """
    count = 0
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([render_value(name) for name in header])
        for row in rows:
            writer.writerow([render_value(value) for value in row])
            count += 1
    return count


def write_xlsx(path: Path, header: Sequence[str], rows: Iterable[Sequence[Any]]) -> int:
    """Write an XLSX file in streaming (write-only) mode.

    Args:
        path: Target file.
        header: Column names.
        rows: Rows of values (escaped here; a quoted cell stays text, never a formula).

    Returns:
        Number of data rows.
    """
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet(SHEET_TITLE)
    sheet.append([render_value(name) for name in header])
    count = 0
    for row in rows:
        sheet.append([render_value(value) for value in row])
        count += 1
    workbook.save(str(path))
    return count


def csv_lines(rows: Iterable[Sequence[Any]]) -> str:
    """Render escaped CSV rows in memory (one chunk of a streamed report).

    Args:
        rows: Rows.

    Returns:
        CSV text.
    """
    buffer = io.StringIO()
    csv.writer(buffer).writerows([render_value(value) for value in row] for row in rows)
    return buffer.getvalue()


def csv_text(header: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    """Render an escaped CSV document with a header row in memory (templates, small reports).

    Args:
        header: Column names.
        rows: Rows.

    Returns:
        CSV text.
    """
    return csv_lines([header, *rows])


def export_filename(entity: str, file_format: str, now: datetime) -> str:
    """Name an export file from fixed parts only (never from user input).

    Args:
        entity: Entity name.
        file_format: csv or xlsx.
        now: Creation time.

    Returns:
        Name like carriers-20261025-120000.csv.
    """
    return f"{entity}-{now.strftime(TIMESTAMP_FORMAT)}.{file_format}"


def content_disposition(filename: str) -> str:
    """Build an attachment header with a sanitized name (no quotes, CR, LF or non-ASCII).

    Args:
        filename: Proposed name.

    Returns:
        The header value.
    """
    return f'attachment; filename="{HEADER_UNSAFE.sub("_", filename)}"'
