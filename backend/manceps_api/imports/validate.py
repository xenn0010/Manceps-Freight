"""Validate rows with the repositories' own rules and classify them: create, existing match, duplicate in the file.

A row is first read through the mapping (cells coerced to field kinds), then checked by the same `validate_new`
function the repository runs before a write, so a preview can never accept a row the commit would refuse for a data
rule. Money and contract terms are flagged (`sensitive`) rather than refused here: whether they need an approval
depends on who commits. Natural keys are normalized by the validators (E.164 phones, MC digits, lowercased email).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId

from manceps_core.mongo import Doc, MongoDb
from manceps_core.repo import brokers, carriers, contacts, fleet
from manceps_core.repo.errors import Invalid

from . import load_rows
from .coerce import CoerceError, coerce
from .errors import RowError
from .header import Cell, as_list
from .schema import CARRIER_PHONE, ENTITY_SPECS, NAME, NAME_PARTS, natural_key, normalize_key

DEFAULT_CONTACT_KIND = "other"
UTC_ZONE = "UTC"
LIVE = {"deleted_at": None}
KEY_FIELDS: Mapping[str, Mapping[str, str]] = {
    "carriers": {"phone": "phone"}, "drivers": {"phone": "phone"}, "brokers": {"mc": "mc_number"},
    "contacts": {"email": "emails", "phone": "phones"}, "loads": {},
}


@dataclass
class RowCheck:
    """The outcome of checking one row (stored with the row)."""

    values: dict[str, Any]
    errors: list[dict[str, str | None]]
    sensitive: list[str]
    key: str | None
    duplicate_of: int | None = None
    match_id: ObjectId | None = None

    def as_doc(self) -> Doc:
        """Render for storage.

        Returns:
            The fields stored on the import row.
        """
        return {"values": self.values, "errors": self.errors, "sensitive": self.sensitive, "key": self.key,
                "duplicate_of": self.duplicate_of, "match_id": self.match_id}


def read_row(entity: str, columns: Sequence[str], mapping: Mapping[str, str | None], cells: Sequence[Cell],
             epoch: datetime | None) -> tuple[dict[str, Any], list[RowError]]:
    """Read a row's mapped cells into field values (list fields collect every mapped column, in order).

    Args:
        entity: Entity name.
        columns: Column names.
        mapping: Column to field.
        cells: The row.
        epoch: Workbook epoch for serial dates.

    Returns:
        (values, coercion errors).
    """
    spec = ENTITY_SPECS[entity]
    values: dict[str, Any] = {}
    errors: list[RowError] = []
    for column, cell in zip(columns, cells, strict=False):
        field = mapping.get(column)
        if field is None:
            continue
        try:
            value = coerce(spec.fields[field].kind, cell, epoch)
        except CoerceError as exc:
            errors.append(RowError("invalid", str(exc), field))
            continue
        if value is None:
            continue
        if spec.fields[field].is_list:
            values.setdefault(field, []).extend(value)
        elif field not in values:
            values[field] = value
    return _with_name(values), errors


def _with_name(values: dict[str, Any]) -> dict[str, Any]:
    """Build `name` from first and last name when no name column is mapped.

    Args:
        values: Field values (first_name and last_name are removed).

    Returns:
        The values.
    """
    parts = [str(values.pop(part)) for part in NAME_PARTS if part in values]
    if parts and NAME not in values:
        values[NAME] = " ".join(parts)
    return values


def _resolve_carrier(db: MongoDb, values: dict[str, Any], cache: dict[str, Any]) -> dict[str, Any]:
    """Turn a driver's carrier phone into the id of a live carrier of this firm.

    Args:
        db: Firm database.
        values: Driver values.
        cache: Phone to carrier id (or None) already looked up in this run.

    Returns:
        The values with carrier_id instead of carrier_phone.

    Raises:
        Invalid: When the phone is not a US number or no live carrier has it.
    """
    raw = values.pop(CARRIER_PHONE, None)
    if raw is None:
        return values
    phone = normalize_key("phone", raw)
    if phone is None:
        raise Invalid(CARRIER_PHONE, "enter the carrier's 10-digit US phone number")
    if phone not in cache:
        found = db[carriers.CARRIERS].find_one({"phone": phone, **LIVE}, {"_id": 1})
        cache[phone] = None if found is None else str(found["_id"])
    if cache[phone] is None:
        raise Invalid(CARRIER_PHONE, "no carrier with this phone number in your firm")
    return {**values, "carrier_id": cache[phone]}


def repo_validate(db: MongoDb, entity: str, values: Mapping[str, Any]) -> dict[str, Any]:
    """Run the repository's own create-time validation for an entity.

    Args:
        db: Firm database.
        entity: Entity name.
        values: Field values.

    Returns:
        The validated, normalized fields (defaults included).

    Raises:
        Invalid: When a field breaks a data rule.
    """
    if entity == "carriers":
        return carriers.validate_new(values, True)
    if entity == "drivers":
        return fleet.validate_new(db, "driver", values)
    if entity == "brokers":
        return brokers.validate_new(values)
    return contacts.validate_new(db, "contact", {"kind": DEFAULT_CONTACT_KIND, **values})


def check_row(db: MongoDb, entity: str, values: dict[str, Any], errors: list[RowError],
              cache: dict[str, Any], zone: ZoneInfo | None = None) -> RowCheck:
    """Validate one row's values; only fields the file provided are kept (defaults apply at create time).

    Args:
        db: Firm database.
        entity: Entity name.
        values: Values from read_row.
        errors: Coercion errors from read_row.
        cache: Reference lookups (carriers for drivers; trucks, drivers and carriers for loads).
        zone: Firm timezone for load times without an offset (UTC when None).

    Returns:
        The check.
    """
    if errors:
        return RowCheck({}, [error.as_dict() for error in errors], [], None)
    try:
        if entity == "loads":
            kept = load_rows.load_values(db, values, zone or ZoneInfo(UTC_ZONE), cache)
            return RowCheck(kept, [], [], natural_key(entity, kept))
        provided = _resolve_carrier(db, dict(values), cache) if entity == "drivers" else dict(values)
        clean = repo_validate(db, entity, provided)
    except Invalid as exc:
        field = next((str(part) for part in exc.field if isinstance(part, str)), None)
        return RowCheck({}, [RowError("invalid", exc.message, field).as_dict()], [], None)
    kept = {name: clean[name] for name in provided if name in clean}
    sensitive = sorted(carriers.SENSITIVE_CARRIER_FIELDS & kept.keys()) if entity == "carriers" else []
    return RowCheck(kept, [], sensitive, natural_key(entity, kept))


def parse_error_check(error: RowError) -> RowCheck:
    """Turn a row the reader could not parse into an invalid check.

    Args:
        error: The reader's row error.

    Returns:
        The check.
    """
    return RowCheck({}, [error.as_dict()], [], None)


def find_matches(db: MongoDb, entity: str, keys: Sequence[str]) -> dict[str, ObjectId]:
    """Find live records matching natural keys, in one query per key kind.

    Args:
        db: Firm database.
        entity: Entity name.
        keys: Keys like "phone:+12145550100".

    Returns:
        Key to the matching record's id (the oldest one when several match).
    """
    if entity == "loads":
        return _load_matches(db, keys)
    spec = ENTITY_SPECS[entity]
    matches: dict[str, ObjectId] = {}
    for kind, field in KEY_FIELDS[entity].items():
        wanted = {key.split(":", 1)[1] for key in keys if key.startswith(f"{kind}:")}
        if not wanted:
            continue
        query = {field: {"$in": sorted(wanted)}, **LIVE}
        for doc in db[spec.collection].find(query, {field: 1}).sort([("_id", 1)]):
            stored = doc.get(field)
            found = as_list(stored) if isinstance(stored, list) else [stored]
            for value in found:
                if value in wanted:
                    matches.setdefault(f"{kind}:{value}", doc["_id"])
    return matches


def _load_matches(db: MongoDb, keys: Sequence[str]) -> dict[str, ObjectId]:
    """Find live loads by ref, or by (broker MC, broker ref).

    Args:
        db: Firm database.
        keys: Keys like "ref:L-2026-00001" or "broker:123456|VL-30981".

    Returns:
        Key to the matching load's id (the oldest when several match).
    """
    refs = sorted({key.removeprefix("ref:") for key in keys if key.startswith("ref:")})
    pairs = sorted({tuple(key.removeprefix("broker:").split("|", 1)) for key in keys if key.startswith("broker:")})
    conditions: list[dict[str, Any]] = [{"ref": {"$in": refs}}] if refs else []
    conditions += [{"broker_mc": mc, "broker_ref": ref} for mc, ref in pairs]
    matches: dict[str, ObjectId] = {}
    if not conditions:
        return matches
    for doc in db["loads"].find({"$or": conditions, **LIVE}, {"ref": 1, "broker_mc": 1, "broker_ref": 1}).sort(
            [("_id", 1)]):
        matches.setdefault(f"ref:{doc['ref']}", doc["_id"])
        if doc.get("broker_mc") and doc.get("broker_ref"):
            matches.setdefault(f"broker:{doc['broker_mc']}|{doc['broker_ref']}", doc["_id"])
    return matches


def find_match(db: MongoDb, entity: str, key: str | None) -> Doc | None:
    """Load the live record a natural key matches now.

    Args:
        db: Firm database.
        entity: Entity name.
        key: Natural key, or None.

    Returns:
        The record, or None.
    """
    if key is None:
        return None
    match = find_matches(db, entity, [key]).get(key)
    return None if match is None else db[ENTITY_SPECS[entity].collection].find_one({"_id": match})


def classify(db: MongoDb, entity: str, checks: Sequence[tuple[int, RowCheck]], seen: dict[str, int]) -> None:
    """Mark in-file duplicates (the first row with a key wins) and existing matches, in place.

    Args:
        db: Firm database.
        entity: Entity name.
        checks: (row number, check) in file order.
        seen: Key to the first row number holding it, carried across batches.
    """
    fresh: list[str] = []
    for row_no, check in checks:
        if check.errors or check.key is None:
            continue
        if check.key in seen:
            check.duplicate_of = seen[check.key]
            continue
        seen[check.key] = row_no
        fresh.append(check.key)
    matches = find_matches(db, entity, fresh)
    for _row_no, check in checks:
        if check.key is not None and check.duplicate_of is None and not check.errors:
            check.match_id = matches.get(check.key)

