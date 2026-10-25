"""Signup tickets: proof that a phone passed its OTP check, so a new user can finish signup without a second code.

`POST /v1/auth/otp/verify` for an approved code on a phone with no account (and no signup details) answers 422
`signup_details_required` with a ticket. The ticket (`mcs_<urlsafe32>`) is stored as SHA-256, bound to the phone,
valid for TICKET_TTL and spent exactly once by a conditional update. Twilio codes are single use, so without the
ticket the user's verified code would be wasted.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from pymongo import ReturnDocument

from manceps_core.accounts import new_id
from manceps_core.mongo import MongoDb

from .sessions import hash_token

SIGNUP_TICKETS = "signup_tickets"
TICKET_PREFIX = "mcs_"
TICKET_BYTES = 32
TICKET_ID_PREFIX = "stk"
TICKET_TTL = timedelta(minutes=10)
TICKET_PATTERN = r"^mcs_[A-Za-z0-9_-]{43}$"


def issue_ticket(db: MongoDb, phone: str, now: datetime) -> tuple[str, int]:
    """Store a new single-use ticket for a verified phone.

    Args:
        db: Platform database.
        phone: E.164 phone whose code was just approved.
        now: Current UTC time.

    Returns:
        (raw ticket, lifetime in seconds). Only the hash is stored.
    """
    raw = TICKET_PREFIX + secrets.token_urlsafe(TICKET_BYTES)
    db[SIGNUP_TICKETS].insert_one({"_id": new_id(TICKET_ID_PREFIX), "token_hash": hash_token(raw), "phone": phone,
                                   "created_at": now, "expires_at": now + TICKET_TTL, "used_at": None})
    return raw, int(TICKET_TTL.total_seconds())


def redeem_ticket(db: MongoDb, raw: str, phone: str, now: datetime) -> bool:
    """Spend a ticket for the phone it was issued to.

    Args:
        db: Platform database.
        raw: Ticket from the client.
        phone: E.164 phone in the request.
        now: Current UTC time.

    Returns:
        True when the ticket was valid, unused, unexpired and bound to this phone (it is now spent).
    """
    spent = db[SIGNUP_TICKETS].find_one_and_update(
        {"token_hash": hash_token(raw), "phone": phone, "used_at": None, "expires_at": {"$gt": now}},
        {"$set": {"used_at": now}}, return_document=ReturnDocument.AFTER,
    )
    return spent is not None
