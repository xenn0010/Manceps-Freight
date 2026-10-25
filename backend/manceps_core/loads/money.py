"""Load money math in integer cents. Every division rounds half up (documented rule), never with binary floats."""

from __future__ import annotations

import math
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

MAX_RATE_CENTS = 100_000_000
MAX_MILES = 10_000.0
CENTS_PER_DOLLAR = 100
PERCENT = 100
ONE = Decimal(1)
MONEY_NOISE = re.compile(r"[\s$,]")


def _decimal(value: float | int) -> Decimal:
    """Convert a number exactly as written (floats through their shortest repr).

    Args:
        value: Number.

    Returns:
        The decimal.
    """
    return Decimal(str(value)) if isinstance(value, float) else Decimal(value)


def round_half_up(value: Decimal) -> int:
    """Round to a whole number, halves away from zero.

    Args:
        value: Decimal value.

    Returns:
        The integer.
    """
    return int(value.quantize(ONE, rounding=ROUND_HALF_UP))


def per_mile_cents(rate_cents: int, miles: float | int | None) -> int | None:
    """Rate per mile in cents.

    Args:
        rate_cents: Amount in cents.
        miles: Miles, or None.

    Returns:
        Cents per mile rounded half up, or None when miles are missing or not positive.
    """
    if miles is None or not math.isfinite(miles) or miles <= 0:
        return None
    return round_half_up(Decimal(rate_cents) / _decimal(miles))


def per_mile_total(cents_per_mile: int, miles: float) -> int:
    """A per-mile amount over a distance.

    Args:
        cents_per_mile: Cents per mile.
        miles: Miles.

    Returns:
        Cents rounded half up.
    """
    return round_half_up(Decimal(cents_per_mile) * _decimal(miles))


def percent_of(cents: int, pct: float) -> int:
    """A percentage of an amount in cents.

    Args:
        cents: Amount in cents.
        pct: Percent (e.g. 10.5).

    Returns:
        Cents rounded half up.
    """
    return round_half_up(Decimal(cents) * _decimal(pct) / PERCENT)


def fuel_cost_cents(miles: float, mpg: float, diesel_dollars_per_gallon: float) -> int:
    """Fuel cost for a distance.

    Args:
        miles: Total miles.
        mpg: Miles per gallon (positive).
        diesel_dollars_per_gallon: Diesel price.

    Returns:
        Cents rounded half up.
    """
    gallons = _decimal(miles) / _decimal(mpg)
    return round_half_up(gallons * _decimal(diesel_dollars_per_gallon) * CENTS_PER_DOLLAR)


def dollars_to_cents(raw: object) -> int:
    """Parse a dollar amount from a sheet cell or number ("$2,240", 650.5, 380).

    Args:
        raw: Cell value.

    Returns:
        Cents rounded half up, from 0 to MAX_RATE_CENTS.

    Raises:
        ValueError: If it is not a finite, non-negative amount within range.
    """
    if isinstance(raw, bool) or raw is None:
        raise ValueError("enter an amount in dollars")
    if isinstance(raw, int | float):
        text = str(raw)
    elif isinstance(raw, str):
        text = MONEY_NOISE.sub("", raw)
    else:
        raise ValueError("enter an amount in dollars")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("enter an amount in dollars") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("enter a positive amount in dollars")
    if amount * CENTS_PER_DOLLAR > MAX_RATE_CENTS:
        raise ValueError("the amount is too large")
    return round_half_up(amount * CENTS_PER_DOLLAR)
