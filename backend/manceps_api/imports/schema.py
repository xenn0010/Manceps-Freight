"""What each importable entity accepts: fields, their cell kinds, header synonyms, required fields and natural keys.

Synonyms are normalized header names (lowercase ASCII letters and digits only, see mapping.normalize_header).
Consent is deliberately absent: consent is recorded through the consent ledger, never imported. Loads are imported
once the loads repository exists (WP1.5).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from manceps_core.repo.errors import Invalid
from manceps_core.repo.fields import digits, email, phone

from .header import as_list, cell_text

ENTITIES = ("carriers", "drivers", "brokers", "contacts")
FIRST_NAME, LAST_NAME, NAME = "first_name", "last_name", "name"
CARRIER_PHONE = "carrier_phone"
NAME_PARTS = (FIRST_NAME, LAST_NAME)


@dataclass(frozen=True)
class FieldSpec:
    """One importable field."""

    kind: str
    label: str
    synonyms: tuple[str, ...]
    is_list: bool = False


@dataclass(frozen=True)
class EntitySpec:
    """One importable entity."""

    name: str
    ref_type: str
    collection: str
    fields: Mapping[str, FieldSpec]
    required: tuple[frozenset[str], ...]
    identity: frozenset[str]
    template: tuple[str, ...]


def _f(kind: str, label: str, *synonyms: str, is_list: bool = False) -> FieldSpec:
    """Shorthand for a FieldSpec.

    Args:
        kind: Coercion kind.
        label: Template header.
        *synonyms: Normalized header names that map to the field.
        is_list: Several columns may feed it.

    Returns:
        The spec.
    """
    return FieldSpec(kind, label, synonyms, is_list)


NAME_FIELDS: Mapping[str, FieldSpec] = {
    FIRST_NAME: _f("text", "First Name", "firstname", "givenname", "first"),
    LAST_NAME: _f("text", "Last Name", "lastname", "familyname", "surname", "last"),
}
PHONE_SYNONYMS = ("phone", "cell", "cellphone", "mobile", "mobilephone", "tel", "telephone", "phonenumber",
                  "cellnumber", "mobilenumber")
MC_SYNONYMS = ("mc", "mcnumber", "mcno", "mcnum", "docket", "docketnumber", "mcdocket")
DOT_SYNONYMS = ("dot", "dotnumber", "usdot", "usdotnumber", "dotno")
EMAIL_SYNONYMS = ("email", "emailaddress", "mail")

CARRIER_FIELDS: Mapping[str, FieldSpec] = {
    "phone": _f("phone", "Phone", *PHONE_SYNONYMS, "contactphone", "carrierphone"),
    NAME: _f("text", "Name", "name", "carriername", "carrier", "contact", "contactname", "fullname", "owner",
             "ownername"),
    "company": _f("text", "Company", "company", "companyname", "legalname", "dba", "businessname"),
    "mc_number": _f("digits", "MC Number", *MC_SYNONYMS),
    "dot_number": _f("digits", "DOT Number", *DOT_SYNONYMS),
    "email": _f("email", "Email", *EMAIL_SYNONYMS),
    "equipment": _f("slug_list", "Equipment", "equipment", "equipmenttype", "trailer", "trailertype", "trucktype",
                    is_list=True),
    "home_base": _f("text", "Home Base", "homebase", "base", "location", "homelocation", "domicile"),
    "notes": _f("text", "Notes", "notes", "note", "comments", "comment", "remarks"),
    "status": _f("text", "Status", "status"),
    "tags": _f("slug_list", "Tags", "tags", "tag", is_list=True),
    "insurance_expires_at": _f("date", "Insurance Expires", "insuranceexpires", "insuranceexpiration",
                               "insuranceexpiry", "insuranceexpirationdate", "insexp", "coiexpires", "coiexpiration"),
    "dispatch_fee_pct": _f("number", "Dispatch Fee %", "dispatchfee", "fee", "feepct", "feepercent",
                           "dispatchfeepct", "dispatchfeepercent"),
    "rate_floor_per_mile": _f("number", "Rate Floor Per Mile", "ratefloorpermile", "ratefloor", "floor", "minrate",
                              "minimumrate", "minrpm", "floorrpm"),
    "agreement_signed": _f("bool", "Agreement Signed", "agreementsigned", "agreement", "contractsigned", "signed"),
    **NAME_FIELDS,
}
DRIVER_FIELDS: Mapping[str, FieldSpec] = {
    CARRIER_PHONE: _f("phone", "Carrier Phone", "carrierphone", "carriercell", "carriermobile", "carrierphonenumber"),
    NAME: _f("text", "Name", "name", "drivername", "driver", "fullname", "contactname"),
    "phone": _f("phone", "Phone", *PHONE_SYNONYMS, "driverphone", "drivercell", "drivermobile"),
    "email": _f("email", "Email", *EMAIL_SYNONYMS, "driveremail"),
    "status": _f("text", "Status", "status"),
    "license_state": _f("text", "License State", "licensestate", "cdlstate", "dlstate"),
    "license_expires_at": _f("date", "License Expires", "licenseexpires", "licenseexpiration", "cdlexpires",
                             "cdlexpiration"),
    **NAME_FIELDS,
}
BROKER_FIELDS: Mapping[str, FieldSpec] = {
    "mc_number": _f("digits", "MC Number", *MC_SYNONYMS, "brokermc"),
    "dot_number": _f("digits", "DOT Number", *DOT_SYNONYMS),
    "company": _f("text", "Company", "company", "companyname", "broker", "brokername", "brokercompany", "name",
                  "legalname"),
    "tags": _f("slug_list", "Tags", "tags", "tag", is_list=True),
    "payment_terms": _f("text", "Payment Terms", "paymentterms", "terms", "payterms"),
    "credit_notes": _f("text", "Credit Notes", "creditnotes", "credit", "creditnote"),
}
CONTACT_FIELDS: Mapping[str, FieldSpec] = {
    "kind": _f("text", "Kind", "kind", "type", "contacttype", "category"),
    NAME: _f("text", "Name", "name", "fullname", "contactname", "displayname"),
    "company": _f("text", "Company", "company", "companyname", "organization", "organizationname", "org",
                  "business"),
    "title": _f("text", "Title", "title", "jobtitle", "position", "organizationtitle", "role"),
    "phones": _f("list", "Phone", *PHONE_SYNONYMS, "phones", "otherphones", "workphone", "homephone",
                 is_list=True),
    "emails": _f("list", "Email", "email", "emails", "emailaddress", "mail", "workemail", is_list=True),
    "tags": _f("slug_list", "Tags", "tags", "tag", is_list=True),
    **NAME_FIELDS,
}

NAME_GROUP = frozenset({NAME, FIRST_NAME, LAST_NAME})
ENTITY_SPECS: Mapping[str, EntitySpec] = {
    "carriers": EntitySpec("carriers", "carrier", "carriers", CARRIER_FIELDS, (frozenset({"phone"}),),
                           frozenset({"phone"}), tuple(CARRIER_FIELDS)[:-2]),
    "drivers": EntitySpec("drivers", "driver", "drivers", DRIVER_FIELDS,
                          (frozenset({CARRIER_PHONE}), NAME_GROUP), frozenset({"phone"}), tuple(DRIVER_FIELDS)[:-2]),
    "brokers": EntitySpec("brokers", "broker", "brokers", BROKER_FIELDS, (frozenset({"mc_number"}),),
                          frozenset({"mc_number"}), tuple(BROKER_FIELDS)),
    "contacts": EntitySpec("contacts", "contact", "contacts", CONTACT_FIELDS, (NAME_GROUP,), frozenset(),
                           ("kind", NAME, "company", "title", "phones", "emails", "tags")),
}


def normalize_key(kind: str, raw: Any) -> str | None:
    """Normalize a natural-key value the way the repositories store it.

    Args:
        kind: phone (E.164), mc (digits) or email (lowercased).
        raw: Raw value.

    Returns:
        The normalized value, or None when it is not valid for the kind.
    """
    text = cell_text(raw)
    rules = {"phone": phone, "mc": digits, "email": email}
    try:
        return str(rules[kind](kind, text))
    except Invalid:
        return None


def natural_key(entity: str, values: Mapping[str, Any]) -> str | None:
    """The key that finds the same record in the firm: carriers and drivers by phone, brokers by MC, contacts by
    first email, else first phone.

    Args:
        entity: Entity name.
        values: Validated, normalized fields.

    Returns:
        "phone:+1...", "mc:123" or "email:a@b", or None when the row has no key.
    """
    if entity == "brokers":
        return f"mc:{values['mc_number']}" if values.get("mc_number") else None
    if entity == "contacts":
        emails, phones = as_list(values.get("emails")), as_list(values.get("phones"))
        if emails:
            return f"email:{emails[0]}"
        return f"phone:{phones[0]}" if phones else None
    return f"phone:{values['phone']}" if values.get("phone") else None
