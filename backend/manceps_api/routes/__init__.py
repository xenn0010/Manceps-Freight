"""HTTP routers under /v1, in the order they are mounted."""

from __future__ import annotations

from fastapi import APIRouter

from . import auth_magic, auth_otp, auth_sessions, firm, me, members, portal

ROUTERS: tuple[APIRouter, ...] = (
    me.router, auth_otp.router, auth_magic.router, auth_sessions.router, portal.router, firm.router, members.router,
)
