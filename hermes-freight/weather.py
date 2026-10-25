"""Weather alerts along a route from the National Weather Service (api.weather.gov)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from . import tenant

NWS_ALERTS = "https://api.weather.gov/alerts/active"
CONTACT_ENV = "FREIGHT_CONTACT_EMAIL"
HTTP_TIMEOUT_SECONDS = 15
MAX_ALERTS = 25
STATE_PATTERN = re.compile(r"^[A-Z]{2}$")
SEVERE = frozenset({"Extreme", "Severe"})
# Events that matter to a truck even when NWS rates them below Severe.
TRUCK_EVENTS = ("Winter", "Blizzard", "Ice", "Wind", "Dust", "Flood", "Tornado", "Fog", "Snow", "Freez")


def _user_agent() -> str:
    """Build the User-Agent NWS requires, with the firm's contact when configured.

    Returns:
        User-Agent header value.
    """
    contact = tenant.secret(CONTACT_ENV) or "contact-unset"
    return f"hermes-freight/0.1 ({contact})"


def fetch_alerts(states: list[str]) -> list[dict[str, Any]]:
    """Fetch active NWS alerts for the given states.

    Args:
        states: Two-letter state codes.

    Returns:
        Alert property dicts.

    Raises:
        urllib.error.URLError: On network or HTTP errors.
        ValueError: If the response is not JSON.
    """
    query = urllib.parse.urlencode({"area": ",".join(states)})
    request = urllib.request.Request(f"{NWS_ALERTS}?{query}",
                                     headers={"User-Agent": _user_agent(), "Accept": "application/geo+json"})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return [f.get("properties") or {} for f in payload.get("features") or []]


def _relevant(alert: dict[str, Any]) -> bool:
    """Keep severe alerts and any alert type that affects driving.

    Args:
        alert: NWS alert properties.

    Returns:
        Whether a dispatcher should see it.
    """
    event = str(alert.get("event", ""))
    return alert.get("severity") in SEVERE or any(word in event for word in TRUCK_EVENTS)


def weather_alerts(args: dict[str, Any], **kwargs: Any) -> str:
    """Tool handler: active driving-relevant weather alerts for states on a route.

    Args:
        args: {"states": ["TX", "OK", ...]}.
        **kwargs: Hermes context (unused).

    Returns:
        JSON with alerts, or an error. A failed lookup never reports "no alerts".
    """
    states = sorted({str(s).strip().upper() for s in args.get("states") or []})
    bad = [s for s in states if not STATE_PATTERN.fullmatch(s)]
    if not states or bad:
        return json.dumps({"error": f"give two-letter state codes; invalid: {bad}" if bad else "give states"})
    try:
        alerts = [a for a in fetch_alerts(states) if _relevant(a)]
    except (urllib.error.URLError, ValueError, TimeoutError) as exc:
        return json.dumps({"status": "unknown", "error": f"weather lookup failed: {exc}"})
    alerts.sort(key=lambda a: (a.get("severity") not in SEVERE, str(a.get("onset") or "")))
    out = [{"event": a.get("event"), "severity": a.get("severity"), "area": a.get("areaDesc"),
            "headline": a.get("headline"), "onset": a.get("onset"), "ends": a.get("ends") or a.get("expires")}
           for a in alerts[:MAX_ALERTS]]
    return json.dumps({"status": "ok", "states": states, "count": len(alerts), "alerts": out})
