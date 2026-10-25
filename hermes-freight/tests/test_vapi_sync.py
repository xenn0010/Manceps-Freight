"""Vapi sync: assistant configs keep the AI disclosure, and syncing only writes to the expected org."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "deploy" / "vapi_sync.py"
PHONE_ID = "phone-1"
INBOUND_ID = "inbound-1"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("vapi_sync", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sync_mod = _load()


class FakeVapi:
    """Records requests; answers like the Vapi REST API."""

    def __init__(self, phone_found: bool = True) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self.phone_found = phone_found

    def __call__(self, method: str, path: str, body: dict[str, Any] | None) -> dict[str, Any]:
        self.calls.append((method, path, body))
        if method == "GET" and path == f"/phone-number/{PHONE_ID}":
            if not self.phone_found:
                raise sync_mod.VapiError(404, "Not Found")
            return {"id": PHONE_ID, "assistantId": INBOUND_ID}
        if method == "POST" and path == "/assistant":
            return {"id": "created-1", **(body or {})}
        if method == "PATCH":
            return {"id": path.rsplit("/", 1)[1], **(body or {})}
        raise AssertionError(f"unexpected request {method} {path}")


def _deployed() -> dict[str, Any]:
    return {"phone_number_id": PHONE_ID, "assistant_id": INBOUND_ID}


def test_shipped_configs_disclose_ai_and_recording() -> None:
    for config in sync_mod.load_configs().values():
        sync_mod.check_disclosure(config)


def test_check_disclosure_rejects_missing_ai() -> None:
    with pytest.raises(ValueError, match="AI"):
        sync_mod.check_disclosure({"name": "x", "firstMessage": "Hello, dispatch desk. This call may be recorded."})


def test_check_disclosure_rejects_missing_recording_notice() -> None:
    with pytest.raises(ValueError, match="record"):
        sync_mod.check_disclosure({"name": "x", "firstMessage": "Hi, this is Manceps, an AI assistant."})


def test_assistants_call_themselves_manceps() -> None:
    for config in sync_mod.load_configs().values():
        text = json.dumps(config)
        assert "Manceps" in config["firstMessage"]
        assert "Hermes" not in text


def test_broker_caller_variables_are_declared() -> None:
    config = sync_mod.load_configs()["broker_caller"]
    used = set(re.findall(r"\{\{\s*(\w+)\s*\}\}", json.dumps(config)))
    assert used == set(sync_mod.BROKER_CALLER_VARIABLES)


def test_broker_caller_never_accepts_or_reveals_floor() -> None:
    prompt = sync_mod.load_configs()["broker_caller"]["model"]["messages"][0]["content"]
    assert "Never accept" in prompt
    assert "Never say the floor" in prompt


def test_sync_updates_inbound_and_creates_broker_caller() -> None:
    fake = FakeVapi()
    deployed = sync_mod.sync(fake, _deployed(), sync_mod.load_configs())
    writes = [(m, p) for m, p, _ in fake.calls if m != "GET"]
    assert ("PATCH", f"/assistant/{INBOUND_ID}") in writes
    assert ("POST", "/assistant") in writes
    assert deployed["broker_caller_assistant_id"] == "created-1"
    assert deployed["assistant_id"] == INBOUND_ID


def test_sync_patches_broker_caller_when_already_created() -> None:
    fake = FakeVapi()
    deployed = {**_deployed(), "broker_caller_assistant_id": "bc-1"}
    sync_mod.sync(fake, deployed, sync_mod.load_configs())
    writes = [(m, p) for m, p, _ in fake.calls if m != "GET"]
    assert ("PATCH", "/assistant/bc-1") in writes
    assert ("POST", "/assistant") not in writes


def test_sync_refuses_key_from_another_org() -> None:
    fake = FakeVapi(phone_found=False)
    with pytest.raises(sync_mod.VapiError, match="another Vapi org"):
        sync_mod.sync(fake, _deployed(), sync_mod.load_configs())
    assert all(m == "GET" for m, _, _ in fake.calls)


def test_sync_checks_disclosure_before_any_request() -> None:
    fake = FakeVapi()
    configs = {"inbound": {"name": "x", "firstMessage": "Hello."}}
    with pytest.raises(ValueError):
        sync_mod.sync(fake, _deployed(), configs)
    assert fake.calls == []


def test_main_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VAPI_API_KEY", raising=False)
    assert sync_mod.main([]) == sync_mod.EXIT_CONFIG


def test_main_dry_run_validates_without_network(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("VAPI_API_KEY", "test-key")

    def no_network(_key: str) -> Any:
        raise AssertionError("dry run must not build a transport")

    monkeypatch.setattr(sync_mod, "http_transport", no_network)
    assert sync_mod.main([]) == 0
    assert "dry run" in capsys.readouterr().out
