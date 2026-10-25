"""Structured JSON logs: secrets and access_token query values never reach the output."""

from __future__ import annotations

import io
import json
from collections.abc import Iterator
from typing import Any

import pytest
import structlog
from fastapi.testclient import TestClient
from pydantic import SecretStr

from manceps_api.logs import REDACTED, configure_logging, redact_query_string

SECRETS = ("hunter2", "abc.def.ghi", "tok-123", "key-456", "sk-789", "refresh-000", "cookie-val", "tok-999")


@pytest.fixture
def log_stream() -> Iterator[io.StringIO]:
    """Route structlog output into a buffer for one test.

    Yields:
        The buffer.
    """
    stream = io.StringIO()
    configure_logging("INFO", stream)
    yield stream
    structlog.reset_defaults()


def _lines(stream: io.StringIO) -> list[dict[str, Any]]:
    """Parse every JSON log line.

    Args:
        stream: Log buffer.

    Returns:
        Parsed events.
    """
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


def test_logs_redact_secrets_and_access_token_query(log_stream: io.StringIO, client: TestClient) -> None:
    """Sensitive keys, bearer tokens, SecretStr values and token query params are redacted everywhere."""
    log = structlog.get_logger("test")
    log.info(
        "probe",
        password="hunter2",  # noqa: S106  # fake secret that must be redacted
        authorization="Bearer abc.def.ghi",
        url="/v1/events/stream?access_token=tok-123&after=5",
        nested={"api_key": "key-456", "items": [{"client_secret": "sk-789"}], "ok": "visible"},
        note="refresh_token=refresh-000 sent",
        cookie="mc_refresh=cookie-val",
        value=SecretStr("never-shown"),
    )
    response = client.get("/healthz?access_token=tok-999&after=7")
    assert response.status_code == 200
    output = log_stream.getvalue()
    for secret in (*SECRETS, "never-shown"):
        assert secret not in output, secret
    events = _lines(log_stream)
    probe = next(event for event in events if event["event"] == "probe")
    assert probe["password"] == REDACTED
    assert probe["nested"]["ok"] == "visible"
    assert probe["url"] == f"/v1/events/stream?access_token={REDACTED}&after=5"
    assert probe["level"] == "info" and probe["timestamp"].endswith("Z")
    access = next(event for event in events if event["event"] == "http.request")
    assert access["query"] == f"access_token={REDACTED}&after=7"
    assert access["status"] == 200


def test_request_id_propagates(log_stream: io.StringIO, client: TestClient) -> None:
    """A valid incoming X-Request-ID is echoed and logged; an invalid one is replaced."""
    response = client.get("/healthz", headers={"X-Request-ID": "req-abc-12345"})
    assert response.headers["x-request-id"] == "req-abc-12345"
    replaced = client.get("/healthz", headers={"X-Request-ID": "bad id with spaces\nInjected: yes"})
    new_id = replaced.headers["x-request-id"]
    assert new_id != "bad id with spaces\nInjected: yes" and len(new_id) == 32
    access = [event for event in _lines(log_stream) if event["event"] == "http.request"]
    assert [event["request_id"] for event in access] == ["req-abc-12345", new_id]
    assert all(event["tenant_id"] is None for event in access)


def test_redact_query_string() -> None:
    """Only sensitive parameters are masked; order and other values are preserved."""
    assert redact_query_string("") == ""
    assert redact_query_string("a=1&token=x&b=") == f"a=1&token={REDACTED}&b="
    assert redact_query_string("ACCESS_TOKEN=y") == f"ACCESS_TOKEN={REDACTED}"


def test_log_level_filters(log_stream: io.StringIO) -> None:
    """Debug lines are dropped at INFO."""
    structlog.get_logger("test").debug("hidden")
    assert "hidden" not in log_stream.getvalue()


def test_exceptions_are_redacted(log_stream: io.StringIO) -> None:
    """Tracebacks are rendered and still pass through redaction."""
    try:
        raise RuntimeError("failed with access_token=tok-123")
    except RuntimeError:
        structlog.get_logger("test").exception("boom")
    output = log_stream.getvalue()
    assert "tok-123" not in output and "RuntimeError" in output
