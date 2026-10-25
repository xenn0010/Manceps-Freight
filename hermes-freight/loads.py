"""Load offer math: miles, rate per mile, fuel, fee, and fit against the carrier's terms.

Miles come from the offer, else from the Google Routes API when GOOGLE_MAPS_API_KEY
is set, else from OpenRouteService truck (HGV) routing when ORS_API_KEY is set.
Diesel price comes from the EIA weekly US average when EIA_API_KEY is set.
Anything unavailable is reported as unknown, never guessed.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import pymongo.errors

from . import broker_check, carriers, store, tenant

GOOGLE_ROUTES = "https://routes.googleapis.com/directions/v2:computeRoutes"
GOOGLE_FIELD_MASK = "routes.distanceMeters"
ORS_GEOCODE = "https://api.openrouteservice.org/geocode/search"
ORS_ROUTE = "https://api.openrouteservice.org/v2/directions/driving-hgv"
EIA_DIESEL = "https://api.eia.gov/v2/petroleum/pri/gnd/data/"
EIA_SERIES = "EMD_EPD2D_PTE_NUS_DPG"
HTTP_TIMEOUT_SECONDS = 20
METERS_PER_MILE = 1609.344
DEFAULT_MPG = 6.5
MIN_MPG, MAX_MPG = 3.0, 12.0


def http_post_json(url: str, body: dict[str, Any], headers: dict[str, str]) -> Any:
    """POST JSON and decode the JSON response.

    Args:
        url: Absolute URL.
        body: JSON body.
        headers: Extra headers.

    Returns:
        Decoded JSON.

    Raises:
        urllib.error.URLError: On network or HTTP errors.
        ValueError: If the body is not JSON.
    """
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def _geocode(place: str, key: str) -> list[float]:
    """Geocode a US place to [lon, lat] with OpenRouteService.

    Args:
        place: Place text, e.g. "Dallas, TX".
        key: ORS API key.

    Returns:
        [lon, lat].

    Raises:
        ValueError: If nothing matched.
        urllib.error.URLError: On network errors.
    """
    query = urllib.parse.urlencode({"api_key": key, "text": place, "boundary.country": "US", "size": 1})
    features = (broker_check.http_get_json(f"{ORS_GEOCODE}?{query}") or {}).get("features") or []
    if not features:
        raise ValueError(f"could not locate {place!r}")
    return list(features[0]["geometry"]["coordinates"][:2])


def _google_miles(origin: str, destination: str, key: str) -> tuple[float | None, str]:
    """Driving miles from the Google Routes API, which accepts addresses directly.

    Args:
        origin: Origin place text.
        destination: Destination place text.
        key: Google Maps Platform API key.

    Returns:
        Miles (None if unknown) and where the number came from.
    """
    body = {"origin": {"address": origin}, "destination": {"address": destination}, "travelMode": "DRIVE"}
    headers = {"X-Goog-Api-Key": key, "X-Goog-FieldMask": GOOGLE_FIELD_MASK}
    try:
        meters = float(http_post_json(GOOGLE_ROUTES, body, headers)["routes"][0]["distanceMeters"])
    except (urllib.error.URLError, ValueError, KeyError, IndexError, TypeError, TimeoutError) as exc:
        return None, f"unknown: Google routing failed ({exc})"
    return round(meters / METERS_PER_MILE, 1), "Google Routes DRIVE (car route estimate; brokers may use PC*MILER)"


def route_miles(origin: str, destination: str) -> tuple[float | None, str]:
    """Route miles between two places: Google Routes if configured, else OpenRouteService HGV.

    Args:
        origin: Origin place text.
        destination: Destination place text.

    Returns:
        Miles (None if unknown) and where the number came from.
    """
    google_key = tenant.secret("GOOGLE_MAPS_API_KEY")
    if google_key:
        return _google_miles(origin, destination, google_key)
    key = tenant.secret("ORS_API_KEY")
    if not key:
        return None, "unknown: no GOOGLE_MAPS_API_KEY or ORS_API_KEY and no loaded_miles given"
    try:
        coords = [_geocode(origin, key), _geocode(destination, key)]
        routes = (http_post_json(ORS_ROUTE, {"coordinates": coords}, {"Authorization": key}) or {}).get("routes") or []
        meters = float(routes[0]["summary"]["distance"])
    except (urllib.error.URLError, ValueError, KeyError, IndexError, TypeError, TimeoutError) as exc:
        return None, f"unknown: routing failed ({exc})"
    return round(meters / METERS_PER_MILE, 1), "openrouteservice driving-hgv (estimate; brokers may use PC*MILER)"


def diesel_price() -> tuple[float | None, str]:
    """Latest weekly US average on-highway diesel price.

    Returns:
        $/gallon (None if unknown) and the source or reason.
    """
    key = tenant.secret("EIA_API_KEY")
    if not key:
        return None, "unknown: EIA_API_KEY not set"
    query = urllib.parse.urlencode({
        "api_key": key, "frequency": "weekly", "data[0]": "value", "facets[series][]": EIA_SERIES,
        "sort[0][column]": "period", "sort[0][direction]": "desc", "length": 1,
    })
    try:
        row = broker_check.http_get_json(f"{EIA_DIESEL}?{query}")["response"]["data"][0]
        return float(row["value"]), f"EIA weekly US diesel, week of {row.get('period')}"
    except (urllib.error.URLError, ValueError, KeyError, IndexError, TypeError, TimeoutError) as exc:
        return None, f"unknown: EIA lookup failed ({exc})"


def _lane_match(carrier: dict[str, Any], origin: str, destination: str) -> bool:
    """Check whether the offer matches one of the carrier's preferred lanes.

    Args:
        carrier: Carrier document.
        origin: Offer origin.
        destination: Offer destination.

    Returns:
        True when both ends contain the lane's origin and destination text.
    """
    def norm(text: Any) -> str:
        return re.sub(r"[^a-z0-9]", "", str(text or "").lower())

    return any(norm(lane.get("origin")) in norm(origin) and norm(lane.get("destination")) in norm(destination)
               for lane in carrier.get("preferred_lanes") or [] if lane.get("origin") and lane.get("destination"))


def _fit(carrier: dict[str, Any], offer: dict[str, Any]) -> dict[str, Any]:
    """Compare offer attributes with the carrier's equipment, lanes, and avoid list.

    Args:
        carrier: Carrier document.
        offer: Offer arguments.

    Returns:
        Fit findings.
    """
    origin, destination = str(offer.get("origin", "")), str(offer.get("destination", ""))
    route = f"{origin} {destination}".lower()
    equipment = offer.get("equipment")
    return {
        "equipment_ok": None if not equipment else equipment in (carrier.get("equipment") or []),
        "preferred_lane": _lane_match(carrier, origin, destination),
        "avoid_hits": [a for a in carrier.get("avoid") or [] if str(a).lower() in route],
    }


def _economics(rate: float, loaded: float, deadhead: float, fee_pct: float, mpg: float,
               diesel: float | None) -> dict[str, Any]:
    """Compute rate per mile, fuel cost, dispatch fee, and carrier net.

    Args:
        rate: All-in rate in USD.
        loaded: Loaded miles.
        deadhead: Empty miles to pickup.
        fee_pct: Dispatch fee percent.
        mpg: Truck fuel economy.
        diesel: Diesel $/gal or None.

    Returns:
        Money figures rounded to cents.
    """
    total = loaded + deadhead
    fuel = round(total / mpg * diesel, 2) if diesel is not None else None
    fee = round(rate * fee_pct / 100, 2)
    return {
        "loaded_miles": loaded, "deadhead_miles": deadhead, "total_miles": round(total, 1),
        "rate_per_loaded_mile": round(rate / loaded, 2),
        "rate_per_total_mile": round(rate / total, 2),
        "dispatch_fee_usd": fee,
        "fuel_cost_usd": fuel,
        "carrier_net_after_fee_and_fuel_usd": round(rate - fee - fuel, 2) if fuel is not None else None,
    }


def load_evaluate(args: dict[str, Any], **kwargs: Any) -> str:
    """Tool handler: evaluate a load offer for one roster carrier.

    Args:
        args: {"carrier_phone", "rate_usd", "origin", "destination", "loaded_miles"?,
            "deadhead_miles"?, "equipment"?, "mpg"?}.
        **kwargs: Hermes context (unused).

    Returns:
        JSON with economics, fit, and a verdict: accept_range, counter, or pass.
    """
    try:
        doc = store.collection(store.CARRIERS).find_one({"phone": carriers.normalize_phone(str(args["carrier_phone"]))})
        rate = float(args["rate_usd"])
        mpg = float(args.get("mpg") or DEFAULT_MPG)
        given_miles = float(args["loaded_miles"]) if args.get("loaded_miles") else None
        deadhead = float(args.get("deadhead_miles") or 0)
    except (KeyError, ValueError, TypeError) as exc:
        return json.dumps({"error": f"need carrier_phone, a numeric rate_usd, and numeric miles ({exc})"})
    except (RuntimeError, pymongo.errors.PyMongoError) as exc:
        return json.dumps({"error": f"database unavailable: {exc}"})
    if doc is None:
        return json.dumps({"error": "carrier is not on this firm's roster"})
    if rate <= 0 or not MIN_MPG <= mpg <= MAX_MPG:
        return json.dumps({"error": f"rate_usd must be positive and mpg within {MIN_MPG}-{MAX_MPG}"})
    loaded, miles_source = (given_miles, "given") if given_miles else route_miles(
        str(args.get("origin", "")), str(args.get("destination", "")))
    diesel, diesel_source = diesel_price()
    result: dict[str, Any] = {"fit": _fit(doc, args), "sources": {"miles": miles_source, "diesel": diesel_source}}
    if not loaded:
        result["verdict"] = "unknown"
        return json.dumps(result)
    econ = _economics(rate, loaded, deadhead, float(doc.get("dispatch_fee_pct") or 0), mpg, diesel)
    result["economics"] = econ
    result.update(_verdict(doc, econ, result["fit"]))
    return json.dumps(result)


def _verdict(carrier: dict[str, Any], econ: dict[str, Any], fit: dict[str, Any]) -> dict[str, Any]:
    """Decide accept_range, counter, or pass against the carrier's rate floor.

    Args:
        carrier: Carrier document.
        econ: Economics from _economics.
        fit: Fit findings.

    Returns:
        Verdict fields, including the counter target when below floor.
    """
    if fit["equipment_ok"] is False or fit["avoid_hits"]:
        return {"verdict": "pass", "reason": "equipment mismatch or avoided area"}
    floor = carrier.get("rate_floor_per_mile")
    if not floor:
        return {"verdict": "unknown", "reason": "carrier has no rate_floor_per_mile; ask the dispatcher"}
    target = round(float(floor) * econ["total_miles"], 2)
    if econ["rate_per_total_mile"] >= float(floor):
        return {"verdict": "accept_range", "floor_per_mile": floor, "floor_total_usd": target}
    return {"verdict": "counter", "floor_per_mile": floor, "counter_at_least_usd": target}
