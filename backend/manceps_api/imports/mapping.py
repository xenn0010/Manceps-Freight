"""Column-to-field mapping: header normalization, suggestions from the synonym table, and validation of a mapping.

A header is matched on its normalized form, then without digits ("Phone 1" -> "phone"), then without a trailing
"value" (Google Contacts' "Phone 1 - Value"). List fields (phones, emails, equipment, tags) may take several
columns; any other field at most one. Columns that look like consent are never suggested and consent can never be a
mapping target: consent is recorded through the consent ledger only.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence

from ..errors import ApiError
from .schema import ENTITY_SPECS, NAME, EntitySpec

NON_ALNUM = re.compile(r"[^a-z0-9]")
DIGITS = re.compile(r"[0-9]")
VALUE_SUFFIX = "value"
CONSENT_MARKERS = ("consent", "optin", "optout", "tcpa")
CONSENT_TARGETS = frozenset({"consent", "sms", "voice", "whatsapp", "sms_consent", "voice_consent",
                             "whatsapp_consent", "consent_sms", "consent_voice", "consent_whatsapp", "opt_in"})
GOOGLE_COLUMN = re.compile(r"^(email|phone)[0-9]+value$")
UNPROCESSABLE = 422


def normalize_header(text: str) -> str:
    """Reduce a header to lowercase ASCII letters and digits ("MC#" -> "mc", "E-mail" -> "email").

    Args:
        text: Header text.

    Returns:
        The normalized form.
    """
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return NON_ALNUM.sub("", ascii_text.lower())


def _candidates(column: str) -> list[str]:
    """Forms of a header to look up, most specific first.

    Args:
        column: Header text.

    Returns:
        Normalized candidates.
    """
    exact = normalize_header(column)
    bare = DIGITS.sub("", exact)
    trimmed = bare.removesuffix(VALUE_SUFFIX) if bare != VALUE_SUFFIX else bare
    return list(dict.fromkeys(form for form in (exact, bare, trimmed) if form))


def is_consent_column(column: str) -> bool:
    """Tell whether a header looks like a consent or opt-in column.

    Args:
        column: Header text.

    Returns:
        True for consent-like headers.
    """
    normalized = normalize_header(column)
    return any(marker in normalized for marker in CONSENT_MARKERS)


def consent_columns(columns: Iterable[str]) -> list[str]:
    """List the consent-like columns (shown to the user as ignored).

    Args:
        columns: Headers.

    Returns:
        The consent-like headers.
    """
    return [column for column in columns if is_consent_column(column)]


def _lookup(spec: EntitySpec, column: str) -> str | None:
    """Find the field a header names.

    Args:
        spec: Entity spec.
        column: Header text.

    Returns:
        Field name, or None.
    """
    for candidate in _candidates(column):
        for name, field in spec.fields.items():
            if candidate in field.synonyms:
                return name
    return None


def suggest_mapping(entity: str, columns: Sequence[str]) -> dict[str, str | None]:
    """Suggest a field for every column.

    Args:
        entity: Entity name.
        columns: Headers in file order.

    Returns:
        Column to field (None when unmapped); a non-list field is suggested for its first column only.
    """
    spec = ENTITY_SPECS[entity]
    used: set[str] = set()
    suggested: dict[str, str | None] = {}
    for column in columns:
        field = None if is_consent_column(column) else _lookup(spec, column)
        if field is not None and not spec.fields[field].is_list and field in used:
            field = None
        if field is not None:
            used.add(field)
        suggested[column] = field
    return suggested


def unmapped_required(entity: str, mapping: Mapping[str, str | None]) -> list[str]:
    """List required fields that no column maps to (one name per unmet requirement).

    Args:
        entity: Entity name.
        mapping: Column to field.

    Returns:
        Field names, e.g. ["phone"].
    """
    mapped = {field for field in mapping.values() if field is not None}
    return [NAME if NAME in group else min(group) for group in ENTITY_SPECS[entity].required if not group & mapped]


def _refuse(code: str, message: str, details: Mapping[str, object]) -> ApiError:
    """Build a 422 mapping error.

    Args:
        code: Error code.
        message: Safe message.
        details: Details.

    Returns:
        The error.
    """
    return ApiError(UNPROCESSABLE, code, message, dict(details))


def check_mapping(entity: str, columns: Sequence[str], proposed: Mapping[str, str | None]) -> dict[str, str | None]:
    """Validate a client's mapping and complete it over every column.

    Args:
        entity: Entity name.
        columns: Detected headers.
        proposed: Column to field (columns left out are unmapped).

    Returns:
        Column to field for every column.

    Raises:
        ApiError: 422 unknown_column, field_not_importable, unknown_field, duplicate_field or
            required_field_unmapped.
    """
    spec = ENTITY_SPECS[entity]
    known = set(columns)
    used: set[str] = set()
    for column, field in proposed.items():
        if column not in known:
            raise _refuse("unknown_column", "the mapping names a column the file does not have", {"column": column})
        if field is None:
            continue
        if field in CONSENT_TARGETS:
            raise _refuse("field_not_importable", "consent is recorded through the consent ledger, never imported",
                          {"column": column, "field": field})
        if field not in spec.fields:
            raise _refuse("unknown_field", f"{entity} have no such field", {"column": column, "field": field})
        if field in used and not spec.fields[field].is_list:
            raise _refuse("duplicate_field", "only one column may map to this field", {"field": field})
        used.add(field)
    complete = {column: proposed.get(column) for column in columns}
    missing = unmapped_required(entity, complete)
    if missing:
        raise _refuse("required_field_unmapped", "map a column to every required field", {"fields": missing})
    return complete


def is_google_contacts(columns: Iterable[str]) -> bool:
    """Tell whether headers come from a Google Contacts export.

    Args:
        columns: Headers.

    Returns:
        True when an "E-mail N - Value" or "Phone N - Value" column is present.
    """
    return any(GOOGLE_COLUMN.fullmatch(normalize_header(column)) for column in columns)
