"""Property-based tests (Hypothesis): normalizers, validators, canonical hashing and pagination cursors.

No input may crash these functions with an unexpected exception or produce an invalid value: each either returns a
value in its documented form or refuses with its documented error.
"""

from __future__ import annotations

import json
import math
import string
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from bson import ObjectId
from hypothesis import given, settings
from hypothesis import strategies as st

from manceps_api.errors import ApiError
from manceps_api.pagination import MAX_CURSOR_CHARS, decode_cursor, encode_cursor
from manceps_core.emails import EMAIL_MAX, EMAIL_PATTERN, normalize_email
from manceps_core.hashing import canonical_json, sha256_hex
from manceps_core.phones import E164_US, normalize_phone
from manceps_core.repo import fields
from manceps_core.repo.brokers import normalize_mc
from manceps_core.repo.errors import Invalid

EXAMPLES = 300
ASCII_DIGITS = frozenset(string.digits)
DIGITISH = st.text(alphabet=st.characters(categories=["Nd", "Pd", "Zs", "Ps", "Pe"]), max_size=14)
SEPARATORS = st.sampled_from(["", " ", "-", ".", "(", ")", "+", " - "])
JSON_SCALARS = st.one_of(st.none(), st.booleans(), st.integers(min_value=-(2**63), max_value=2**63 - 1),
                         st.floats(allow_nan=False, allow_infinity=False), st.text(max_size=20))
JSON_VALUES = st.recursive(JSON_SCALARS, lambda inner: st.one_of(
    st.lists(inner, max_size=5), st.dictionaries(st.text(max_size=8), inner, max_size=5)), max_leaves=20)


@st.composite
def us_phones(draw: st.DrawFn) -> tuple[str, str]:
    """Draw a valid 10-digit US number written in a random human format.

    Args:
        draw: Hypothesis draw function.

    Returns:
        (formatted text, expected E.164).
    """
    digits = draw(st.text(alphabet=string.digits, min_size=10, max_size=10))
    pieces = [digits[:3], digits[3:6], digits[6:]]
    prefix = draw(st.sampled_from(["", "1", "+1", "+1 ", "1-"]))
    text = prefix + "".join(draw(SEPARATORS) + piece for piece in pieces)
    return text, f"+1{digits}"


@settings(max_examples=EXAMPLES)
@given(st.one_of(st.text(), DIGITISH))
def test_phone_normalizer_never_crashes_and_only_returns_e164(raw: str) -> None:
    try:
        normalized = normalize_phone(raw)
    except ValueError:
        return
    assert E164_US.fullmatch(normalized) and set(normalized[1:]) <= ASCII_DIGITS
    assert normalize_phone(normalized) == normalized


@settings(max_examples=EXAMPLES)
@given(us_phones())
def test_phone_normalizer_accepts_every_common_format(case: tuple[str, str]) -> None:
    text, expected = case
    assert normalize_phone(text) == expected


@settings(max_examples=EXAMPLES)
@given(st.text(alphabet=st.characters(categories=["Nd"]), min_size=10, max_size=11))
def test_phone_normalizer_refuses_non_ascii_digits(raw: str) -> None:
    if set(raw) <= ASCII_DIGITS:
        return
    with pytest.raises(ValueError):
        normalize_phone(raw)


@settings(max_examples=EXAMPLES)
@given(st.text(max_size=300))
def test_email_normalizer_is_idempotent_and_valid(raw: str) -> None:
    try:
        normalized = normalize_email(raw)
    except ValueError:
        return
    assert len(normalized) <= EMAIL_MAX and EMAIL_PATTERN.fullmatch(normalized)
    assert normalized == normalized.strip() and normalize_email(normalized) == normalized


@settings(max_examples=EXAMPLES)
@given(st.from_regex(r"[a-z0-9._%+-]{1,20}@[a-z0-9-]{1,20}\.[a-z]{2,6}", fullmatch=True), st.booleans())
def test_email_normalizer_accepts_plain_addresses(address: str, shout: bool) -> None:
    typed = f"  {address.upper() if shout else address}\t"
    assert normalize_email(typed) == address


@settings(max_examples=EXAMPLES)
@given(st.lists(st.text(max_size=40), max_size=15))
def test_tag_validator_returns_only_valid_sorted_unique_tags(raw: list[str]) -> None:
    try:
        tags = fields.tags("tags", raw)
    except Invalid:
        return
    assert tags == sorted(set(tags)) and len(tags) <= fields.MAX_TAGS
    assert all(fields.TAG_PATTERN.fullmatch(tag) and tag.isascii() for tag in tags)
    assert fields.tags("tags", tags) == tags


