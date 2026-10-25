"""A small, streaming vCard reader (RFC 6350, plus the 2.1 and 3.0 forms phones still export).

Supported: line unfolding, property groups (`item1.TEL`), parameters with quoted and comma-separated values, bare
2.1 type parameters (`TEL;CELL:`), value unescaping, `tel:` URIs. Each card becomes one row with the fixed columns
VCARD_COLUMNS; the first mobile (TYPE=cell) number goes first so contacts map their mobile as the primary phone.
A malformed card becomes a row-level error and reading continues with the next card.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from .errors import UNPROCESSABLE, ImportFileError, RowError
from .header import Cell, ParsedRow

VCARD_COLUMNS = ("Full name", "Organization", "Title", "Mobile phone", "Other phones", "Emails")
BEGIN, END = "BEGIN:VCARD", "END:VCARD"
MAX_LINE_CHARS = 10_000
MAX_PROPERTIES = 500
MOBILE_TYPES = frozenset({"cell", "mobile", "iphone"})
NAME_PATTERN = re.compile(r"^[A-Za-z0-9-]+$")
URI_PREFIXES = ("tel:", "mailto:")
ESCAPES = {"n": "\n", "N": "\n", ",": ",", ";": ";", "\\": "\\"}
FOLD_CHARS = (" ", "\t")


@dataclass(frozen=True)
class ContentLine:
    """One parsed property: `[group.]NAME;params:value`."""

    name: str
    types: frozenset[str]
    value: str


def unescape(value: str) -> str:
    r"""Undo vCard text escaping (\, \; \n \\).

    Args:
        value: Escaped text.

    Returns:
        Plain text.
    """
    out: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char == "\\" and index + 1 < len(value) and value[index + 1] in ESCAPES:
            out.append(ESCAPES[value[index + 1]])
            index += 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


def split_unescaped(value: str, separator: str) -> list[str]:
    """Split on a separator that is not escaped with a backslash.

    Args:
        value: Escaped text.
        separator: One character.

    Returns:
        The escaped parts.
    """
    parts: list[str] = []
    current: list[str] = []
    escaped = False
    for char in value:
        if char == separator and not escaped:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
        escaped = char == "\\" and not escaped
    parts.append("".join(current))
    return parts


def _split_quoted(text: str, separator: str) -> list[str]:
    """Split on a separator outside double quotes.

    Args:
        text: Text.
        separator: One character.

    Returns:
        The parts.
    """
    parts: list[str] = []
    current: list[str] = []
    quoted = False
    for char in text:
        if char == '"':
            quoted = not quoted
        if char == separator and not quoted:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return parts


def _types(params: list[str]) -> frozenset[str]:
    """Collect TYPE values, including bare 2.1 parameters like CELL.

    Args:
        params: Parameter texts after the property name.

    Returns:
        Lowercased types.
    """
    found: set[str] = set()
    for param in params:
        name, has_value, raw = param.partition("=")
        if not has_value:
            found.add(name.strip().lower())
        elif name.strip().upper() == "TYPE":
            found.update(part.strip().strip('"').lower() for part in raw.strip('"').split(","))
    return frozenset(item for item in found if item)


def parse_line(line: str) -> ContentLine | None:
    """Parse one unfolded content line.

    Args:
        line: Text like `item1.TEL;TYPE=cell:+1 214 555 0100`.

    Returns:
        The property, or None when the line is malformed.
    """
    head = _split_quoted(line, ":")
    if len(head) < 2:
        return None
    left, value = head[0], line[len(head[0]) + 1:]
    params = _split_quoted(left, ";")
    name = params[0].rsplit(".", 1)[-1].strip()
    if not NAME_PATTERN.fullmatch(name):
        return None
    return ContentLine(name.upper(), _types(params[1:]), value)


def _plain(value: str) -> str:
    """Unescape a value and drop a tel: or mailto: URI prefix.

    Args:
        value: Raw value.

    Returns:
        Plain text.
    """
    text = unescape(value).strip()
    for prefix in URI_PREFIXES:
        if text.lower().startswith(prefix):
            return text[len(prefix):].strip()
    return text


@dataclass
class _Card:
    """Properties collected for one card."""

    props: list[ContentLine] = field(default_factory=list[ContentLine])
    error: RowError | None = None

    def add(self, line: str) -> None:
        """Parse and keep one content line, or remember the card is malformed.

        Args:
            line: Unfolded content line.
        """
        if self.error is not None:
            return
        parsed = parse_line(line) if len(line) <= MAX_LINE_CHARS else None
        if parsed is None:
            self.error = RowError("malformed_line", "a line in this card could not be read")
        elif len(self.props) >= MAX_PROPERTIES:
            self.error = RowError("malformed_card", f"a card may hold at most {MAX_PROPERTIES} properties")
        else:
            self.props.append(parsed)

    def first(self, name: str) -> str | None:
        """Return the first value of a property.

        Args:
            name: Property name.

        Returns:
            The raw value, or None.
        """
        return next((prop.value for prop in self.props if prop.name == name), None)

    def full_name(self) -> str | None:
        """Return FN, or "Given Family" built from N.

        Returns:
            The name, or None.
        """
        formatted = _plain(self.first("FN") or "")
        if formatted:
            return formatted
        parts = [unescape(part).strip() for part in split_unescaped(self.first("N") or "", ";")]
        given, family = (parts + ["", ""])[1], parts[0]
        return " ".join(part for part in (given, family) if part) or None

    def cells(self) -> tuple[Cell, ...]:
        """Render the card as one row of VCARD_COLUMNS.

        Returns:
            The cells.
        """
        phones = [(_plain(prop.value), prop.types) for prop in self.props if prop.name == "TEL"]
        phones = [(number, types) for number, types in phones if number]
        mobile = next((number for number, types in phones if types & MOBILE_TYPES), None)
        others = [number for number, _types in phones]
        if mobile is not None:
            others.remove(mobile)
        emails = [email for email in (_plain(prop.value) for prop in self.props if prop.name == "EMAIL") if email]
        org = split_unescaped(self.first("ORG") or "", ";")[0]
        return (self.full_name(), unescape(org).strip() or None, _plain(self.first("TITLE") or "") or None, mobile,
                others or None, emails or None)


def unfold(lines: Iterable[str]) -> Iterator[str]:
    """Join folded lines (a line starting with a space or tab continues the previous one).

    Args:
        lines: Physical lines.

    Yields:
        Logical lines without line endings (overlong ones are cut at MAX_LINE_CHARS + 1 chars).
    """
    pending: str | None = None
    for raw in lines:
        line = raw.rstrip("\r\n")
        if pending is not None and line.startswith(FOLD_CHARS):
            if len(pending) <= MAX_LINE_CHARS:
                pending += line[1:]
            continue
        if pending is not None:
            yield pending[: MAX_LINE_CHARS + 1]
        pending = line
    if pending is not None:
        yield pending[: MAX_LINE_CHARS + 1]


def _finish(card: _Card, row_no: int) -> ParsedRow:
    """Close a card into a row.

    Args:
        card: Collected card.
        row_no: Card number.

    Returns:
        The row (cells, or the card's error).
    """
    if card.error is not None:
        return ParsedRow(row_no, None, card.error)
    return ParsedRow(row_no, card.cells(), None)


def _advance(row_no: int, max_cards: int) -> int:
    """Count one more row, refusing the file past the cap.

    Args:
        row_no: Rows so far.
        max_cards: Row cap.

    Returns:
        The next row number.

    Raises:
        ImportFileError: 422 too_many_rows.
    """
    if row_no >= max_cards:
        raise ImportFileError(UNPROCESSABLE, "too_many_rows", f"the file has more than {max_cards} rows")
    return row_no + 1


def read_cards(lines: Iterable[str], max_cards: int) -> Iterator[ParsedRow]:
    """Read cards from text lines, one row per card (or per block of stray text).

    Args:
        lines: Physical lines of the file.
        max_cards: Row cap; reading stops at the first row past it.

    Yields:
        Rows with VCARD_COLUMNS cells, or a row-level error.

    Raises:
        ImportFileError: 422 too_many_rows past max_cards.
    """
    card: _Card | None = None
    row_no, stray = 0, False
    for line in unfold(lines):
        marker = line.strip().upper()
        if not marker:
            continue
        if marker == BEGIN:
            if card is not None:
                row_no = _advance(row_no, max_cards)
                yield ParsedRow(row_no, None, RowError("malformed_card", "a card is missing END:VCARD"))
            card, stray = _Card(), False
        elif marker == END and card is not None:
            row_no = _advance(row_no, max_cards)
            yield _finish(card, row_no)
            card, stray = None, False
        elif card is not None:
            card.add(line)
        elif not stray:
            row_no, stray = _advance(row_no, max_cards), True
            yield ParsedRow(row_no, None, RowError("outside_card", "text outside a vCard was ignored"))
    if card is not None:
        row_no = _advance(row_no, max_cards)
        yield ParsedRow(row_no, None, RowError("malformed_card", "a card is missing END:VCARD"))
