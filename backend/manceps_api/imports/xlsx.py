"""XLSX reading: zip-bomb guard, openpyxl read-only streaming of the first sheet, and its merged-cell ranges.

openpyxl's read-only mode does not expose merged cells, so the first sheet's `<mergeCell ref=...>` elements are read
with a streaming, entity-safe XML parser (defusedxml). The archive's declared uncompressed sizes are summed before
anything is decompressed; zipfile never inflates an entry past its declared size, so the sum is a hard bound.
"""

from __future__ import annotations

import zipfile
from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, BinaryIO
from xml.etree.ElementTree import ParseError

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import iterparse
from openpyxl import load_workbook
from openpyxl.utils.cell import range_boundaries
from openpyxl.utils.exceptions import InvalidFileException

from .errors import PAYLOAD_TOO_LARGE, UNPROCESSABLE, ImportFileError, RowError
from .header import Cell

MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_ENTRIES = 10_000
INT64_MAX = 2**63 - 1
MERGE_TAG = "mergeCell"
SHEET_PATH_ATTRIBUTE = "_worksheet_path"
WORKBOOK_ERRORS = (InvalidFileException, zipfile.BadZipFile, KeyError, IndexError, ValueError, TypeError,
                   AttributeError, OSError, EOFError, ParseError, DefusedXmlException)

Merge = tuple[int, int, int, int]
Record = tuple[int, list[Cell] | None, RowError | None]


def check_archive(stream: BinaryIO) -> None:
    """Refuse archives that would inflate past MAX_UNCOMPRESSED_BYTES or hold too many entries; leave it rewound.

    Args:
        stream: Seekable XLSX file.

    Raises:
        ImportFileError: 413 archive_too_large, or 422 invalid_workbook when it is not a readable zip.
    """
    try:
        with zipfile.ZipFile(stream) as archive:
            entries = archive.infolist()
    except (zipfile.BadZipFile, OSError, ValueError, EOFError) as exc:
        raise ImportFileError(UNPROCESSABLE, "invalid_workbook", "the workbook cannot be read") from exc
    finally:
        stream.seek(0)
    if len(entries) > MAX_ENTRIES or sum(entry.file_size for entry in entries) > MAX_UNCOMPRESSED_BYTES:
        raise ImportFileError(PAYLOAD_TOO_LARGE, "archive_too_large", "the workbook expands to more data than allowed")


def _local_name(tag: str) -> str:
    """Strip an XML namespace.

    Args:
        tag: Tag like "{ns}mergeCell".

    Returns:
        The local name.
    """
    return tag.rsplit("}", 1)[-1]


def read_merges(stream: BinaryIO, sheet_path: str) -> list[Merge]:
    """Read a sheet's merged ranges with a streaming parser (memory stays flat on large sheets).

    Args:
        stream: Seekable XLSX file.
        sheet_path: Archive path of the sheet XML.

    Returns:
        (min_col, min_row, max_col, max_row) per merged range.

    Raises:
        ImportFileError: 422 invalid_workbook on malformed XML.
    """
    merges: list[Merge] = []
    try:
        with zipfile.ZipFile(stream) as archive, archive.open(sheet_path.lstrip("/")) as sheet:
            for _event, element in iterparse(sheet, events=("end",)):
                if _local_name(element.tag) == MERGE_TAG and element.get("ref"):
                    bounds = range_boundaries(str(element.get("ref")))
                    if None not in bounds:
                        merges.append((int(bounds[0] or 0), int(bounds[1] or 0), int(bounds[2] or 0),
                                       int(bounds[3] or 0)))
                element.clear()
    except WORKBOOK_ERRORS as exc:
        raise ImportFileError(UNPROCESSABLE, "invalid_workbook", "the workbook cannot be read") from exc
    finally:
        stream.seek(0)
    return merges


def fill_merged(row_no: int, cells: list[Cell], merges: list[Merge]) -> list[Cell]:
    """Copy each merged range's top-left value into the range's other cells on one row.

    Args:
        row_no: 1-based sheet row.
        cells: The row's values.
        merges: Merged ranges.

    Returns:
        The row with merged cells forward-filled.
    """
    filled = list(cells)
    for min_col, min_row, max_col, max_row in merges:
        if not min_row <= row_no <= max_row or min_col > len(filled):
            continue
        source = filled[min_col - 1] if min_row == row_no else None
        if source is None:
            continue
        for column in range(min_col, min(max_col, len(filled)) + 1):
            filled[column - 1] = source
    return filled


def clean_cell(value: Any) -> Cell:
    """Make an openpyxl value storable: aware datetimes, text for times and huge integers.

    Args:
        value: Value from openpyxl.

    Returns:
        The cell.
    """
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if isinstance(value, time | timedelta):
        return str(value)
    if isinstance(value, bool | float | str) or value is None:
        return value
    if isinstance(value, int):
        return value if abs(value) <= INT64_MAX else str(value)
    return str(value)


def open_sheet(stream: BinaryIO) -> tuple[Iterator[Record], datetime, list[Merge]]:
    """Open the first sheet in read-only mode.

    Args:
        stream: Seekable XLSX file (already sniffed).

    Returns:
        (row records, workbook epoch, merged ranges).

    Raises:
        ImportFileError: 413 archive_too_large or 422 invalid_workbook.
    """
    check_archive(stream)
    try:
        workbook = load_workbook(stream, read_only=True, data_only=True)
        sheet = workbook.worksheets[0]
    except WORKBOOK_ERRORS as exc:
        raise ImportFileError(UNPROCESSABLE, "invalid_workbook", "the workbook cannot be read") from exc
    path = getattr(sheet, SHEET_PATH_ATTRIBUTE, None)
    merges = read_merges(stream, path) if isinstance(path, str) else []
    return _records(workbook, sheet), workbook.epoch, merges


def _records(workbook: Any, sheet: Any) -> Iterator[Record]:
    """Stream the sheet's rows, closing the workbook at the end.

    Args:
        workbook: Read-only workbook.
        sheet: Its first sheet.

    Yields:
        (row number, cells, None).

    Raises:
        ImportFileError: 422 invalid_workbook when the sheet XML breaks mid-way.
    """
    try:
        for row_no, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            yield row_no, [clean_cell(value) for value in row], None
    except WORKBOOK_ERRORS as exc:
        raise ImportFileError(UNPROCESSABLE, "invalid_workbook", "the workbook cannot be read") from exc
    finally:
        workbook.close()
