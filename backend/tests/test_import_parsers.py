"""Import file handling without HTTP: type sniffing, CSV/XLSX/vCard parsing, header detection and size guards."""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime
from typing import Any

import pytest
from importkit import fixture_bytes, xlsx_bytes
from openpyxl import Workbook
from openpyxl.utils.datetime import CALENDAR_MAC_1904

from manceps_api.imports import coerce, mapping, parsers, sniff, vcard, xlsx
from manceps_api.imports.errors import ImportFileError
from manceps_api.imports.parsers import ParsedFile, ParsedRow
from manceps_api.imports.sniff import FileType

MAX_ROWS = 20_000


def _parse(file_type: FileType, content: bytes, max_rows: int = MAX_ROWS) -> tuple[ParsedFile, list[ParsedRow]]:
    """Parse bytes and drain the rows.

    Args:
        file_type: csv, xlsx or vcf.
        content: File bytes.
        max_rows: Row cap.

    Returns:
        The parsed file and its rows.
    """
    parsed = parsers.parse_file(file_type, io.BytesIO(content), max_rows)
    return parsed, list(parsed.rows)


def _cells(parsed: ParsedFile, row: ParsedRow) -> dict[str, Any]:
    """Pair a row's cells with the column names.

    Args:
        parsed: Parsed file.
        row: One row.

    Returns:
        Column to value.
    """
    assert row.cells is not None, row.error
    return dict(zip(parsed.columns, row.cells, strict=True))


def test_sniff_by_extension_and_magic() -> None:
    assert sniff.detect_type("roster.CSV", io.BytesIO(b"a,b\n1,2\n")) == "csv"
    assert sniff.detect_type("people.vcf", io.BytesIO(b"\r\n\xef\xbb\xbfbegin:vcard\r\n")) == "vcf"
    assert sniff.detect_type("loads.xlsx", io.BytesIO(fixture_bytes("loads.xlsx"))) == "xlsx"
    refusals = [("loads.xlsx", b"a,b\n"), ("roster.csv", fixture_bytes("loads.xlsx")), ("roster.csv", b"a\x00b"),
                ("people.vcf", b"FN:x\n"), ("payload.exe", b"MZ"), ("noext", b"a,b"),
                ("fake.xlsx", _zip_without_workbook())]
    for name, content in refusals:
        with pytest.raises(ImportFileError) as caught:
            sniff.detect_type(name, io.BytesIO(content))
        assert caught.value.status_code == 415, name


