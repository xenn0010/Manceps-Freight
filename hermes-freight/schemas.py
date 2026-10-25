"""Tool schemas for hermes-freight: what the model reads to choose and call tools."""

from __future__ import annotations

from typing import Any

from .carriers import CONSENT_CHANNELS, EQUIPMENT_TYPES

_EQUIPMENT = sorted(EQUIPMENT_TYPES)

_CARRIER_FIELDS: dict[str, Any] = {
    "type": "object",
    "description": "Fields to set. Omit fields you are not changing.",
    "properties": {
        "name": {"type": "string", "description": "Driver or owner name"},
        "company": {"type": "string"},
        "mc_number": {"type": "string"},
        "dot_number": {"type": "string"},
        "equipment": {"type": "array", "items": {"type": "string", "enum": _EQUIPMENT}},
        "dispatch_fee_pct": {"type": "number", "description": "Dispatch fee percent of gross, e.g. 8"},
        "rate_floor_per_mile": {
            "type": "number",
            "description": "Lowest all-in $/mile the carrier accepts, over total miles (loaded + deadhead)",
        },
        "home_base": {"type": "string", "description": "City, ST"},
        "preferred_lanes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"origin": {"type": "string"}, "destination": {"type": "string"}},
            },
        },
        "avoid": {"type": "array", "items": {"type": "string"}, "description": "Regions, states, or freight to avoid"},
        "notes": {"type": "string"},
        "agreement_signed": {"type": "boolean"},
        "consent": {
            "type": "object",
            "description": "Contact consent. Only record what the carrier actually agreed to, and how.",
            "properties": {
                **{ch: {"type": "boolean"} for ch in CONSENT_CHANNELS},
                "method": {"type": "string", "description": "How consent was given, with date"},
            },
            "required": ["method"],
        },
    },
}

CARRIER_UPSERT: dict[str, Any] = {
    "name": "carrier_upsert",
    "description": (
        "Add a carrier (owner-operator truck) to this firm's roster or update their profile, keyed by "
        "phone number. Use when the dispatcher adds a truck or changes a carrier's equipment, lanes, "
        "rate floor, fee, or consent. Changes to fee, rate floor, consent, or agreement need the "
        "dispatcher's approval."
    ),
    "parameters": {
        "type": "object",
        "properties": {"phone": {"type": "string", "description": "Carrier phone, any US format"},
                       "fields": _CARRIER_FIELDS},
        "required": ["phone", "fields"],
    },
}

CARRIER_GET: dict[str, Any] = {
    "name": "carrier_get",
    "description": "Look up one carrier on this firm's roster by phone number or MC number.",
    "parameters": {
        "type": "object",
        "properties": {"phone": {"type": "string"}, "mc_number": {"type": "string"}},
    },
}

CARRIER_LIST: dict[str, Any] = {
    "name": "carrier_list",
    "description": "List this firm's carriers, optionally only those with a given equipment type.",
    "parameters": {
        "type": "object",
        "properties": {"equipment": {"type": "string", "enum": _EQUIPMENT}},
    },
}

BROKER_CHECK: dict[str, Any] = {
    "name": "broker_check",
    "description": (
        "Vet a freight broker before booking: FMCSA operating status, broker authority, and an active "
        "BMC-84/85 bond or trust on file, plus email domain age and MX/SPF/DMARC when an email is given. "
        "Returns verdict looks_ok, review, or do_not_book. Run this before quoting or accepting any load "
        "from a broker not checked in the last 30 days."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "mc_number": {"type": "string"},
            "dot_number": {"type": "string"},
            "email": {"type": "string", "description": "Broker contact email, to check the domain"},
        },
    },
}

BROKER_REMEMBER: dict[str, Any] = {
    "name": "broker_remember",
    "description": (
        "Save something learned about a broker for future negotiations: payment speed, detention "
        "and lumper habits, rate behavior, reliability, red flags. Use snake_case tags such as "
        "slow_pay, quick_pay, pays_detention, double_brokering_risk, good_rates."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "mc_number": {"type": "string"},
            "company": {"type": "string"},
            "note": {"type": "string", "description": "One factual observation with its source, e.g. call date"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["mc_number", "note"],
    },
}

BROKER_RECALL: dict[str, Any] = {
    "name": "broker_recall",
    "description": "Recall this firm's notes, tags, and last vetting verdict for a broker before talking to them.",
    "parameters": {
        "type": "object",
        "properties": {"mc_number": {"type": "string"}},
        "required": ["mc_number"],
    },
}

RATECON_READ: dict[str, Any] = {
    "name": "ratecon_read",
    "description": (
        "Read a Rate Confirmation PDF the dispatcher or broker sent, extract its terms (rate, stops, "
        "dates, equipment, payment, detention, penalties), and compare them with what was agreed on the "
        "call. Returns verdict do_not_sign (terms differ), review (warnings or nothing to compare), or "
        "matches_agreement. The path must be an inbound document attachment."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path of the received PDF attachment"},
            "agreed": {
                "type": "object",
                "description": "Terms agreed with the broker; include what is known",
                "properties": {
                    "rate_usd": {"type": "number"},
                    "origin": {"type": "string", "description": "City, ST"},
                    "destination": {"type": "string", "description": "City, ST"},
                    "pickup_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "delivery_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "equipment": {"type": "string"},
                    "broker_mc": {"type": "string"},
                },
            },
        },
        "required": ["path"],
    },
}

WEATHER_ALERTS: dict[str, Any] = {
    "name": "weather_alerts",
    "description": (
        "Active National Weather Service alerts that affect driving (winter storms, high wind, ice, "
        "flooding, tornadoes, dense fog) for the states a load passes through. Use before dispatch and "
        "during transit."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "states": {"type": "array", "items": {"type": "string"}, "description": "e.g. [\"TX\", \"OK\"]"},
        },
        "required": ["states"],
    },
}

LOAD_EVALUATE: dict[str, Any] = {
    "name": "load_evaluate",
    "description": (
        "Evaluate a load offer for one carrier on this firm's roster: miles, rate per loaded and total "
        "mile, fuel cost, dispatch fee, carrier net, equipment and lane fit, and the carrier's rate floor. "
        "Returns verdict accept_range, counter (with the minimum to ask for), pass, or unknown. Use on every "
        "offer before negotiating."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "carrier_phone": {"type": "string"},
            "rate_usd": {"type": "number", "description": "All-in offered rate"},
            "origin": {"type": "string", "description": "City, ST"},
            "destination": {"type": "string", "description": "City, ST"},
            "loaded_miles": {"type": "number", "description": "If the broker stated miles"},
            "deadhead_miles": {"type": "number", "description": "Empty miles to pickup"},
            "equipment": {"type": "string", "enum": _EQUIPMENT},
            "mpg": {"type": "number", "description": "Truck fuel economy, default 6.5"},
        },
        "required": ["carrier_phone", "rate_usd", "origin", "destination"],
    },
}

BROKER_SEARCH: dict[str, Any] = {
    "name": "broker_search",
    "description": (
        "Search FMCSA's public registry of active brokers by MC number, USDOT number, or company name "
        "(optionally within a state). Use when a broker gives a name but no MC, or to confirm the MC "
        "on a Rate Con belongs to the company named. Returns registry records, not vetting; run "
        "broker_check on the result."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "mc_number": {"type": "string"},
            "dot_number": {"type": "string"},
            "name": {"type": "string", "description": "Company name or part of it"},
            "state": {"type": "string", "description": "Two-letter state to narrow a name search"},
        },
    },
}