@settings(max_examples=EXAMPLES)
@given(st.lists(st.from_regex(r"[a-z][a-z0-9_]{1,31}", fullmatch=True), max_size=fields.MAX_TAGS))
def test_tag_validator_accepts_valid_tags(raw: list[str]) -> None:
    assert fields.tags("tags", raw) == sorted(set(raw))


@settings(max_examples=EXAMPLES)
@given(st.one_of(st.text(), DIGITISH, st.integers(), st.none()))
def test_mc_validator_returns_ascii_digits_only(raw: Any) -> None:
    try:
        mc = normalize_mc(raw)
    except Invalid:
        return
    assert mc and set(mc) <= ASCII_DIGITS and normalize_mc(mc) == mc


@settings(max_examples=EXAMPLES)
@given(st.text(alphabet=string.digits, min_size=1, max_size=8), st.sampled_from(["MC", "MC-", "mc #", "", "MC "]))
def test_mc_validator_strips_prefixes(digits: str, prefix: str) -> None:
    assert normalize_mc(prefix + digits) == digits


@settings(max_examples=EXAMPLES)
@given(JSON_VALUES)
def test_canonical_json_round_trips_and_is_stable(value: Any) -> None:
    text = canonical_json(value)
    assert json.loads(text) == value
    assert canonical_json(json.loads(text)) == text
    assert len(sha256_hex(value)) == 64


@settings(max_examples=EXAMPLES)
@given(st.dictionaries(st.text(max_size=8), JSON_SCALARS, min_size=1, max_size=8), st.randoms())
def test_canonical_json_ignores_key_order(value: dict[str, Any], rng: Any) -> None:
    keys = list(value)
    rng.shuffle(keys)
    assert sha256_hex({key: value[key] for key in keys}) == sha256_hex(value)


@settings(max_examples=EXAMPLES)
@given(JSON_VALUES, JSON_VALUES)
def test_canonical_hash_separates_different_values(left: Any, right: Any) -> None:
    if canonical_json(left) != canonical_json(right):
        assert sha256_hex(left) != sha256_hex(right)
    assert (sha256_hex(left) == sha256_hex(right)) == (json.dumps(left, sort_keys=True) == json.dumps(right,
                                                                                                    sort_keys=True))


@settings(max_examples=EXAMPLES)
@given(st.one_of(st.just(math.nan), st.just(math.inf), st.just(-math.inf)), st.text(max_size=5))
def test_canonical_json_refuses_non_finite_numbers(number: float, key: str) -> None:
    for value in (number, [number], {key: number}):
        with pytest.raises(ValueError):
            canonical_json(value)


@settings(max_examples=EXAMPLES)
@given(st.integers(min_value=0, max_value=10**6), st.text(max_size=5))
def test_canonical_json_refuses_ambiguous_keys(number: int, value: str) -> None:
    with pytest.raises(TypeError):
        canonical_json({number: value})
    assert sha256_hex({str(number): value}) != sha256_hex([str(number), value])


@settings(max_examples=EXAMPLES)
@given(st.datetimes(timezones=st.just(UTC)), st.integers(min_value=-1440, max_value=1440))
def test_canonical_json_datetimes(moment: datetime, offset_minutes: int) -> None:
    assert canonical_json(moment) == json.dumps(moment.isoformat())
    with pytest.raises(ValueError):
        canonical_json(moment.replace(tzinfo=None) + timedelta(minutes=offset_minutes))


@settings(max_examples=EXAMPLES)
@given(st.binary(min_size=12, max_size=12))
def test_cursor_round_trips_every_object_id(raw: bytes) -> None:
    object_id = ObjectId(raw)
    cursor = encode_cursor(object_id)
    assert len(cursor) <= MAX_CURSOR_CHARS and cursor.isascii() and "=" not in cursor
    assert decode_cursor(cursor) == object_id


@settings(max_examples=EXAMPLES)
@given(st.text(max_size=MAX_CURSOR_CHARS))
def test_cursor_decoder_refuses_garbage_with_400(cursor: str) -> None:
    try:
        decoded = decode_cursor(cursor)
    except ApiError as exc:
        assert exc.status_code == 400 and exc.code == "invalid_cursor"
        return
    assert isinstance(decoded, ObjectId) and decode_cursor(encode_cursor(decoded)) == decoded
