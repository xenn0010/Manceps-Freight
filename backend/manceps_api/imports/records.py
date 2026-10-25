"""Import documents and rows: statuses, counters, preview actions and lookups shared by the API, worker and undo.

`imports` holds one document per upload; `import_rows` one document per data row with its raw cells, the check
(values, errors, sensitive fields, natural key, duplicate and match) and, after a commit, its outcome and `before`
snapshot. Rows expire (TTL) ROWS_TTL after the upload, or after the commit once it ran.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from openpyxl.utils.datetime import CALENDAR_MAC_1904, CALENDAR_WINDOWS_1900

from manceps_core.mongo import Doc, MongoDb
from manceps_core.repo.fields import parse_id
from manceps_core.repo.store import get_by_id

from .header import as_list, as_map
from .validate import RowCheck

IMPORTS = "imports"
IMPORT_ROWS = "import_rows"
REF_TYPE = "import"
UPLOADED, MAPPED, COMMITTING, COMMITTED, FAILED, UNDOING, UNDONE = (
    "uploaded", "mapped", "committing", "committed", "failed", "undoing", "undone")
STRATEGIES = ("skip", "update", "merge")
DEFAULT_STRATEGY = "update"
ROWS_TTL = timedelta(days=30)
COMMIT_MAX_AGE = timedelta(days=7)
CHECK_STAT_KEYS = ("rows", "valid", "invalid", "duplicates_in_file", "needs_approval", "new", "existing")
OUTCOME_STAT_KEYS = ("created", "updated", "merged", "skipped", "rejected")
EPOCH_1904, EPOCH_1900 = "1904", "1900"


def empty_stats() -> dict[str, int]:
    """Return zeroed counters.

    Returns:
        Every stat key at 0.
    """
    return dict.fromkeys(CHECK_STAT_KEYS + OUTCOME_STAT_KEYS, 0)


def tally(stats: dict[str, int], check: RowCheck, allow_sensitive: bool) -> None:
    """Count one checked row.

    Args:
        stats: Counters (updated in place).
        check: The row's check.
        allow_sensitive: The uploader may set carrier terms directly.
    """
    stats["rows"] += 1
    if check.errors:
        stats["invalid"] += 1
        return
    stats["valid"] += 1
    if check.duplicate_of is not None:
        stats["duplicates_in_file"] += 1
    elif check.sensitive and not allow_sensitive:
        stats["needs_approval"] += 1
    elif check.match_id is not None:
        stats["existing"] += 1
    else:
        stats["new"] += 1


def preview_action(row: Mapping[str, Any], strategy: str, allow_sensitive: bool) -> tuple[str, str | None]:
    """Decide what a commit would do with a row.

    Args:
        row: Stored import row.
        strategy: skip, update or merge for rows matching an existing record.
        allow_sensitive: Whether carrier terms may be written directly.

    Returns:
        (create|update|merge|skip, reason or None).
    """
    if row.get("errors"):
        return "skip", "invalid"
    if row.get("duplicate_of") is not None:
        return "skip", "duplicate_in_file"
    if row.get("sensitive") and not allow_sensitive:
        return "skip", "approval_required"
    if row.get("match_id") is None:
        return "create", None
    return ("skip", "exists") if strategy == "skip" else (strategy, None)


def strategy_counts(stats: Mapping[str, int], strategy: str) -> dict[str, int]:
    """Count preview actions over the whole file from the stored counters.

    Args:
        stats: Import counters.
        strategy: Duplicate strategy.

    Returns:
        {create, update, merge, skip}.
    """
    counts = {"create": stats["new"], "update": 0, "merge": 0, "skip": 0}
    blocked = stats["invalid"] + stats["duplicates_in_file"] + stats["needs_approval"]
    if strategy == "skip":
        counts["skip"] = blocked + stats["existing"]
    else:
        counts[strategy] = stats["existing"]
        counts["skip"] = blocked
    return counts


def load_import(db: MongoDb, raw_id: Any) -> Doc:
    """Load an import of this firm.

    Args:
        db: Firm database.
        raw_id: Id text or ObjectId.

    Returns:
        The import.

    Raises:
        NotFound: If the id is malformed or unknown in this firm.
    """
    return get_by_id(db, IMPORTS, parse_id(raw_id, REF_TYPE), REF_TYPE)


def mapping_pairs(mapping: Mapping[str, str | None]) -> list[dict[str, str | None]]:
    """Store a mapping as pairs (column names may hold characters MongoDB keys cannot).

    Args:
        mapping: Column to field.

    Returns:
        [{column, field}] in column order.
    """
    return [{"column": column, "field": field} for column, field in mapping.items()]


def mapping_of(doc: Mapping[str, Any], key: str = "mapping") -> dict[str, str | None]:
    """Read a stored mapping.

    Args:
        doc: Import document.
        key: mapping or suggested_mapping.

    Returns:
        Column to field.
    """
    pairs = [as_map(pair) for pair in as_list(doc.get(key))]
    return {str(pair["column"]): pair.get("field") for pair in pairs}


def epoch_name(epoch: datetime | None) -> str | None:
    """Name a workbook epoch for storage.

    Args:
        epoch: Workbook epoch, or None for CSV and vCard.

    Returns:
        "1904", "1900" or None.
    """
    if epoch is None:
        return None
    return EPOCH_1904 if epoch == CALENDAR_MAC_1904 else EPOCH_1900


def epoch_of(doc: Mapping[str, Any]) -> datetime | None:
    """Read the stored workbook epoch.

    Args:
        doc: Import document.

    Returns:
        The epoch, or None.
    """
    name = doc.get("epoch")
    if name is None:
        return None
    return CALENDAR_MAC_1904 if name == EPOCH_1904 else CALENDAR_WINDOWS_1900


def outcome_stats(db: MongoDb, import_id: Any, stats: Mapping[str, int]) -> dict[str, int]:
    """Recount commit outcomes from the rows (exact even after a resumed job).

    Args:
        db: Firm database.
        import_id: Import id.
        stats: Current counters.

    Returns:
        Counters with created, updated, merged, skipped and rejected recounted.
    """
    counted = dict(stats)
    for action in OUTCOME_STAT_KEYS:
        counted[action] = db[IMPORT_ROWS].count_documents({"import_id": import_id, "outcome.action": action})
    return counted
