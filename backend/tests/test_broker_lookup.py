"""The real broker-lookup transport: bounded retries with backoff, fail-closed errors that never leak the URL."""

from __future__ import annotations

from typing import Any

import dns.exception
import dns.resolver
import httpx
import pytest
from pydantic import SecretStr

from manceps_api.integrations import broker_lookup
from manceps_api.integrations.broker_lookup import HttpLookupTransport, broker_lookup_from_settings, resolve_dns
from manceps_api.integrations.configured import Integrations
from manceps_api.settings import Settings
from manceps_core.brokers.check import LookupFailed

URL = "https://mobile.fmcsa.dot.gov/qc/services/carriers/777?webKey=super-secret-key"


class Handler:
    """MockTransport handler replaying a script of responses (or exceptions)."""

    def __init__(self, script: list[httpx.Response | Exception]) -> None:
        """Store the script.

        Args:
            script: Responses in order; the last one repeats.
        """
        self.script = script
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Return the next scripted response.

        Args:
            request: Outgoing request.

        Returns:
            The response.

        Raises:
            Exception: A scripted exception.
        """
        self.requests.append(request)
        step = self.script[min(len(self.requests), len(self.script)) - 1]
        if isinstance(step, Exception):
            raise step
        return step


def _transport(handler: Handler, sleeps: list[float]) -> HttpLookupTransport:
    """Build the transport under test.

    Args:
        handler: Mock handler.
        sleeps: Receives each backoff delay.

    Returns:
        The transport.
    """
    return HttpLookupTransport(transport=httpx.MockTransport(handler), sleep=sleeps.append)


def test_get_json_retries_server_errors_then_succeeds() -> None:
    handler = Handler([httpx.Response(503), httpx.Response(429), httpx.Response(200, json={"ok": True})])
    sleeps: list[float] = []
    assert _transport(handler, sleeps).get_json(URL) == {"ok": True}
    assert len(handler.requests) == 3 and sleeps == [0.5, 1.0]
    assert handler.requests[0].headers["user-agent"].startswith("manceps/")


def test_get_json_gives_up_without_leaking_url() -> None:
    handler = Handler([httpx.ConnectError("connect failed for " + URL)])
    sleeps: list[float] = []
    with pytest.raises(LookupFailed) as caught:
        _transport(handler, sleeps).get_json(URL)
    assert len(handler.requests) == 3 and "super-secret-key" not in str(caught.value)
    assert str(caught.value) == "ConnectError"


@pytest.mark.parametrize(("response", "message"), [
    (httpx.Response(404), "HTTP 404"), (httpx.Response(200, text="<html>"), "invalid JSON"),
])
def test_get_json_client_errors_are_not_retried(response: httpx.Response, message: str) -> None:
    handler = Handler([response])
    sleeps: list[float] = []
    with pytest.raises(LookupFailed, match=message):
        _transport(handler, sleeps).get_json(URL)
    assert len(handler.requests) == 1 and sleeps == []


class FakeTxt:
    """A TXT rdata double."""

    strings = (b"v=spf1 ", b"-all")


class FakeMx:
    """An MX rdata double."""

    def to_text(self) -> str:
        """Render the record.

        Returns:
            Record text.
        """
        return "10 mx.acme.com."


def test_resolve_dns_maps_answers_and_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    answers: dict[tuple[str, str], Any] = {("acme.com", "TXT"): [FakeTxt()], ("acme.com", "MX"): [FakeMx()],
                                           ("none.com", "MX"): dns.resolver.NXDOMAIN(),
                                           ("empty.com", "TXT"): dns.resolver.NoAnswer(),
                                           ("down.com", "MX"): dns.exception.Timeout()}

    def fake_resolve(name: str, rdtype: str, lifetime: float) -> Any:
        assert lifetime == broker_lookup.DNS_TIMEOUT_SECONDS
        answer = answers[(name, rdtype)]
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(dns.resolver, "resolve", fake_resolve)
    assert resolve_dns("acme.com", "TXT") == ["v=spf1 -all"]
    assert resolve_dns("acme.com", "MX") == ["10 mx.acme.com."]
    assert resolve_dns("none.com", "MX") == [] and resolve_dns("empty.com", "TXT") == []
    with pytest.raises(LookupFailed, match="Timeout"):
        resolve_dns("down.com", "MX")
    transport = HttpLookupTransport(dns_resolve=lambda name, rdtype: [f"{name}/{rdtype}"])
    assert transport.resolve("acme.com", "MX") == ["acme.com/MX"]


def test_broker_lookup_from_settings() -> None:
    assert broker_lookup_from_settings(Settings(env="test")) is None
    assert broker_lookup_from_settings(Settings(env="test", fmcsa_webkey=SecretStr(""))) is None
    settings = Settings(env="test", fmcsa_webkey=SecretStr("fmcsa-secret-xyz"))
    lookup = broker_lookup_from_settings(settings)
    assert lookup is not None and lookup.fmcsa_key == "fmcsa-secret-xyz"
    assert isinstance(lookup.transport, HttpLookupTransport) and "fmcsa-secret-xyz" not in repr(lookup)
    assert Integrations.from_settings(settings).broker_lookup is not None
