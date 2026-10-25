"""Public FMCSA reference data: broker lookup and BMC-84/85 bond status.

Reads the shared `freight_reference` database loaded by deploy/load_reference.py from
data.transportation.gov. Read-only; a missing or unreachable reference is reported as
unknown, never as a pass.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

import pymongo.errors
from pymongo.database import Database

from . import tenant

DB_NAME = "freight_reference"
MAX_RESULTS = 10
DATE_FORMAT = "%m/%d/%Y"
PASS, FAIL, UNKNOWN = "pass", "fail", "unknown"


def _db() -> Database:
    """Return the shared reference database.

    Returns:
        Database handle.
    """
    return tenant.shared_database(DB_NAME)


def _active(bond: dict[str, Any], today: datetime) -> bool | None:
    """Decide whether a bond filing is still in force.

    Args:
        bond: broker_bonds document.
        today: Current UTC time.

    Returns:
        True with no cancellation or a future one, False once it has passed, None when
        the cancellation date cannot be read.
    """
    cancel = bond.get("cancellation_effective_date")
    if not cancel:
        return True
    try:
        return datetime.strptime(cancel, DATE_FORMAT).replace(tzinfo=UTC) > today
    except ValueError:
        return None


def bond_status(mc: str, dot: str) -> dict[str, Any]:
    """Check FMCSA's active/pending insurance filings for a broker bond or trust.

    Args:
        mc: MC docket digits ("" if unknown).
        dot: USDOT digits ("" if unknown).

    Returns:
        A broker_check-style result for the "bond" check.
    """
    keys = [{"mc_number": mc.lstrip("0")}] if mc else []
    keys += [{"dot_number": dot.lstrip("0")}] if dot else []
    if not keys:
        return {"check": "bond", "status": UNKNOWN, "detail": "no MC or DOT to look up"}
    try:
        db = _db()
        meta = db["sync_meta"].find_one({"_id": "broker_bonds"}) or {}
        if not meta.get("complete"):
            return {"check": "bond", "status": UNKNOWN, "detail": "bond reference data not fully loaded"}
        bonds = list(db["broker_bonds"].find({"$or": keys}, {"_id": 0, "synced_at": 0}))
    except (RuntimeError, pymongo.errors.PyMongoError) as exc:
        return {"check": "bond", "status": UNKNOWN, "detail": f"bond lookup failed: {exc}"}
    source = f"FMCSA ActPendInsur, updated {meta.get('source_updated')}"
    today = datetime.now(UTC)
    active = [b for b in bonds if _active(b, today) is True]
    if active:
        best = active[0]
        return {"check": "bond", "status": PASS, "detail": f"{best.get('form_name')} with {best.get('surety')}",
                "filings": active, "source": source}
    unreadable = [b for b in bonds if _active(b, today) is None]
    if unreadable:
        return {"check": "bond", "status": UNKNOWN, "detail": "bond cancellation date unreadable",
                "filings": unreadable, "source": source}
    detail = "all bond filings cancelled" if bonds else "no BMC-84/85 bond or trust on file"
    return {"check": "bond", "status": FAIL, "detail": detail, "source": source}


def _summary(doc: dict[str, Any]) -> dict[str, Any]:
    """Trim a reference broker document for tool output.

    Args:
        doc: brokers document.

    Returns:
        Compact broker record.
    """
    return {k: doc.get(k) for k in ("dot_number", "mc_numbers", "legal_name", "dba_name", "city", "state")}


def broker_search(args: dict[str, Any], **kwargs: Any) -> str:
    """Tool handler: find FMCSA-registered brokers by MC, DOT, or name.

    Args:
        args: {"mc_number"} or {"dot_number"} or {"name", "state"?}.
        **kwargs: Hermes context (unused).

    Returns:
        JSON with matching brokers (public FMCSA records) and data freshness.
    """
    mc = re.sub(r"\D", "", str(args.get("mc_number", ""))).lstrip("0")
    dot = re.sub(r"\D", "", str(args.get("dot_number", ""))).lstrip("0")
    name = str(args.get("name", "")).strip()
    if mc:
        query: dict[str, Any] = {"mc_numbers": mc}
    elif dot:
        query = {"_id": dot}
    elif len(name) >= 3:
        query = {"$text": {"$search": name}}
    else:
        return json.dumps({"error": "give mc_number, dot_number, or a name of at least 3 characters"})
    if args.get("state") and not (mc or dot):
        query["state"] = str(args["state"]).strip().upper()
    try:
        db = _db()
        meta = db["sync_meta"].find_one({"_id": "brokers"}) or {}
        cursor = db["brokers"].find(query).limit(MAX_RESULTS)
        found = [_summary(d) for d in cursor]
    except (RuntimeError, pymongo.errors.PyMongoError) as exc:
        return json.dumps({"error": f"reference data unavailable: {exc}"})
    return json.dumps({"results": found, "count": len(found),
                       "source": f"FMCSA Company Census, updated {meta.get('source_updated')}",
                       "note": "public registry data; a listed phone number is not consent to call or text"})
