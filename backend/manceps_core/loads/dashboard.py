"""Weekly dashboard: revenue per day this week and last week, loads booked and average rate per mile.

A load counts in the week and on the day (in the firm's timezone) it was booked (`booked_at`), when its status is
booked or later (contracted: booked through paid). Revenue is the load's `rate_cents`. The average rate per mile is
total revenue divided by total loaded miles over this week's loads that have miles, rounded half up. Weeks start on
Monday in the firm's timezone, so a week can be 167 or 169 hours long across a daylight-saving change.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from ..mongo import MongoDb
from . import machine, money

DAYS_PER_WEEK = 7
MONDAY = 0
LOADS = "loads"


def week_start_of(moment: datetime, zone: ZoneInfo) -> date:
    """Find the Monday of the firm-local week holding a moment.

    Args:
        moment: Aware datetime.
        zone: Firm timezone.

    Returns:
        That Monday.
    """
    local = moment.astimezone(zone).date()
    return local - timedelta(days=local.weekday())


def _local_midnight(day: date, zone: ZoneInfo) -> datetime:
    """Return the start of a firm-local day.

    Args:
        day: Local date.
        zone: Firm timezone.

    Returns:
        Aware datetime at local midnight.
    """
    return datetime.combine(day, time.min, tzinfo=zone)


def _week(loads: Iterable[Mapping[str, Any]], start: date, zone: ZoneInfo) -> dict[str, Any]:
    """Total one week's loads by local booking day.

    Args:
        loads: Contracted loads booked in or near the week.
        start: The week's Monday.
        zone: Firm timezone.

    Returns:
        days (7 entries), revenue_cents, loads_booked, loaded_miles and miles_revenue_cents.
    """
    revenue = [0] * DAYS_PER_WEEK
    booked = [0] * DAYS_PER_WEEK
    miles, miles_revenue = 0.0, 0
    for load in loads:
        offset = (load["booked_at"].astimezone(zone).date() - start).days
        if not 0 <= offset < DAYS_PER_WEEK:
            continue
        rate = int(load.get("rate_cents") or 0)
        revenue[offset] += rate
        booked[offset] += 1
        loaded = load.get("loaded_miles")
        if isinstance(loaded, int | float) and not isinstance(loaded, bool) and loaded > 0:
            miles += float(loaded)
            miles_revenue += rate
    days = [{"date": start + timedelta(days=offset), "revenue_cents": revenue[offset], "loads_booked": booked[offset]}
            for offset in range(DAYS_PER_WEEK)]
    return {"days": days, "revenue_cents": sum(revenue), "loads_booked": sum(booked), "loaded_miles": round(miles, 1),
            "miles_revenue_cents": miles_revenue}


def summary(db: MongoDb, week_start: date, zone: ZoneInfo) -> dict[str, Any]:
    """Build the weekly summary for a firm-local week and the week before it.

    Args:
        db: Firm database.
        week_start: The week's Monday (firm-local).
        zone: Firm timezone.

    Returns:
        week_start, timezone, this_week, last_week, revenue_change_cents and avg_rate_per_mile_cents.

    Raises:
        ValueError: If week_start is not a Monday.
    """
    if week_start.weekday() != MONDAY:
        raise ValueError("week_start must be a Monday")
    last_start = week_start - timedelta(days=DAYS_PER_WEEK)
    window = {"$gte": _local_midnight(last_start, zone),
              "$lt": _local_midnight(week_start + timedelta(days=DAYS_PER_WEEK), zone)}
    query = {"booked_at": window, "status": {"$in": sorted(machine.CONTRACTED)}, "deleted_at": None}
    loads = list(db[LOADS].find(query, {"booked_at": 1, "rate_cents": 1, "loaded_miles": 1}))
    this_week, last_week = _week(loads, week_start, zone), _week(loads, last_start, zone)
    per_mile = money.per_mile_cents(this_week.pop("miles_revenue_cents"), this_week["loaded_miles"])
    last_week.pop("miles_revenue_cents")
    return {"week_start": week_start, "timezone": zone.key, "this_week": this_week, "last_week": last_week,
            "revenue_change_cents": this_week["revenue_cents"] - last_week["revenue_cents"],
            "avg_rate_per_mile_cents": per_mile}
