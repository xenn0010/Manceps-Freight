"""Property-based tests (Hypothesis) for import parsing, header detection, mapping suggestions and natural keys.

No input may crash a parser: a file either parses into rows (each a cell tuple or a row-level error) or is refused
with an ImportFileError; nothing else escapes.
"""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from importkit import xlsx_bytes

from manceps_api.imports import coerce, header, mapping, parsers, schema, vcard
from manceps_api.imports.errors import ImportFileError
from manceps_api.imports.parsers import ParsedRow
from manceps_api.imports.sniff import FileType

EXAMPLES = 200
SLOW_EXAMPLES = 40
MAX_ROWS = 50
SURROGATE_LOW = 0xD800
SURROGATE_HIGH = 0xDFFF
WORKBOOK_PART = "xl/workbook.xml"
CELL_TEXT = st.text(max_size=12)
CELLS = st.one_of(st.none(), CELL_TEXT, st.integers(min_value=-10**12, max_value=10**12),
                  st.floats(allow_nan=False, allow_infinity=False, width=32), st.booleans())
CSV_ALPHABET = st.sampled_from(list("ab1,;\t|\"' \n\r=+-@é\x00"))


def _drain(file_type: FileType, content: bytes) -> list[ParsedRow] | None:
    """Parse bytes, returning rows, or None when the file was refused as a whole.

    Args:
        file_type: csv, xlsx or vcf.
        content: Bytes.

    Returns:
        Rows, or None on ImportFileError.
    """
    try:
        parsed = parsers.parse_file(file_type, io.BytesIO(content), MAX_ROWS)
        rows = list(parsed.rows)
    except ImportFileError:
        return None
    assert len(set(parsed.columns)) == len(parsed.columns) and all(parsed.columns)
    for row in rows:
        assert (row.cells is None) != (row.error is None)
        assert row.cells is None or len(row.cells) == len(parsed.columns)
    return rows


@settings(max_examples=EXAMPLES)
@given(st.text(alphabet=CSV_ALPHABET, max_size=300))
def test_csv_parser_never_crashes(text: str) -> None:
    _drain("csv", text.encode("utf-8"))


@settings(max_examples=EXAMPLES)
@given(st.binary(max_size=300))
def test_csv_parser_survives_arbitrary_bytes(content: bytes) -> None:
    _drain("csv", content)


@settings(max_examples=EXAMPLES)
@given(st.lists(st.lists(CELL_TEXT, min_size=1, max_size=6), min_size=1, max_size=8))
def test_csv_round_trips_well_formed_rows(rows: list[list[str]]) -> None:
    buffer = io.StringIO()
    csv.writer(buffer).writerows([["h1", "h2", "h3", "h4", "h5", "h6"], *rows])
    parsed = _drain("csv", buffer.getvalue().encode("utf-8"))
    assert parsed is not None


@settings(max_examples=EXAMPLES)
@given(st.text(max_size=400))
def test_vcard_reader_never_crashes(text: str) -> None:
    rows = list(vcard.read_cards(io.StringIO("BEGIN:VCARD\n" + text).readlines(), MAX_ROWS))
    for row in rows:
        assert (row.cells is None) != (row.error is None)
        assert row.cells is None or len(row.cells) == len(vcard.VCARD_COLUMNS)


@settings(max_examples=EXAMPLES)
@given(st.lists(st.sampled_from(["BEGIN:VCARD", "END:VCARD", "FN:A", "TEL;TYPE=cell:2145550100", " folded",
                                 "EMAIL:a@b.example", "N:x;y", "garbage", "", "TEL;;;:", "ORG:;;", "item1.TEL:1"]),
                max_size=30))
def test_vcard_structured_noise(lines: list[str]) -> None:
    _drain("vcf", ("BEGIN:VCARD\n" + "\n".join(lines)).encode("utf-8"))


