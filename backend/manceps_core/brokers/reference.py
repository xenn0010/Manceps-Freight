"""Public FMCSA reference data in the shared, read-only `freight_reference` database (ported from hermes-freight).

Bond status fails closed: missing, partial or unreadable data is `unknown`, never `pass`. Broker search matches MC,
DOT, or a literal, case-insensitive name fragment (legal or DBA name).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pymongo.errors import PyMongoError

from ..mongo import Doc, MongoDb
from ..repo import fields
from ..repo.errors import Invalid

REFERENCE_DB = "freight_reference"
MAX_RESULTS = 10
MIN_NAME_CHARS = 3
DATE_FORMAT = "%m/%d/%Y"
PASS, FAIL, UNKNOWN = "pass", "fail", "unknown"
SUMMARY_FIELDS = ("dot_number", "mc_numbers", "legal_name", "dba_name", "city", "state")
CONSENT_NOTE = "public registry data; a listed phone number is not consent to call or text"


def _active(bond: Doc, today: datetime) -> bool | None:
    """Decide whether a bond filing is still in force.

    Args:
        bond: broker_bonds document.
        today: Current UTC time.

    Returns:
        True with no cancellation or a future one, False once it has passed, None when unreadable.
    """
    cancel = bond.get("cancellation_effective_date")
    if not cancel:
        return True
    try:
        return datetime.strptime(str(cancel), DATE_FORMAT).replace(tzinfo=UTC) > today
    except ValueError:
        return None


def bond_status(db: MongoDb, mc: str, dot: str, now: datetime) -> dict[str, Any]:
    """Check FMCSA's active/pending insurance filings for a broker bond or trust (BMC-84/85).

    Args:
        db: Reference database.
        mc: MC docket digits ("" if unknown).
        dot: USDOT digits ("" if unknown).
        now: Current UTC time.

    Returns:
        The "bond" check result.
    """
    keys = [{"mc_number": mc.lstrip("0")}] if mc else []
    keys += [{"dot_number": dot.lstrip("0")}] if dot else []
    if not keys:
        return {"check": "bond", "status": UNKNOWN, "detail": "no MC or DOT to look up"}
    try:
        meta = db["sync_meta"].find_one({"_id": "broker_bonds"}) or {}
        if not meta.get("complete"):
            return {"check": "bond", "status": UNKNOWN, "detail": "bond reference data not fully loaded"}
        bonds = list(db["broker_bonds"].find({"$or": keys}, {"_id": 0, "synced_at": 0}))
    except PyMongoError as exc:
        return {"check": "bond", "status": UNKNOWN, "detail": f"bond lookup failed: {type(exc).__name__}"}
    source = f"FMCSA ActPendInsur, updated {meta.get('source_updated')}"
    active = [bond for bond in bonds if _active(bond, now) is True]
    if active:
        best = active[0]
        return {"check": "bond", "status": PASS, "detail": f"{best.get('form_name')} with {best.get('surety')}",
                "filings": active, "source": source}
    unreadable = [bond for bond in bonds if _active(bond, now) is None]
    if unreadable:
        return {"check": "bond", "status": UNKNOWN, "detail": "bond cancellation date unreadable",
                "filings": unreadable, "source": source}
    detail = "all bond filings cancelled" if bonds else "no BMC-84/85 bond or trust on file"
    return {"check": "bond", "status": FAIL, "detail": detail, "source": source}


def _query(mc: str | None, dot: str | None, name: str | None, state: str | None) -> dict[str, Any]:
    """Build the reference query from the search inputs.

    Args:
        mc: MC number in any format.
        dot: DOT number in any format.
        name: Name fragment.
        state: Two-letter state, only used with a name.

    Returns:
        The MongoDB filter.

    Raises:
        Invalid: When no usable search input is given.
    """
    if mc:
        return {"mc_numbers": fields.digits("mc", mc).lstrip("0")}
    if dot:
        return {"_id": fields.digits("dot", dot).lstrip("0")}
    term = (name or "").strip()
    if len(term) < MIN_NAME_CHARS:
        raise Invalid("q", f"give mc, dot, or a name of at least {MIN_NAME_CHARS} characters")
    query: dict[str, Any] = {"$or": [{"legal_name": fields.contains(term)}, {"dba_name": fields.contains(term)}]}
    if state:
        query["state"] = fields.state("state", state)
    return query


def search_brokers(db: MongoDb, mc: str | None = None, dot: str | None = None, name: str | None = None,
                   state: str | None = None) -> dict[str, Any]:
    """Find FMCSA-registered brokers by MC, DOT, or name.

    Args:
        db: Reference database.
        mc: MC number.
        dot: DOT number.
        name: Name fragment (at least MIN_NAME_CHARS).
        state: Optional two-letter state for name searches.

    Returns:
        {items, count, source, note}.

    Raises:
        Invalid: When no usable search input is given.
        pymongo.errors.PyMongoError: If the reference database is unreachable.
    """
    query = _query(mc, dot, name, state)
    meta = db["sync_meta"].find_one({"_id": "brokers"}) or {}
    items = [{key: doc.get(key) for key in SUMMARY_FIELDS} for doc in db["brokers"].find(query).limit(MAX_RESULTS)]
    return {"items": items, "count": len(items),
            "source": f"FMCSA Company Census, updated {meta.get('source_updated')}", "note": CONSENT_NOTE}


def legal_name_for_mc(db: MongoDb, mc: str) -> str | None:
    """Look up a broker's registered name by MC (best effort; failures return None).

    Args:
        db: Reference database.
        mc: MC digits.

    Returns:
        The legal name, or None when unknown or the reference is unreachable.
    """
    try:
        doc = db["brokers"].find_one({"mc_numbers": mc.lstrip("0")}, {"legal_name": 1})
    except PyMongoError:
        return None
    name = (doc or {}).get("legal_name")
    return str(name) if name else None
