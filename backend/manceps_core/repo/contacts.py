"""Contacts (broker reps, shippers, receivers...) and facilities (shipper and receiver locations).

Contact phones and emails are normalized lists; consent is never written here (it belongs to the consent ledger).
Facilities store their location as GeoJSON `geo` for the 2dsphere index and reference contacts of the same firm.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from typing import Any, cast

from bson import ObjectId

from ..mongo import Doc, MongoDb
from . import fields
from .errors import Invalid, NotFound
from .store import WriteContext, get_by_id, insert, list_live, soft_delete, update

CONTACTS = "contacts"
FACILITIES = "facilities"
CONTACT_KINDS = ("broker_contact", "shipper", "receiver", "facility", "other")
CONTACT_SOURCES = ("manual", "import", "vcard", "google", "agent")
DEFAULT_SOURCE = "manual"
ZIP_PATTERN = re.compile(r"^[0-9]{5}(-[0-9]{4})?$")
MAX_LATITUDE = 90.0
MAX_LONGITUDE = 180.0
HOURS_MAX = 500

Rule = Callable[[str, Any], Any]


def _zip(field: str, value: Any) -> str:
    """Validate a US ZIP or ZIP+4.

    Args:
        field: Field name.
        value: Raw value.

    Returns:
        The ZIP.

    Raises:
        Invalid: If malformed.
    """
    code = str(value).strip()
    if not ZIP_PATTERN.fullmatch(code):
        raise Invalid(field, "a ZIP code is 5 digits or ZIP+4")
    return code


def _coordinate(field: str, value: Any) -> float:
    """Read one finite numeric coordinate.

    Args:
        field: Field name.
        value: Raw value.

    Returns:
        The coordinate.

    Raises:
        Invalid: If it is not a finite number.
    """
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise Invalid(field, f"{field} needs numeric lat and lng")
    return float(value)


def _geo(field: str, value: Any) -> dict[str, Any]:
    """Turn {lat, lng} into a GeoJSON point.

    Args:
        field: Field name.
        value: Mapping with lat and lng.

    Returns:
        {"type": "Point", "coordinates": [lng, lat]}.

    Raises:
        Invalid: If either coordinate is missing or out of range.
    """
    empty: Mapping[str, Any] = {}
    point = cast(Mapping[str, Any], value) if isinstance(value, Mapping) else empty
    lat, lng = _coordinate(field, point.get("lat")), _coordinate(field, point.get("lng"))
    if abs(lat) > MAX_LATITUDE or abs(lng) > MAX_LONGITUDE:
        raise Invalid(field, f"{field} is out of range")
    return {"type": "Point", "coordinates": [lng, lat]}


def _contact_ids(db: MongoDb) -> Rule:
    """Build a rule checking every id names a live contact of this firm.

    Args:
        db: Firm database.

    Returns:
        The rule, returning id texts.
    """

    def rule(field: str, value: Any) -> list[str]:
        ids = fields.text_list(field, value)
        for raw in ids:
            try:
                get_by_id(db, CONTACTS, raw, "contact")
            except NotFound as exc:
                raise Invalid(field, "no such contact in this firm") from exc
        return list(dict.fromkeys(ids))

    return rule


def _contact_rules(_db: MongoDb) -> Mapping[str, Rule]:
    """Rules for contact fields.

    Args:
        _db: Firm database (unused; contacts reference nothing).

    Returns:
        Field name to rule.
    """
    return {"kind": lambda field, value: fields.choice(field, value, CONTACT_KINDS), "name": fields.text,
            "company": fields.text, "title": fields.text, "phones": fields.phones, "emails": fields.emails,
            "tags": fields.tags, "source": lambda field, value: fields.choice(field, value, CONTACT_SOURCES)}


def _facility_rules(db: MongoDb) -> Mapping[str, Rule]:
    """Rules for facility fields (`location` is stored as `geo`).

    Args:
        db: Firm database.

    Returns:
        Field name to rule.
    """
    return {"name": fields.text, "address": fields.text, "city": fields.text, "state": fields.state, "zip": _zip,
            "location": _geo, "hours": lambda field, value: fields.text(field, value, HOURS_MAX),
            "detention_notes": lambda field, value: fields.text(field, value, fields.MAX_NOTE_CHARS),
            "contact_ids": _contact_ids(db)}


KINDS: Mapping[str, tuple[str, Callable[[MongoDb], Mapping[str, Rule]], frozenset[str]]] = {
    "contact": (CONTACTS, _contact_rules, frozenset({"kind", "name"})),
    "facility": (FACILITIES, _facility_rules, frozenset({"name"})),
}


def _validate(db: MongoDb, kind: str, changes: Mapping[str, Any]) -> dict[str, Any]:
    """Validate fields of a contact or facility; None is kept (remove) unless required.

    Args:
        db: Firm database.
        kind: contact or facility.
        changes: Proposed values.

    Returns:
        Cleaned values, with a facility `location` renamed to `geo`.

    Raises:
        Invalid: On unknown fields, removing a required field, or bad values.
    """
    _collection, build, required = KINDS[kind]
    rules = build(db)
    clean: dict[str, Any] = {}
    for name, value in changes.items():
        rule = rules.get(name)
        if rule is None:
            raise Invalid(name, "this field cannot be written here")
        if value is None and name in required:
            raise Invalid(name, f"{name} is required")
        clean["geo" if name == "location" else name] = None if value is None else rule(name, value)
    return clean


def validate_new(db: MongoDb, kind: str, values: Mapping[str, Any]) -> dict[str, Any]:
    """Apply every rule a new contact or facility must pass, without writing (imports preview rows with it).

    Args:
        db: Firm database.
        kind: contact or facility.
        values: Proposed fields.

    Returns:
        The validated fields (without defaults; a facility `location` becomes `geo`).

    Raises:
        Invalid: On missing required fields or bad values.
    """
    required = KINDS[kind][2]
    missing = [name for name in sorted(required) if values.get(name) is None]
    if missing:
        raise Invalid(missing[0], f"{missing[0]} is required")
    return {key: value for key, value in _validate(db, kind, values).items() if value is not None}


def create_record(db: MongoDb, ctx: WriteContext, kind: str, values: Mapping[str, Any],
                  record_id: ObjectId | None = None) -> Doc:
    """Add a contact or facility.

    Args:
        db: Firm database.
        ctx: Writer.
        kind: contact or facility.
        values: Proposed fields.
        record_id: Reserved id (imports), or None for a new one.

    Returns:
        The stored record.

    Raises:
        Invalid: On missing required fields or bad values.
        DuplicateKeyError: If record_id is already taken.
    """
    clean = validate_new(db, kind, values)
    defaults: dict[str, Any] = {"tags": [], "phones": [], "emails": [], "source": DEFAULT_SOURCE} \
        if kind == "contact" else {"contact_ids": []}
    return insert(db, ctx, KINDS[kind][0], kind, {**defaults, **clean}, None, record_id)


def get_record(db: MongoDb, kind: str, record_id: Any) -> Doc:
    """Load a live contact or facility.

    Args:
        db: Firm database.
        kind: contact or facility.
        record_id: Id text.

    Returns:
        The record.

    Raises:
        NotFound: If absent, malformed or deleted.
    """
    return get_by_id(db, KINDS[kind][0], record_id, kind)


def update_record(db: MongoDb, ctx: WriteContext, kind: str, record_id: Any, changes: Mapping[str, Any]) -> Doc:
    """Change a contact or facility (None removes an optional field).

    Args:
        db: Firm database.
        ctx: Writer.
        kind: contact or facility.
        record_id: Id text.
        changes: Proposed fields.

    Returns:
        The updated record.

    Raises:
        NotFound: If the record is not live.
        Invalid: On bad values or an empty change.
    """
    if not changes:
        raise Invalid("body", "send at least one field to change")
    current = get_record(db, kind, record_id)
    return update(db, ctx, KINDS[kind][0], kind, current, _validate(db, kind, changes))


def delete_record(db: MongoDb, ctx: WriteContext, kind: str, record_id: Any) -> Doc:
    """Soft-delete a contact or facility.

    Args:
        db: Firm database.
        ctx: Writer.
        kind: contact or facility.
        record_id: Id text.

    Returns:
        The deleted record.

    Raises:
        NotFound: If the record is not live.
    """
    return soft_delete(db, ctx, KINDS[kind][0], kind, get_record(db, kind, record_id))


def list_contacts(db: MongoDb, filters: Mapping[str, Any], after: ObjectId | None, limit: int) -> list[Doc]:
    """List live contacts, oldest first.

    Args:
        db: Firm database.
        filters: Optional kind, tag, phone (any format) and q (name or company contains).
        after: Cursor id.
        limit: Page size.

    Returns:
        Up to limit + 1 contacts.

    Raises:
        Invalid: If the phone filter is not a US number.
    """
    query: dict[str, Any] = {}
    if filters.get("kind"):
        query["kind"] = filters["kind"]
    if filters.get("tag"):
        query["tags"] = filters["tag"]
    if filters.get("phone"):
        query["phones"] = fields.phone("phone", filters["phone"])
    if filters.get("q"):
        query["$or"] = [{"name": fields.contains(filters["q"])}, {"company": fields.contains(filters["q"])}]
    return list_live(db, CONTACTS, query, after, limit)


def list_facilities(db: MongoDb, filters: Mapping[str, Any], after: ObjectId | None, limit: int) -> list[Doc]:
    """List live facilities, oldest first.

    Args:
        db: Firm database.
        filters: Optional state, city (exact, any case) and q (name or address contains).
        after: Cursor id.
        limit: Page size.

    Returns:
        Up to limit + 1 facilities.

    Raises:
        Invalid: If the state filter is not a two-letter code.
    """
    query: dict[str, Any] = {}
    if filters.get("state"):
        query["state"] = fields.state("state", filters["state"])
    if filters.get("city"):
        query["city"] = {"$regex": f"^{re.escape(str(filters['city']).strip())}$", "$options": "i"}
    if filters.get("q"):
        query["$or"] = [{"name": fields.contains(filters["q"])}, {"address": fields.contains(filters["q"])}]
    return list_live(db, FACILITIES, query, after, limit)
