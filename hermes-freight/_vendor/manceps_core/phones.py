"""US phone normalization to E.164 (the same rule as signup-api and the hermes-freight plugin)."""

from __future__ import annotations

import re

US_COUNTRY_CODE = "1"
US_NATIONAL_DIGITS = 10
NON_DIGITS = re.compile(r"[^0-9]")  # ASCII only: \D would keep Arabic-Indic and other Unicode digits
E164_US = re.compile(r"^\+1[0-9]{10}$")


def normalize_phone(raw: str) -> str:
    """Normalize a US phone number to E.164.

    Args:
        raw: Number in any common US format, e.g. "(214) 555-0199" or "+1 214 555 0199".

    Returns:
        The number as +1XXXXXXXXXX.

    Raises:
        ValueError: If it is not a 10-digit US number.
    """
    digits = NON_DIGITS.sub("", raw or "")
    if len(digits) == US_NATIONAL_DIGITS + 1 and digits.startswith(US_COUNTRY_CODE):
        digits = digits[1:]
    if len(digits) != US_NATIONAL_DIGITS:
        raise ValueError("enter a 10-digit US phone number")
    return f"+{US_COUNTRY_CODE}{digits}"
