"""Email address normalization shared by sign-in, invitations and firm data."""

from __future__ import annotations

import re

EMAIL_MAX = 254
EMAIL_PATTERN = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]+$")


def normalize_email(value: str) -> str:
    """Trim, lowercase and sanity-check an email address.

    Args:
        value: Address as typed.

    Returns:
        The normalized address.

    Raises:
        ValueError: If it does not look like an address.
    """
    value = value.strip().lower()
    if len(value) > EMAIL_MAX or not EMAIL_PATTERN.fullmatch(value):
        raise ValueError("enter a valid email address")
    return value
