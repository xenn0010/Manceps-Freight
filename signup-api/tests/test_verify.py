"""Twilio Verify client: requests are well formed and failures never approve."""

from __future__ import annotations

import io
import json
import urllib.error
from typing import Any

import pytest

from signup_api import verify

SID, TOKEN, SERVICE = "AC123", "tok", "VA456"


class _Recorder:
    def __init__(self, reply: Any) -> None:
        self.reply = reply
        self.requests: list[Any] = []

    def __call__(self, request: Any, timeout: float) -> Any:
        self.requests.append(request)
        if isinstance(self.reply, Exception):
            raise self.reply
        return io.BytesIO(json.dumps(self.reply).encode())


@pytest.fixture
def twilio() -> verify.TwilioVerifier:
    return verify.TwilioVerifier(SID, TOKEN, SERVICE)


def test_send_posts_sms_verification(twilio: verify.TwilioVerifier, monkeypatch: pytest.MonkeyPatch) -> None:
    rec = _Recorder({"status": "pending"})
    monkeypatch.setattr(verify, "_urlopen", rec)
    twilio.send("+12405550100")
    request = rec.requests[0]
    assert request.full_url == f"{verify.TWILIO_VERIFY}/Services/{SERVICE}/Verifications"
    assert request.data == b"To=%2B12405550100&Channel=sms"
    assert request.get_header("Authorization").startswith("Basic ")


@pytest.mark.parametrize(("status", "approved"), [("approved", True), ("pending", False), ("canceled", False)])
def test_check_only_approved_passes(twilio: verify.TwilioVerifier, monkeypatch: pytest.MonkeyPatch,
                                   status: str, approved: bool) -> None:
    monkeypatch.setattr(verify, "_urlopen", _Recorder({"status": status}))
    assert twilio.check("+12405550100", "123456") is approved


def test_expired_check_is_not_approved(twilio: verify.TwilioVerifier, monkeypatch: pytest.MonkeyPatch) -> None:
    gone = urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b"{}"))  # type: ignore[arg-type]
    monkeypatch.setattr(verify, "_urlopen", _Recorder(gone))
    assert twilio.check("+12405550100", "123456") is False


def test_network_failure_raises(twilio: verify.TwilioVerifier, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(verify, "_urlopen", _Recorder(urllib.error.URLError("down")))
    with pytest.raises(verify.VerifyError):
        twilio.check("+12405550100", "123456")
    with pytest.raises(verify.VerifyError):
        twilio.send("+12405550100")


def test_from_env_requires_all_three(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in verify.TWILIO_ENV:
        monkeypatch.setenv(name, "x")
    assert isinstance(verify.from_env(), verify.TwilioVerifier)
    monkeypatch.delenv(verify.TWILIO_ENV[2])
    assert verify.from_env() is None
