"""Approval and consent rules on outbound messages and carrier terms."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import hermes_freight
import pytest
from hermes_freight import carriers, policy

CONSENTED = "2145550199"


@pytest.fixture(autouse=True)
def _firm(as_tenant: Callable[..., None], monkeypatch: pytest.MonkeyPatch) -> None:
    as_tenant("apex-freight")
    monkeypatch.setenv(policy.DISPATCHER_PHONE_ENV, "(240) 555-0100")
    carriers.carrier_upsert({"phone": CONSENTED,
                             "fields": {"consent": {"whatsapp": True, "method": "replied YES 2026-10-24"}}})


def _send(target: str, action: str = "send") -> dict[str, str] | None:
    return policy.pre_tool_call("send_message", {"action": action, "target": target, "message": "hi"})


def test_consented_carrier_allowed() -> None:
    assert _send(f"whatsapp:+1{CONSENTED}") is None
    assert _send(f"whatsapp:1{CONSENTED}@s.whatsapp.net") is None


def test_unconsented_number_blocked() -> None:
    directive = _send("whatsapp:+19725550100")
    assert directive and directive["action"] == "block" and "consent" in directive["message"]


def test_consent_channel_must_match() -> None:
    directive = _send(f"sms:+1{CONSENTED}")
    assert directive and directive["action"] == "block"


def test_dispatcher_and_home_channel_allowed() -> None:
    assert _send("whatsapp:+12405550100") is None
    assert _send("whatsapp") is None


def test_non_phone_recipient_needs_approval() -> None:
    directive = _send("telegram:@some_broker")
    assert directive and directive["action"] == "approve"


def test_non_send_actions_pass() -> None:
    assert _send("whatsapp:+19725550100", action="list") is None


def test_sensitive_carrier_edit_needs_approval() -> None:
    directive = policy.pre_tool_call("carrier_upsert", {"phone": CONSENTED, "fields": {"dispatch_fee_pct": 10}})
    assert directive and directive["action"] == "approve" and "dispatch_fee_pct" in directive["message"]
    assert policy.pre_tool_call("carrier_upsert", {"phone": CONSENTED, "fields": {"notes": "x"}}) is None


def test_unrelated_tools_untouched() -> None:
    assert policy.pre_tool_call("web_search", {"query": "diesel prices"}) is None


def test_policy_crash_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(args: dict[str, Any]) -> None:
        raise RuntimeError("boom")

    monkeypatch.setitem(policy.CHECKS, "send_message", boom)
    directive = _send(f"whatsapp:+1{CONSENTED}")
    assert directive and directive["action"] == "block"


def test_no_tenant_blocks_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FREIGHT_TENANT_ID")
    directive = _send(f"whatsapp:+1{CONSENTED}")
    assert directive and directive["action"] == "block"


class _FakeCtx:
    def __init__(self) -> None:
        self.tools: list[str] = []
        self.hooks: list[str] = []
        self.skills: dict[str, Path] = {}

    def register_tool(self, name: str, toolset: str, schema: dict[str, Any], handler: Any) -> None:
        assert schema["name"] == name and callable(handler)
        self.tools.append(name)

    def register_hook(self, name: str, callback: Any) -> None:
        self.hooks.append(name)

    def register_skill(self, name: str, path: Path) -> None:
        self.skills[name] = path


def test_register_wires_tools_hook_and_skills() -> None:
    ctx = _FakeCtx()
    hermes_freight.register(ctx)
    assert set(ctx.tools) == {"carrier_upsert", "carrier_get", "carrier_list",
                              "broker_check", "broker_remember", "broker_recall",
                              "ratecon_read", "weather_alerts", "load_evaluate", "broker_search"}
    assert ctx.hooks == ["pre_tool_call"]
    assert set(ctx.skills) == {"carrier-onboarding", "broker-vetting"}
