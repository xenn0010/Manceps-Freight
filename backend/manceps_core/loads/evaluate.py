"""Load economics and verdict, ported from hermes-freight `loads.load_evaluate`, in integer cents.

Inputs that cannot be obtained (no routing key, EIA down, no carrier, no fee or floor) are reported as unknown and
never guessed. The verdict is fail-closed: `accept` only when every input is known and the rate per total mile meets
the carrier's floor; `pass` on an equipment mismatch or an avoided area; `counter` (with the lowest acceptable total)
when below the floor; otherwise `unknown`.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from . import money
from .views import DELIVERY, PICKUP, first_stop, last_stop, mappings, place_text

ACCEPT, COUNTER, PASS, UNKNOWN = "accept", "counter", "pass", "unknown"
VERDICTS = (ACCEPT, COUNTER, PASS, UNKNOWN)
DEFAULT_MPG = 6.5
MIN_MPG, MAX_MPG = 3.0, 12.0
NON_ALNUM = re.compile(r"[^a-z0-9]")


@dataclass(frozen=True)
class Reading:
    """A looked-up value and where it came from ("unknown: <why>" when missing)."""

    value: float | None
    source: str


MilesLookup = Callable[[str, str], Reading]
DieselLookup = Callable[[], Reading]


def _norm(text: Any) -> str:
    """Reduce text to lowercase letters and digits for matching.

    Args:
        text: Any value.

    Returns:
        The normalized text.
    """
    return NON_ALNUM.sub("", str(text or "").lower())


def fit(carrier: Mapping[str, Any], equipment: str | None, origin: str, destination: str) -> dict[str, Any]:
    """Compare a load with a carrier's equipment, preferred lanes and avoid list (plugin rules).

    Args:
        carrier: Carrier document.
        equipment: Load equipment, or None.
        origin: Origin text.
        destination: Destination text.

    Returns:
        equipment_ok (None when the load names none), preferred_lane and avoid_hits.
    """
    route = f"{origin} {destination}".lower()
    lanes = [lane for lane in mappings(carrier.get("preferred_lanes"))
             if lane.get("origin") and lane.get("destination")]
    preferred = any(_norm(lane["origin"]) in _norm(origin) and _norm(lane["destination"]) in _norm(destination)
                    for lane in lanes)
    owned = _texts(carrier.get("equipment"))
    return {"equipment_ok": None if not equipment else equipment in owned, "preferred_lane": preferred,
            "avoid_hits": [item for item in _texts(carrier.get("avoid")) if item.lower() in route]}


def _texts(value: Any) -> list[str]:
    """Read a stored list as texts.

    Args:
        value: Stored value.

    Returns:
        The items as strings (empty when not a list).
    """
    if not isinstance(value, list | tuple):
        return []
    return [str(item) for item in cast(list[Any], value)]


def economics(rate_cents: int, loaded: float, deadhead: float, fee_pct: float | None, mpg: float,
              diesel: float | None) -> dict[str, Any]:
    """Compute per-mile rates, fee, fuel and carrier net in cents.

    Args:
        rate_cents: All-in rate.
        loaded: Loaded miles (positive).
        deadhead: Empty miles to pickup.
        fee_pct: Dispatch fee percent, or None when unknown.
        mpg: Fuel economy.
        diesel: Diesel $/gal, or None when unknown.

    Returns:
        The figures; unknown ones are None.
    """
    total = round(loaded + deadhead, 1)
    fee = None if fee_pct is None else money.percent_of(rate_cents, fee_pct)
    fuel = None if diesel is None else money.fuel_cost_cents(total, mpg, diesel)
    net = None if fee is None or fuel is None else rate_cents - fee - fuel
    return {"loaded_miles": loaded, "deadhead_miles": deadhead, "total_miles": total,
            "rate_per_loaded_mile_cents": money.per_mile_cents(rate_cents, loaded),
            "rate_per_total_mile_cents": money.per_mile_cents(rate_cents, total),
            "dispatch_fee_cents": fee, "fuel_cost_cents": fuel, "carrier_net_cents": net}


def _number(value: Any) -> float | None:
    """Read a positive number from a stored field.

    Args:
        value: Stored value.

    Returns:
        The float, or None.
    """
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        return None
    return float(value)


def verdict(carrier: Mapping[str, Any] | None, econ: Mapping[str, Any] | None, found: Mapping[str, Any] | None,
            unknown: list[str]) -> dict[str, Any]:
    """Decide accept, counter, pass or unknown.

    Args:
        carrier: Carrier, or None.
        econ: Economics, or None when miles or rate are unknown.
        found: Fit findings, or None without a carrier.
        unknown: Names of unknown inputs so far.

    Returns:
        verdict, reason and, for a counter or accept, the floor figures.
    """
    if found is not None and (found["equipment_ok"] is False or found["avoid_hits"]):
        return {"verdict": PASS, "reason": "equipment mismatch or avoided area"}
    if carrier is None or econ is None:
        return {"verdict": UNKNOWN, "reason": f"unknown: {', '.join(unknown)}"}
    floor = _number(carrier.get("rate_floor_per_mile"))
    if floor is None:
        return {"verdict": UNKNOWN, "reason": "carrier has no rate floor; ask the dispatcher"}
    try:
        floor_cents = money.dollars_to_cents(floor)
    except ValueError:
        return {"verdict": UNKNOWN, "reason": "carrier's rate floor is out of range; ask the dispatcher"}
    target = money.per_mile_total(floor_cents, float(econ["total_miles"]))
    figures = {"floor_per_mile_cents": floor_cents, "floor_total_cents": target}
    if (econ["rate_per_total_mile_cents"] or 0) < floor_cents:
        return {"verdict": COUNTER, "reason": "below the carrier's floor", "counter_at_least_cents": target,
                **figures}
    if unknown:
        return {"verdict": UNKNOWN, "reason": f"meets the floor, but unknown: {', '.join(unknown)}", **figures}
    return {"verdict": ACCEPT, "reason": "meets the carrier's floor", **figures}


def _miles(load: Mapping[str, Any], lookup: MilesLookup | None, origin: str, destination: str) -> Reading:
    """Find loaded miles: the load's own figure, else the routing lookup.

    Args:
        load: Load.
        lookup: Routing lookup, or None when no routing key is configured.
        origin: Origin text.
        destination: Destination text.

    Returns:
        The reading.
    """
    given = _number(load.get("loaded_miles"))
    if given is not None:
        return Reading(given, "given")
    if lookup is None:
        return Reading(None, "unknown: no GOOGLE_MAPS_API_KEY or ORS_API_KEY and no loaded_miles on the load")
    if not origin or not destination:
        return Reading(None, "unknown: the load needs a pickup and a delivery place")
    return lookup(origin, destination)


def evaluate(load: Mapping[str, Any], carrier: Mapping[str, Any] | None, miles_lookup: MilesLookup | None,
             diesel_lookup: DieselLookup | None, mpg: float = DEFAULT_MPG) -> dict[str, Any]:
    """Evaluate a load for its carrier.

    Args:
        load: Load document.
        carrier: The load's carrier, or None.
        miles_lookup: Routing lookup, or None when not configured.
        diesel_lookup: Diesel lookup, or None when not configured.
        mpg: Fuel economy (clamped to [MIN_MPG, MAX_MPG]).

    Returns:
        verdict, reason, fit, economics, sources and unknown (names of missing inputs).
    """
    origin = place_text(first_stop(load, PICKUP)) or ""
    destination = place_text(last_stop(load, DELIVERY)) or ""
    miles = _miles(load, miles_lookup, origin, destination)
    diesel = diesel_lookup() if diesel_lookup is not None else Reading(None, "unknown: EIA_API_KEY not set")
    rate = load.get("rate_cents")
    fee = _number(carrier.get("dispatch_fee_pct")) if carrier is not None else None
    unknown = [name for name, value in (("rate", rate), ("miles", miles.value), ("carrier", carrier),
                                        ("dispatch_fee", fee), ("diesel", diesel.value)) if value is None]
    econ = None
    if isinstance(rate, int) and miles.value is not None:
        deadhead = _number(load.get("deadhead_miles")) or 0.0
        econ = economics(rate, round(miles.value, 1), deadhead, fee, min(max(mpg, MIN_MPG), MAX_MPG), diesel.value)
    found = None if carrier is None else fit(carrier, load.get("equipment"), origin, destination)
    return {**verdict(carrier, econ, found, unknown), "fit": found, "economics": econ, "unknown": unknown,
            "sources": {"miles": miles.source, "diesel": diesel.source}}
