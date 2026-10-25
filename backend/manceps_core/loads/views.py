"""Small derived views of a load shared by the API, the board and exports: lane text and its first/last stops."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

PICKUP, DELIVERY = "pickup", "delivery"
LANE_ARROW = " → "


def mapping(value: Any) -> dict[str, Any] | None:
    """Read a stored sub-document.

    Args:
        value: Stored value.

    Returns:
        A copy as a dict, or None when it is not a mapping.
    """
    return dict(cast(Mapping[str, Any], value)) if isinstance(value, Mapping) else None


def mappings(value: Any) -> list[dict[str, Any]]:
    """Read a stored list of sub-documents, skipping anything malformed.

    Args:
        value: Stored value.

    Returns:
        Copies of the mapping items.
    """
    if not isinstance(value, list | tuple):
        return []
    items: list[Any] = list(cast(list[Any], value))
    return [dict(cast(Mapping[str, Any], item)) for item in items if isinstance(item, Mapping)]


def stops_of(load: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Read a load's stops in sequence order.

    Args:
        load: Load document.

    Returns:
        The stops (empty when none or malformed).
    """
    return sorted(mappings(load.get("stops")), key=lambda stop: int(stop.get("seq") or 0))


def first_stop(load: Mapping[str, Any], kind: str) -> Mapping[str, Any] | None:
    """Return the first stop of a kind.

    Args:
        load: Load document.
        kind: pickup or delivery.

    Returns:
        The stop, or None.
    """
    return next((stop for stop in stops_of(load) if stop.get("type") == kind), None)


def last_stop(load: Mapping[str, Any], kind: str) -> Mapping[str, Any] | None:
    """Return the last stop of a kind.

    Args:
        load: Load document.
        kind: pickup or delivery.

    Returns:
        The stop, or None.
    """
    matching = [stop for stop in stops_of(load) if stop.get("type") == kind]
    return matching[-1] if matching else None


def place_text(stop: Mapping[str, Any] | None) -> str | None:
    """Render a stop's place as "City, ST", falling back to the address.

    Args:
        stop: Stop, or None.

    Returns:
        The text, or None when the stop names no place.
    """
    if stop is None:
        return None
    parts = [str(stop[key]) for key in ("city", "state") if stop.get(key)]
    if parts:
        return ", ".join(parts)
    address = stop.get("address")
    return str(address) if address else None


def lane_text(load: Mapping[str, Any]) -> str | None:
    """Render a load's lane, "Fresno, CA → Stockton, CA".

    Args:
        load: Load document.

    Returns:
        The lane, or None when neither end is known.
    """
    origin = place_text(first_stop(load, PICKUP))
    destination = place_text(last_stop(load, DELIVERY))
    if origin is None and destination is None:
        return None
    return f"{origin or '?'}{LANE_ARROW}{destination or '?'}"
