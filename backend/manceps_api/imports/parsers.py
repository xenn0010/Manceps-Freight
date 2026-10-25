"""Row readers for uploaded files: CSV (encoding and delimiter sniffed), XLSX (first sheet) and vCard.

Everything streams: rows are produced one at a time and the row cap stops reading at the first row past it, so an
oversized file is refused before it is fully parsed. A malformed row becomes a row-level error and reading goes on;
only problems with the file as a whole (no header, too many columns or rows, unreadable workbook) raise.
"""

from __future__ import annotations

import codecs
import csv
import io
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, BinaryIO

from . import vcard, xlsx
from .errors import UNPROCESSABLE, ImportFileError, RowError
from .header import HEADER_SCAN_ROWS, Cell, ParsedRow, column_names, find_header, trim_trailing
from .sniff import FileType

__all__ = ["MAX_CELL_CHARS", "MAX_COLUMNS", "ParsedFile", "ParsedRow", "parse_file"]

SNIFF_BYTES = 64 * 1024
MAX_CELL_CHARS = 10_000
MAX_COLUMNS = 200
MAX_CONSECUTIVE_BAD_ROWS = 1_000
DELIMITERS = (",", ";", "\t", "|")
DELIMITER_SAMPLE_LINES = 20
UTF8 = "utf-8-sig"
FALLBACK_ENCODING = "cp1252"

Record = tuple[int, list[Cell] | None, RowError | None]
HeaderFill = Callable[[int, list[Cell]], list[Cell]]


@dataclass(frozen=True)
class ParsedFile:
    """A parsed upload: its columns and a lazy stream of data rows."""

    file_type: FileType
    columns: tuple[str, ...]
    header_row: int
    epoch: datetime | None
    rows: Iterator[ParsedRow]


class _Rejoined(io.RawIOBase):
    """Bytes already read (the sniffed head) followed by the rest of a stream; works on non-seekable input."""

    def __init__(self, head: bytes, rest: BinaryIO) -> None:
        """Join the parts.

        Args:
            head: Bytes read first.
            rest: The stream they came from.
        """
        super().__init__()
        self._head = head
        self._rest = rest

    def readable(self) -> bool:
        """Report readability.

        Returns:
            True.
        """
        return True

    def readinto(self, buffer: Any) -> int:
        """Fill a buffer from the head, then from the stream.

        Args:
            buffer: Writable buffer.

        Returns:
            Bytes written (0 at the end).
        """
        view = memoryview(buffer).cast("B")
        if self._head:
            size = min(len(view), len(self._head))
            view[:size], self._head = self._head[:size], self._head[size:]
            return size
        chunk = self._rest.read(len(view))
        view[: len(chunk)] = chunk
        return len(chunk)


def _encoding(head: bytes) -> str:
    """Pick UTF-8 when the head decodes as UTF-8 (a cut multibyte tail is fine), else Windows-1252.

    Args:
        head: First bytes.

    Returns:
        Codec name.
    """
    try:
        codecs.getincrementaldecoder("utf-8")().decode(head, final=False)
    except UnicodeDecodeError:
        return FALLBACK_ENCODING
    return UTF8


def _delimiter(sample: str) -> str:
    """Pick the delimiter used most across the first lines (comma on a tie).

    Args:
        sample: Decoded head of the file.

    Returns:
        The delimiter.
    """
    lines = [line for line in sample.splitlines() if line.strip()][:DELIMITER_SAMPLE_LINES]
    counts = {delimiter: sum(line.count(delimiter) for line in lines) for delimiter in DELIMITERS}
    best = max(DELIMITERS, key=lambda delimiter: counts[delimiter])
    return best if counts[best] > 0 else DELIMITERS[0]


def csv_records(stream: BinaryIO) -> Iterator[Record]:
    """Read CSV records; a record the csv module rejects becomes a row-level error.

    Args:
        stream: The file.

    Yields:
        (record number, cells or None, error or None).

    Raises:
        ImportFileError: 422 malformed_file after MAX_CONSECUTIVE_BAD_ROWS unreadable records in a row.
    """
    head = stream.read(SNIFF_BYTES)
    encoding = _encoding(head)
    text = io.TextIOWrapper(io.BufferedReader(_Rejoined(head, stream)), encoding=encoding, errors="replace",
                            newline="")
    reader = csv.reader(text, delimiter=_delimiter(head.decode(encoding, errors="replace")))
    record_no, bad_run = 0, 0
    while True:
        record_no += 1
        try:
            cells: list[Cell] = list(next(reader))
        except StopIteration:
            return
        except csv.Error:
            bad_run += 1
            if bad_run > MAX_CONSECUTIVE_BAD_ROWS:
                raise ImportFileError(UNPROCESSABLE, "malformed_file", "the file is not readable CSV") from None
            yield record_no, None, RowError("malformed_row", "this row could not be read as CSV")
            continue
        bad_run = 0
        yield record_no, cells, None


