"""Routing miles (Google Routes, else OpenRouteService HGV) and the EIA weekly diesel price for load evaluation.

Endpoints and request shapes are the ones the hermes-freight plugin already uses live (`hermes-freight/loads.py`).
Every call has a timeout and bounded retries with exponential backoff (all calls are read-only lookups). A failure
becomes an `unknown: <reason>` reading whose reason names only the error type or HTTP status, never the URL (EIA and
ORS geocode URLs carry the key). Without keys the lookups are absent and the evaluation reports the inputs unknown.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import httpx

from manceps_core.loads.evaluate import DieselLookup, MilesLookup, Reading

from ..settings import Settings

GOOGLE_ROUTES = "https://routes.googleapis.com/directions/v2:computeRoutes"
GOOGLE_FIELD_MASK = "routes.distanceMeters"
ORS_GEOCODE = "https://api.openrouteservice.org/geocode/search"
ORS_ROUTE = "https://api.openrouteservice.org/v2/directions/driving-hgv"
EIA_DIESEL = "https://api.eia.gov/v2/petroleum/pri/gnd/data/"
EIA_SERIES = "EMD_EPD2D_PTE_NUS_DPG"
METERS_PER_MILE = 1609.344
HTTP_TIMEOUT_SECONDS = 15.0
MAX_RETRIES = 2
BACKOFF_SECONDS = 0.5
BACKOFF_FACTOR = 2
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
HTTP_ERROR_FROM = 400
MILES_DECIMALS = 1


class FreightLookupFailed(Exception):
    """A lookup failed; the message is safe to store (no URL, no key)."""


class _Transient(FreightLookupFailed):
    """A failure worth retrying."""


@dataclass
class JsonClient:
    """JSON over HTTP with timeouts and bounded retries."""

    transport: httpx.BaseTransport | None = None
    timeout: float = HTTP_TIMEOUT_SECONDS
    retries: int = MAX_RETRIES
    sleep: Callable[[float], None] = field(default=time.sleep)

    def _once(self, client: httpx.Client, method: str, url: str, body: Any, headers: Mapping[str, str]) -> Any:
        """Make one request.

        Args:
            client: httpx client.
            method: GET or POST.
            url: URL.
            body: JSON body or None.
            headers: Extra headers.

        Returns:
            Decoded JSON.

        Raises:
            _Transient: On network errors, 429 and 5xx.
            FreightLookupFailed: On other HTTP errors or invalid JSON.
        """
        try:
            response = client.request(method, url, json=body, headers=dict(headers))
        except httpx.HTTPError as exc:
            raise _Transient(type(exc).__name__) from exc
        if response.status_code in RETRY_STATUSES:
            raise _Transient(f"HTTP {response.status_code}")
        if response.status_code >= HTTP_ERROR_FROM:
            raise FreightLookupFailed(f"HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise FreightLookupFailed("invalid JSON") from exc

    def call(self, method: str, url: str, body: Any = None, headers: Mapping[str, str] | None = None) -> Any:
        """Request JSON, retrying transient failures.

        Args:
            method: GET or POST.
            url: URL.
            body: JSON body or None.
            headers: Extra headers.

        Returns:
            Decoded JSON.

        Raises:
            FreightLookupFailed: When every attempt fails.
        """
        with httpx.Client(transport=self.transport, timeout=self.timeout) as client:
            for attempt in range(self.retries):
                try:
                    return self._once(client, method, url, body, headers or {})
                except _Transient:
                    self.sleep(BACKOFF_SECONDS * BACKOFF_FACTOR ** attempt)
            return self._once(client, method, url, body, headers or {})


def _miles(meters: Any) -> float:
    """Convert meters to miles.

    Args:
        meters: Distance in meters.

    Returns:
        Miles with one decimal.
    """
    return round(float(meters) / METERS_PER_MILE, MILES_DECIMALS)


def google_miles(client: JsonClient, key: str) -> MilesLookup:
    """Build a Google Routes (DRIVE) miles lookup.

    Args:
        client: JSON client.
        key: Google Maps Platform key.

    Returns:
        The lookup.
    """

    def lookup(origin: str, destination: str) -> Reading:
        body = {"origin": {"address": origin}, "destination": {"address": destination}, "travelMode": "DRIVE"}
        headers = {"X-Goog-Api-Key": key, "X-Goog-FieldMask": GOOGLE_FIELD_MASK}
        try:
            meters = client.call("POST", GOOGLE_ROUTES, body, headers)["routes"][0]["distanceMeters"]
            return Reading(_miles(meters), "Google Routes DRIVE (car route estimate; brokers may use PC*MILER)")
        except (FreightLookupFailed, KeyError, IndexError, TypeError, ValueError) as exc:
            return Reading(None, f"unknown: Google routing failed ({type(exc).__name__}: {_safe(exc)})")

    return lookup


def _safe(exc: Exception) -> str:
    """Render an error for storage without anything that could hold a URL or key.

    Args:
        exc: Exception.

    Returns:
        Its message when it is one of ours, else its type.
    """
    return str(exc) if isinstance(exc, FreightLookupFailed) else type(exc).__name__


def ors_miles(client: JsonClient, key: str) -> MilesLookup:
    """Build an OpenRouteService truck (HGV) miles lookup.

    Args:
        client: JSON client.
        key: ORS key.

    Returns:
        The lookup.
    """

    def geocode(place: str) -> list[float]:
        query = urlencode({"api_key": key, "text": place, "boundary.country": "US", "size": 1})
        features = client.call("GET", f"{ORS_GEOCODE}?{query}")["features"]
        return [float(value) for value in features[0]["geometry"]["coordinates"][:2]]

    def lookup(origin: str, destination: str) -> Reading:
        try:
            coords = [geocode(origin), geocode(destination)]
            routes = client.call("POST", ORS_ROUTE, {"coordinates": coords}, {"Authorization": key})["routes"]
            return Reading(_miles(routes[0]["summary"]["distance"]),
                           "openrouteservice driving-hgv (estimate; brokers may use PC*MILER)")
        except (FreightLookupFailed, KeyError, IndexError, TypeError, ValueError) as exc:
            return Reading(None, f"unknown: routing failed ({type(exc).__name__}: {_safe(exc)})")

    return lookup


def eia_diesel(client: JsonClient, key: str) -> DieselLookup:
    """Build the EIA weekly US on-highway diesel lookup.

    Args:
        client: JSON client.
        key: EIA key.

    Returns:
        The lookup.
    """

    def lookup() -> Reading:
        query = urlencode({"api_key": key, "frequency": "weekly", "data[0]": "value",
                           "facets[series][]": EIA_SERIES, "sort[0][column]": "period",
                           "sort[0][direction]": "desc", "length": 1})
        try:
            row = client.call("GET", f"{EIA_DIESEL}?{query}")["response"]["data"][0]
            price = float(row["value"])
            if price <= 0:
                raise ValueError("price")
            return Reading(price, f"EIA weekly US diesel, week of {row.get('period')}")
        except (FreightLookupFailed, KeyError, IndexError, TypeError, ValueError) as exc:
            return Reading(None, f"unknown: EIA lookup failed ({type(exc).__name__}: {_safe(exc)})")

    return lookup


def miles_from_settings(settings: Settings, client: JsonClient | None = None) -> MilesLookup | None:
    """Build the miles lookup: Google when its key is set, else ORS, else None.

    Args:
        settings: Settings.
        client: JSON client (tests pass one with a fake transport).

    Returns:
        The lookup, or None when no routing key is configured.
    """
    http = client or JsonClient()
    if settings.google_maps_api_key is not None and settings.google_maps_api_key.get_secret_value():
        return google_miles(http, settings.google_maps_api_key.get_secret_value())
    if settings.ors_api_key is not None and settings.ors_api_key.get_secret_value():
        return ors_miles(http, settings.ors_api_key.get_secret_value())
    return None


def diesel_from_settings(settings: Settings, client: JsonClient | None = None) -> DieselLookup | None:
    """Build the diesel lookup.

    Args:
        settings: Settings.
        client: JSON client.

    Returns:
        The lookup, or None when EIA_API_KEY is unset.
    """
    if settings.eia_api_key is None or not settings.eia_api_key.get_secret_value():
        return None
    return eia_diesel(client or JsonClient(), settings.eia_api_key.get_secret_value())