@settings(max_examples=SLOW_EXAMPLES, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(st.lists(CELLS, max_size=5), min_size=1, max_size=6))
def test_xlsx_parser_reads_generated_workbooks(rows: list[list[Any]]) -> None:
    clean = [[_xlsx_safe(cell) for cell in row] for row in rows]
    _drain("xlsx", xlsx_bytes(clean))


def _xlsx_safe(cell: Any) -> Any:
    """Drop characters an XLSX file cannot hold (control characters).

    Args:
        cell: Cell value.

    Returns:
        A value openpyxl can write.
    """
    if isinstance(cell, str):
        return "".join(char for char in cell if char >= " " and char not in "𐏿") or None
    return cell


@settings(max_examples=EXAMPLES)
@given(st.binary(max_size=200))
def test_xlsx_parser_refuses_garbage(content: bytes) -> None:
    assert _drain("xlsx", b"PK\x03\x04" + content) is None


@settings(max_examples=SLOW_EXAMPLES)
@given(st.dictionaries(st.text(min_size=1, max_size=20), st.binary(max_size=50), max_size=4))
def test_xlsx_parser_refuses_arbitrary_zips(entries: dict[str, bytes]) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries.items():
            if name != WORKBOOK_PART:
                archive.writestr(name, data)
        archive.writestr(WORKBOOK_PART, b"<not-a-workbook")
    assert _drain("xlsx", buffer.getvalue()) is None


@settings(max_examples=EXAMPLES)
@given(st.lists(st.lists(CELLS, max_size=8), max_size=25))
def test_header_detection(rows: list[list[Any]]) -> None:
    found = header.find_header(rows)
    if found is None:
        assert all(sum(1 for cell in row if header.is_filled(cell)) < header.MIN_HEADER_CELLS
                   for row in rows[: header.HEADER_SCAN_ROWS])
        return
    assert sum(1 for cell in rows[found] if header.is_filled(cell)) >= header.MIN_HEADER_CELLS
    names = header.column_names(rows[found])
    assert len(names) == len(rows[found]) and len({name.lower() for name in names}) == len(names)
    assert all(name and name == name.strip() for name in names)


@settings(max_examples=EXAMPLES)
@given(st.sampled_from(schema.ENTITIES), st.lists(st.text(max_size=30), max_size=30, unique=True))
def test_mapping_suggestion(entity: str, columns: list[str]) -> None:
    suggested = mapping.suggest_mapping(entity, columns)
    assert list(suggested) == columns
    targets = [field for field in suggested.values() if field is not None]
    spec = schema.ENTITY_SPECS[entity]
    assert all(field in spec.fields for field in targets)
    scalar = [field for field in targets if not spec.fields[field].is_list]
    assert len(scalar) == len(set(scalar))
    assert not set(targets) & mapping.CONSENT_TARGETS


@settings(max_examples=EXAMPLES)
@given(st.text(max_size=40))
def test_header_normalization_is_stable(text: str) -> None:
    once = mapping.normalize_header(text)
    assert once == mapping.normalize_header(once) and once.isascii() and once == once.lower()


@settings(max_examples=EXAMPLES)
@given(st.sampled_from(["phone", "mc", "email"]), st.one_of(st.text(max_size=30), st.integers(), st.floats()))
def test_natural_key_normalization(kind: str, raw: Any) -> None:
    key = schema.normalize_key(kind, raw)
    if key is None:
        return
    assert key == schema.normalize_key(kind, key)
    if kind == "phone":
        assert key.startswith("+1") and len(key) == 12 and key[1:].isdigit()
    elif kind == "mc":
        assert key.isdigit() and key.isascii()
    else:
        assert key == key.lower() and "@" in key


@settings(max_examples=EXAMPLES)
@given(st.sampled_from(sorted(coerce.KINDS)), st.one_of(CELLS, st.datetimes(), st.lists(CELL_TEXT, max_size=3)))
def test_coercion_never_crashes(kind: str, value: Any) -> None:
    try:
        result = coerce.coerce(kind, value, datetime(1899, 12, 30))
    except coerce.CoerceError:
        return
    if kind == "date":
        assert result is None or result.tzinfo is not None
