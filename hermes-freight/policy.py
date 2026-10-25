"""Approval rules enforced on every tool call through Hermes's pre_tool_call hook.

- Outbound messages to a phone number are blocked unless the number is the
  dispatcher's own or a roster carrier with consent on file for that channel.
- Messages to other named recipients escalate to the dispatcher for approval.
- Changing a carrier's money or legal terms escalates to the dispatcher.
"""

from __future__ import annotations

import re
from typing import Any

from . import carriers, tenant

DISPATCHER_PHONE_ENV = "FREIGHT_DISPATCHER_PHONE"
PHONE_CHANNELS = {"whatsapp": "whatsapp", "sms": "sms", "signal": "sms"}
SEND_ACTIONS = frozenset({"", "send"})
SENSITIVE_CARRIER_FIELDS = frozenset({"dispatch_fee_pct", "rate_floor_per_mile", "consent", "agreement_signed"})
PHONE_DIGITS = re.compile(r"\+?1?\d{10}")


def _block(message: str) -> dict[str, str]:
    """Build a veto directive.

    Args:
        message: Reason shown to the model.

    Returns:
        Hermes block directive.
    """
    return {"action": "block", "message": message}


def _approve(message: str) -> dict[str, str]:
    """Build a human-approval directive.

    Args:
        message: What the dispatcher is asked to approve.

    Returns:
        Hermes approval directive.
    """
    return {"action": "approve", "message": message}


def _phone_from_ref(ref: str) -> str | None:
    """Extract a US phone number from a target reference such as a WhatsApp JID.

    Args:
        ref: Target reference after the platform prefix.

    Returns:
        E.164 number, or None when the reference is not a phone number.
    """
    match = PHONE_DIGITS.search(re.sub(r"[\s().-]", "", ref.split("@", 1)[0]))
    if not match:
        return None
    try:
        return carriers.normalize_phone(match.group(0))
    except ValueError:
        return None


def _dispatcher_phone() -> str | None:
    """Read the dispatcher's own number from the profile scope.

    Returns:
        E.164 number, or None if unset or malformed.
    """
    raw = tenant.secret(DISPATCHER_PHONE_ENV)
    if not raw:
        return None
    try:
        return carriers.normalize_phone(raw)
    except ValueError:
        return None


def check_send_message(args: dict[str, Any]) -> dict[str, str] | None:
    """Apply the consent rule to a send_message call.

    Args:
        args: send_message arguments.

    Returns:
        A directive, or None to allow.
    """
    if str(args.get("action") or "").lower() not in SEND_ACTIONS:
        return None
    platform, _, ref = str(args.get("target", "")).partition(":")
    platform, ref = platform.strip().lower(), ref.strip()
    if not ref:
        return None  # home channel: the dispatcher's own chat
    channel = PHONE_CHANNELS.get(platform)
    phone = _phone_from_ref(ref) if channel else None
    if channel and phone:
        if phone == _dispatcher_phone():
            return None
        if carriers.consented(phone, channel):
            return None
        return _block(
            f"No {channel} consent on file for {phone}. Messaging people who have not consented "
            "is not allowed (TCPA). Record consent on the carrier profile first."
        )
    return _approve(f"Send a message to {platform}:{ref}? This recipient is not on the consent list.")


def check_carrier_upsert(args: dict[str, Any]) -> dict[str, str] | None:
    """Escalate edits to a carrier's money or legal terms.

    Args:
        args: carrier_upsert arguments.

    Returns:
        A directive, or None to allow.
    """
    fields = args.get("fields") or {}
    touched = sorted(SENSITIVE_CARRIER_FIELDS & set(fields))
    if not touched:
        return None
    summary = ", ".join(f"{k}={fields[k]!r}" for k in touched)
    return _approve(f"Change carrier {args.get('phone')}: {summary}?")


CHECKS = {"send_message": check_send_message, "carrier_upsert": check_carrier_upsert}


def pre_tool_call(tool_name: str, args: dict[str, Any], task_id: str = "", **kwargs: Any) -> dict[str, str] | None:
    """Hermes hook: return a block/approve directive for governed tools.

    Args:
        tool_name: Tool about to run.
        args: Its arguments.
        task_id: Hermes task id.
        **kwargs: Additional hook payload.

    Returns:
        Directive or None. Internal errors block rather than allow (fail closed).
    """
    check = CHECKS.get(tool_name)
    if check is None:
        return None
    try:
        return check(args if isinstance(args, dict) else {})
    except Exception as exc:  # noqa: BLE001 - a policy crash must never let the call through
        return _block(f"freight policy check failed, call blocked: {exc}")