def _shape(record: Record, width: int) -> ParsedRow | None:
    """Fit a record to the header width, or turn it into a row-level error.

    Args:
        record: (number, cells, error).
        width: Number of columns.

    Returns:
        The row, or None for a blank row.
    """
    row_no, cells, error = record
    if cells is None:
        return ParsedRow(row_no, None, error)
    trimmed = trim_trailing(cells)
    if not trimmed:
        return None
    if len(trimmed) > width:
        return ParsedRow(row_no, None, RowError("unexpected_cells", "this row has values outside the header columns"))
    if any(isinstance(cell, str) and len(cell) > MAX_CELL_CHARS for cell in trimmed):
        return ParsedRow(row_no, None, RowError("cell_too_long", f"a cell is longer than {MAX_CELL_CHARS} characters"))
    return ParsedRow(row_no, tuple(trimmed + [None] * (width - len(trimmed))), None)


def _rows(records: Iterator[Record], width: int, max_rows: int) -> Iterator[ParsedRow]:
    """Yield shaped data rows, stopping at the first row past the cap.

    Args:
        records: Records after the header.
        width: Number of columns.
        max_rows: Row cap.

    Yields:
        Data rows (blank rows are skipped and not counted).

    Raises:
        ImportFileError: 422 too_many_rows.
    """
    count = 0
    for record in records:
        row = _shape(record, width)
        if row is None:
            continue
        count += 1
        if count > max_rows:
            raise ImportFileError(UNPROCESSABLE, "too_many_rows", f"the file has more than {max_rows} rows")
        yield row


def _with_header(file_type: FileType, records: Iterator[Record], max_rows: int, epoch: datetime | None,
                 fill: HeaderFill) -> ParsedFile:
    """Read records until the header (the first with two filled cells, within HEADER_SCAN_ROWS); the rest are data.

    Args:
        file_type: csv or xlsx.
        records: All records of the sheet.
        max_rows: Row cap.
        epoch: Workbook epoch, or None.
        fill: Fixes up the header row (merged-cell forward fill).

    Returns:
        The parsed file.

    Raises:
        ImportFileError: 422 no_header or too_many_columns.
    """
    scanned: list[list[Cell]] = []
    header: Record | None = None
    for record in records:
        scanned.append(record[1] or [])
        if find_header(scanned) is not None:
            header = record
            break
        if len(scanned) >= HEADER_SCAN_ROWS:
            break
    if header is None:
        raise ImportFileError(UNPROCESSABLE, "no_header", "no header row found (a row with at least two column names)")
    cells = trim_trailing(fill(header[0], list(header[1] or [])))
    if len(cells) > MAX_COLUMNS:
        raise ImportFileError(UNPROCESSABLE, "too_many_columns", f"the file has more than {MAX_COLUMNS} columns")
    columns = column_names(cells)
    return ParsedFile(file_type, columns, header[0], epoch, _rows(records, len(columns), max_rows))


def _no_fill(_row_no: int, cells: list[Cell]) -> list[Cell]:
    """Leave a header row unchanged (CSV has no merged cells).

    Args:
        _row_no: Row number.
        cells: Header cells.

    Returns:
        The cells.
    """
    return cells


def parse_file(file_type: FileType, stream: BinaryIO, max_rows: int) -> ParsedFile:
    """Parse an uploaded file lazily.

    Args:
        file_type: Type from sniff.detect_type.
        stream: The file (seekable for XLSX).
        max_rows: Row cap.

    Returns:
        Columns and a row stream; iterating the rows may raise ImportFileError (too_many_rows, invalid_workbook).

    Raises:
        ImportFileError: For file-level problems found before the first row.
    """
    if file_type == "vcf":
        text = io.TextIOWrapper(io.BufferedReader(_Rejoined(b"", stream)), encoding=UTF8, errors="replace",
                                newline="")
        return ParsedFile("vcf", vcard.VCARD_COLUMNS, 0, None, vcard.read_cards(text, max_rows))
    if file_type == "xlsx":
        records, epoch, merges = xlsx.open_sheet(stream)
        return _with_header("xlsx", records, max_rows, epoch,
                            lambda row_no, cells: xlsx.fill_merged(row_no, cells, merges))
    return _with_header("csv", csv_records(stream), max_rows, None, _no_fill)
