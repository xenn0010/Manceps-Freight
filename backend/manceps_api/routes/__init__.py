"""HTTP routers under /v1, in the order they are mounted."""

from __future__ import annotations

from fastapi import APIRouter

from . import (
    approvals,
    auth_magic,
    auth_otp,
    auth_sessions,
    board,
    brokers,
    carrier_access,
    carriers,
    contacts,
    events,
    exports,
    firm,
    fleet,
    imports,
    loads,
    me,
    members,
    notes,
    portal,
)

ROUTERS: tuple[APIRouter, ...] = (
    me.router, auth_otp.router, auth_magic.router, auth_sessions.router, portal.router, firm.router, members.router,
    carriers.router, carrier_access.router, fleet.router, brokers.router, contacts.router, notes.router,
    imports.router, exports.router, loads.router, approvals.router, board.router, events.router,
)