def _zip_without_workbook() -> bytes:
    """Build a zip that is not a workbook.

    Returns:
        Zip bytes.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<x/>")
    return buffer.getvalue()


@pytest.mark.parametrize(("raw", "clean"), [
    ("../../etc/passwd", "passwd"), ("C:\\Users\\me\\roster (1).csv", "roster_1.csv"),
    ("..hidden.csv", "hidden.csv"), ("", "upload"), ("\x00\x1f.csv", "upload.csv"), ("名单.csv", "upload.csv"),
    ("a" * 300 + ".csv", "a" * 116 + ".csv"),
])
def test_sanitize_filename(raw: str, clean: str) -> None:
    assert sniff.sanitize_filename(raw) == clean


def test_carriers_csv_fixture() -> None:
    parsed, rows = _parse("csv", fixture_bytes("carriers.csv"))
    assert parsed.columns[:4] == ("Carrier Name", "Company", "MC#", "Phone") and parsed.header_row == 1
    assert [row.row_no for row in rows] == [2, 3, 4, 5, 6]
    assert _cells(parsed, rows[0])["Equipment"] == "dry_van, reefer"
    suggested = mapping.suggest_mapping("carriers", parsed.columns)
    assert suggested == {"Carrier Name": "name", "Company": "company", "MC#": "mc_number", "Phone": "phone",
                         "Email": "email", "Equipment": "equipment", "Home Base": "home_base", "SMS Consent": None}
    assert mapping.consent_columns(parsed.columns) == ["SMS Consent"]


def test_messy_csv_fixture() -> None:
    parsed, rows = _parse("csv", fixture_bytes("carriers_messy.csv"))
    assert parsed.header_row == 3
    assert parsed.columns == ("Contact", "Cell", "Docket", "Company Name", "E-mail", "Trailer Type", "Notes")
    assert [row.row_no for row in rows] == [4, 5, 7, 8, 9, 10]
    first = _cells(parsed, rows[0])
    assert first["Notes"] == "Runs I-10, prefers\nnight loads" and first["Cell"] == "(469) 555-0120"
    suggested = mapping.suggest_mapping("carriers", parsed.columns)
    assert suggested["Cell"] == "phone" and suggested["Docket"] == "mc_number" and suggested["Contact"] == "name"
    assert suggested["Trailer Type"] == "equipment" and suggested["E-mail"] == "email"


def test_semicolon_and_tab_delimiters() -> None:
    for delimiter in (";", "\t", "|"):
        content = f"Name{delimiter}Phone\nA{delimiter}2145550100\n".encode()
        parsed, rows = _parse("csv", content)
        assert parsed.columns == ("Name", "Phone"), delimiter
        assert rows[0].cells == ("A", "2145550100")


def test_csv_row_level_errors_never_stop_the_file() -> None:
    huge = "x" * (parsers.MAX_CELL_CHARS + 1)
    content = f"Name,Phone\nok,1\n\"{huge}\",2\nextra,3,surprise\nfine,4,\n".encode()
    _parsed, rows = _parse("csv", content)
    assert [row.error.code if row.error else None for row in rows] == [None, "cell_too_long", "unexpected_cells",
                                                                       None]
    giant = "a,b\n\"" + "y" * 200_000 + "\",1\nc,d\n"
    _parsed, rows = _parse("csv", giant.encode())
    assert [row.error.code if row.error else row.cells for row in rows] == ["malformed_row", ("c", "d")]


def test_csv_latin1_bytes_are_decoded() -> None:
    _parsed, rows = _parse("csv", "Name,City\nJos\xe9,Mont\xe9rrey\n".encode("cp1252"))
    assert rows[0].cells == ("José", "Montérrey")


def test_header_detection_rules() -> None:
    with pytest.raises(ImportFileError) as caught:
        _parse("csv", b"only one column\nvalue\n")
    assert caught.value.code == "no_header"
    with pytest.raises(ImportFileError) as caught:
        _parse("csv", b"")
    assert caught.value.code == "no_header"
    wide = ",".join(f"c{index}" for index in range(parsers.MAX_COLUMNS + 1)).encode()
    with pytest.raises(ImportFileError) as caught:
        _parse("csv", wide + b"\n")
    assert caught.value.code == "too_many_columns"
    parsed, _rows = _parse("csv", b"Phone,,Phone,phone\n1,2,3,4\n")
    assert parsed.columns == ("Phone", "Column 2", "Phone 2", "phone 3")


class EndlessRows(io.RawIOBase):
    """A file that never ends: proves the row cap stops reading instead of parsing everything."""

    def __init__(self) -> None:
        """Start before the header."""
        self.sent = 0
        self.header_sent = False

    def readable(self) -> bool:
        """Report readability.

        Returns:
            True.
        """
        return True

    def readinto(self, buffer: Any) -> int:
        """Fill the buffer with the header, then rows forever.

        Args:
            buffer: Writable buffer.

        Returns:
            Bytes written.
        """
        chunk = b"Name,Phone\n" if not self.header_sent else b"carrier,2145550100\n" * 64
        self.header_sent = True
        self.sent += len(chunk)
        view = memoryview(buffer)
        view[:len(chunk)] = chunk
        return len(chunk)


def test_row_cap_stops_streaming_before_the_end() -> None:
    stream = EndlessRows()
    parsed = parsers.parse_file("csv", io.BufferedReader(stream), 100)
    seen = 0
    with pytest.raises(ImportFileError) as caught:
        for _row in parsed.rows:
            seen += 1
    assert caught.value.code == "too_many_rows" and caught.value.status_code == 422
    assert seen == 100 and stream.sent < 1_000_000


def test_loads_xlsx_fixture_merged_headers_serial_dates_float_phones() -> None:
    parsed, rows = _parse("xlsx", fixture_bytes("loads.xlsx"))
    assert parsed.header_row == 2
    assert parsed.columns == ("Load #", "Broker MC", "Pickup", "Pickup 2", "Delivery Date", "Driver Phone", "Rate")
    first = _cells(parsed, rows[0])
    assert coerce.coerce("date", first["Pickup"], parsed.epoch) == datetime(2026, 12, 1, tzinfo=UTC)
    assert coerce.coerce("date", first["Delivery Date"], parsed.epoch) == datetime(2026, 12, 3, 12, tzinfo=UTC)
    assert coerce.coerce("phone", first["Driver Phone"], parsed.epoch) == "2145550199"
    assert coerce.coerce("digits", first["Broker MC"], parsed.epoch) == "123456"
    assert first["Pickup 2"] == "Dallas, TX" and len(rows) == 3


def test_xlsx_1904_epoch_and_formatted_dates() -> None:
    workbook = Workbook()
    workbook.epoch = CALENDAR_MAC_1904
    sheet = workbook.active
    assert sheet is not None
    sheet.append(["Name", "Expires", "Formatted"])
    sheet.append(["A", 46357, datetime(2027, 1, 2)])
    buffer = io.BytesIO()
    workbook.save(buffer)
    parsed, rows = _parse("xlsx", buffer.getvalue())
    cells = _cells(parsed, rows[0])
    assert coerce.coerce("date", cells["Expires"], parsed.epoch) == datetime(2030, 12, 2, tzinfo=UTC)
    assert coerce.coerce("date", cells["Formatted"], parsed.epoch) == datetime(2027, 1, 2, tzinfo=UTC)


def test_xlsx_zip_bomb_is_refused_before_parsing() -> None:
    buffer = io.BytesIO(xlsx_bytes([["Name", "Phone"], ["a", "b"]]))
    with zipfile.ZipFile(buffer, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/media/bomb.bin", b"\0" * (xlsx.MAX_UNCOMPRESSED_BYTES + 1))
    assert len(buffer.getvalue()) < xlsx.MAX_UNCOMPRESSED_BYTES // 100
    with pytest.raises(ImportFileError) as caught:
        _parse("xlsx", buffer.getvalue())
    assert caught.value.code == "archive_too_large" and caught.value.status_code == 413


def test_xlsx_corrupt_archive_is_422() -> None:
    content = xlsx_bytes([["Name", "Phone"], ["a", "b"]])
    with pytest.raises(ImportFileError) as caught:
        _parse("xlsx", content[: len(content) // 2])
    assert caught.value.status_code == 422


def test_vcard_fixture_three_phones_first_mobile() -> None:
    parsed, rows = _parse("vcf", fixture_bytes("contacts.vcf"))
    assert parsed.columns == vcard.VCARD_COLUMNS
    cards = [_cells(parsed, row) for row in rows]
    assert [card["Full name"] for card in cards] == ["Ana Rivera", "Ben Okafor", "Dana Chen"]
    assert [card["Mobile phone"] for card in cards] == ["(214) 555-0131", "+1-214-555-0140", "2145550152"]
    assert cards[0]["Other phones"] == ["(214) 555-0130", "214-555-0132"]
    assert cards[1]["Emails"] == ["ben@northline.example", "dispatch@northline.example"]
    assert cards[0]["Organization"] == "Summit Brokerage"
    assert cards[2]["Title"] == "Night dispatcher with a very long title that is folded across two lines"


def test_vcard_malformed_cards_are_row_errors() -> None:
    text = ("BEGIN:VCARD\nFN:Good\nTEL:2145550100\nEND:VCARD\n"
            "BEGIN:VCARD\nFN:No end\n"
            "BEGIN:VCARD\nthis line has no colon\nEND:VCARD\n"
            "stray text\n"
            "BEGIN:VCARD\nN:Last;First\nEND:VCARD\n")
    _parsed, rows = _parse("vcf", ("BEGIN:VCARD\nFN:x\nEND:VCARD\n" + text).encode())
    codes = [row.error.code if row.error else None for row in rows]
    assert codes == [None, None, "malformed_card", "malformed_line", "outside_card", None]
    assert rows[-1].cells is not None and rows[-1].cells[0] == "First Last"


def test_vcard_unescape_and_params() -> None:
    assert vcard.unescape("a\\,b\\;c\\nd\\\\e") == "a,b;c\nd\\e"
    line = vcard.parse_line('item1.TEL;TYPE="voice,CELL";PREF=1:tel:+1-214-555-0100')
    assert line is not None
    assert line.name == "TEL" and line.types == frozenset({"voice", "cell"}) and line.value == "tel:+1-214-555-0100"
    legacy = vcard.parse_line("TEL;CELL;VOICE:2145550100")
    assert legacy is not None and legacy.types == frozenset({"cell", "voice"})
    assert vcard.parse_line("no colon here") is None


def test_coerce_rules() -> None:
    epoch = None
    assert coerce.coerce("phone", 2145550199.0, epoch) == "2145550199"
    assert coerce.coerce("phone", 2145550199, epoch) == "2145550199"
    assert coerce.coerce("number", "$2,500.50", epoch) == 2500.5
    assert coerce.coerce("number", "12%", epoch) == 12.0
    assert coerce.coerce("bool", "Yes", epoch) is True and coerce.coerce("bool", "n", epoch) is False
    assert coerce.coerce("date", "2026-11-30", epoch) == datetime(2026, 11, 30, tzinfo=UTC)
    assert coerce.coerce("date", "11/30/2026", epoch) == datetime(2026, 11, 30, tzinfo=UTC)
    assert coerce.coerce("list", "Dry Van; Power-Only | flatbed / step deck", epoch) == [
        "Dry Van", "Power-Only", "flatbed", "step deck"]
    assert coerce.coerce("slug_list", "Dry Van; Power-Only", epoch) == ["dry_van", "power_only"]
    assert coerce.coerce("list", "a ::: b", epoch) == ["a", "b"]
    assert coerce.coerce("text", 12.0, epoch) == "12" and coerce.coerce("text", "  ", epoch) is None
    for kind, value in (("number", "abc"), ("bool", "maybe"), ("date", "31/31/2026"), ("number", "nan")):
        with pytest.raises(coerce.CoerceError):
            coerce.coerce(kind, value, epoch)


def test_google_contacts_fixture_suggestion() -> None:
    parsed, rows = _parse("csv", fixture_bytes("google_contacts.csv"))
    suggested = mapping.suggest_mapping("contacts", parsed.columns)
    assert suggested["First Name"] == "first_name" and suggested["Last Name"] == "last_name"
    assert suggested["Organization Name"] == "company" and suggested["Organization Title"] == "title"
    assert suggested["E-mail 1 - Value"] == "emails" and suggested["E-mail 2 - Value"] == "emails"
    assert suggested["Phone 1 - Value"] == "phones" and suggested["Phone 2 - Value"] == "phones"
    assert suggested["Phone 1 - Label"] is None and suggested["Labels"] is None
    assert mapping.is_google_contacts(parsed.columns) and len(rows) == 3
