"""Load public FMCSA reference data into the shared `freight_reference` database.

Sources (data.transportation.gov, public US government records):
  az4n-8mr2  Company Census File: active companies with broker classification
  qh9u-swkp  ActPendInsur: active and pending insurance filings; BMC-84/85 = broker bond/trust

Run as the operator (it writes with the operator's MONGODB_URI):
    python3 load_reference.py            # full sync
    python3 load_reference.py --limit 1000   # smoke test
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pymongo
import pymongo.errors
from pymongo import ReplaceOne
from pymongo.database import Database

SODA = "https://data.transportation.gov"
CENSUS = "az4n-8mr2"
INSURANCE = "qh9u-swkp"
DB_NAME = "freight_reference"
PAGE_SIZE = 20000
WRITE_BATCH = 2000
HTTP_TIMEOUT_SECONDS = 120
HTTP_RETRIES = 4
RETRY_BACKOFF_SECONDS = 5
USER_AGENT = "hermes-freight reference loader"
HERMES_ENV = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / ".env"

BROKER_FIELDS = ("dot_number", "legal_name", "dba_name", "phy_street", "phy_city", "phy_state", "phy_zip",
                 "phone", "email_address", "status_code", "carship", "add_date", "mcs150_date",
                 "docket1prefix", "docket1", "docket1_status_code", "docket2prefix", "docket2",
                 "docket2_status_code", "docket3prefix", "docket3", "docket3_status_code")
BROKER_WHERE = "carship like '%B%' AND status_code='A'"
BOND_WHERE = "ins_form_code in('84','85')"
BOND_FORMS = {"84": "BMC-84 surety bond", "85": "BMC-85 trust fund"}


def get_json(url: str) -> Any:
    """GET JSON with retries for transient failures.

    Args:
        url: Absolute URL.

    Returns:
        Decoded JSON.

    Raises:
        urllib.error.URLError: When every attempt fails.
    """
    for attempt in range(HTTP_RETRIES):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == HTTP_RETRIES - 1:
                raise
            print(f"  retry {attempt + 1} after {exc}", file=sys.stderr)
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
    raise RuntimeError("unreachable")


def pages(dataset: str, where: str, select: str | None, limit: int | None) -> Iterator[list[dict[str, Any]]]:
    """Yield pages of rows from a Socrata dataset in a stable order.

    Args:
        dataset: Socrata dataset id.
        where: SoQL filter.
        select: SoQL select list, or None for all columns.
        limit: Stop after this many rows (None for all).

    Yields:
        Lists of row dicts.
    """
    offset = 0
    while limit is None or offset < limit:
        size = PAGE_SIZE if limit is None else min(PAGE_SIZE, limit - offset)
        params = {"$where": where, "$order": ":id", "$limit": size, "$offset": offset}
        if select:
            params["$select"] = select
        rows = get_json(f"{SODA}/resource/{dataset}.json?{urllib.parse.urlencode(params)}")
        if not rows:
            return
        yield rows
        offset += len(rows)


def _digits(value: Any) -> str:
    """Strip everything but digits and leading zeros.

    Args:
        value: Raw identifier.

    Returns:
        Normalized digit string ("" when none).
    """
    return re.sub(r"\D", "", str(value or "")).lstrip("0")


def broker_doc(row: dict[str, Any], synced_at: datetime) -> dict[str, Any] | None:
    """Map a census row to a broker reference document.

    Args:
        row: Census row.
        synced_at: Sync timestamp.

    Returns:
        Document, or None when the row has no DOT number.
    """
    dot = _digits(row.get("dot_number"))
    if not dot:
        return None
    dockets = [{"prefix": row.get(f"docket{i}prefix"), "number": _digits(row.get(f"docket{i}")),
                "status": row.get(f"docket{i}_status_code")} for i in (1, 2, 3) if row.get(f"docket{i}")]
    return {
        "_id": dot, "dot_number": dot, "legal_name": row.get("legal_name"), "dba_name": row.get("dba_name"),
        "mc_numbers": [d["number"] for d in dockets if d["prefix"] == "MC" and d["number"]],
        "dockets": dockets, "street": row.get("phy_street"), "city": row.get("phy_city"),
        "state": row.get("phy_state"), "zip": row.get("phy_zip"), "phone": row.get("phone"),
        "email": row.get("email_address"), "classification": row.get("carship"),
        "added": row.get("add_date"), "mcs150_date": row.get("mcs150_date"),
        "source": CENSUS, "synced_at": synced_at,
    }


def bond_doc(row: dict[str, Any], synced_at: datetime) -> dict[str, Any] | None:
    """Map an insurance row to a broker bond document.

    Args:
        row: ActPendInsur row.
        synced_at: Sync timestamp.

    Returns:
        Document, or None when the row has no docket.
    """
    docket = str(row.get("docket_number") or "")
    number = _digits(docket)
    if not number:
        return None
    form = str(row.get("ins_form_code"))
    key = f"{docket}|{form}|{row.get('policy_no')}|{row.get('effective_date')}"
    return {
        "_id": key, "docket": docket, "mc_number": number if docket.startswith("MC") else None,
        "dot_number": _digits(row.get("dot_number")), "form": form, "form_name": BOND_FORMS.get(form),
        "kind": row.get("mod_col_1"), "surety": row.get("name_company"), "policy_no": row.get("policy_no"),
        "transaction_date": row.get("trans_date"), "effective_date": row.get("effective_date"),
        "cancellation_effective_date": row.get("cancl_effective_date"), "source": INSURANCE,
        "synced_at": synced_at,
    }


def dataset_updated(dataset: str) -> str | None:
    """Return when FMCSA last updated a dataset's rows.

    Args:
        dataset: Socrata dataset id.

    Returns:
        ISO timestamp, or None when unavailable.
    """
    try:
        stamp = get_json(f"{SODA}/api/views/{dataset}.json").get("rowsUpdatedAt")
    except (urllib.error.URLError, ValueError, AttributeError):
        return None
    return datetime.fromtimestamp(stamp, UTC).isoformat() if stamp else None


def sync(db: Database, name: str, dataset: str, where: str, select: str | None,
         mapper: Any, limit: int | None) -> int:
    """Upsert one dataset into a collection and drop rows that left the source.

    Args:
        db: Reference database.
        name: Collection name.
        dataset: Socrata dataset id.
        where: SoQL filter.
        select: SoQL select list.
        mapper: Row -> document function taking (row, synced_at).
        limit: Row cap for smoke tests; pruning is skipped when set.

    Returns:
        Number of documents written.
    """
    synced_at = datetime.now(UTC)
    written = 0
    for rows in pages(dataset, where, select, limit):
        ops = [ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in (mapper(r, synced_at) for r in rows) if d]
        for start in range(0, len(ops), WRITE_BATCH):
            db[name].bulk_write(ops[start:start + WRITE_BATCH], ordered=False)
        written += len(ops)
        print(f"  {name}: {written} rows", flush=True)
    if limit is None and written:
        removed = db[name].delete_many({"synced_at": {"$lt": synced_at}}).deleted_count
        print(f"  {name}: removed {removed} rows no longer in the source")
    db["sync_meta"].replace_one({"_id": name}, {
        "_id": name, "dataset": dataset, "source_updated": dataset_updated(dataset), "rows": written,
        "synced_at": synced_at, "complete": limit is None,
    }, upsert=True)
    return written


def ensure_indexes(db: Database) -> None:
    """Create lookup indexes for the reference collections.

    Args:
        db: Reference database.
    """
    db["brokers"].create_index("mc_numbers")
    db["brokers"].create_index("state")
    db["brokers"].create_index([("legal_name", pymongo.TEXT), ("dba_name", pymongo.TEXT)], name="name_text")
    db["broker_bonds"].create_index("mc_number")
    db["broker_bonds"].create_index("dot_number")


def operator_uri() -> str:
    """Read the operator's MONGODB_URI from the environment or Hermes .env.

    Returns:
        Connection string.

    Raises:
        RuntimeError: If it is not configured.
    """
    uri = os.environ.get("MONGODB_URI", "")
    if not uri and HERMES_ENV.is_file():
        for line in HERMES_ENV.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == "MONGODB_URI":
                uri = value.strip().strip("'\"")
    if not uri:
        raise RuntimeError("MONGODB_URI not set")
    return uri


def main() -> int:
    """Parse arguments and run the sync.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description="Load FMCSA broker and bond reference data")
    parser.add_argument("--limit", type=int, default=None, help="rows per dataset (smoke test; no pruning)")
    args = parser.parse_args()
    try:
        client: pymongo.MongoClient = pymongo.MongoClient(operator_uri(), serverSelectionTimeoutMS=20000)
        db = client[DB_NAME]
        ensure_indexes(db)
        brokers = sync(db, "brokers", CENSUS, BROKER_WHERE, ",".join(BROKER_FIELDS), broker_doc, args.limit)
        bonds = sync(db, "broker_bonds", INSURANCE, BOND_WHERE, None, bond_doc, args.limit)
    except (RuntimeError, urllib.error.URLError, pymongo.errors.PyMongoError) as exc:
        print(f"reference sync failed: {exc}", file=sys.stderr)
        return 1
    print(f"done: {brokers} brokers, {bonds} bond filings in {DB_NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
