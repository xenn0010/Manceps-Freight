"""Twilio Verify and SMTP clients against fake transports: well-formed requests, failures never approve."""

from __future__ import annotations

import email.message
from urllib.parse import parse_qs

import httpx
import pytest
from pydantic import SecretStr

from manceps_api.integrations import configured, mailer, twilio_verify
from manceps_api.settings import Settings

SID, TOKEN, SERVICE = "AC123", "tok", "VA456"
PHONE = "+12405550100"


class Recorder:
    """httpx transport handler that records requests and returns a canned reply."""

    def __init__(self, status: int, body: object | None = None, error: Exception | None = None) -> None:
        """Set the canned reply.

        Args:
            status: HTTP status to return.
            body: JSON body to return.
            error: Exception to raise instead of replying.
        """
        self.status = status
        self.body = body
        self.error = error
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Handle one request.

        Args:
            request: Outgoing request.

        Returns:
            The canned response.

        Raises:
            Exception: The configured error, if any.
        """
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if self.body is None:
            return httpx.Response(self.status, content=b"not json")
        return httpx.Response(self.status, json=self.body)


def _client(recorder: Recorder) -> twilio_verify.TwilioVerifier:
    """Build a verifier over a mock transport.

    Args:
        recorder: Transport handler.

    Returns:
        The verifier.
    """
    return twilio_verify.TwilioVerifier(SID, TOKEN, SERVICE, transport=httpx.MockTransport(recorder))


def test_send_posts_sms_verification() -> None:
    recorder = Recorder(201, {"status": "pending"})
    _client(recorder).send(PHONE)
    request = recorder.requests[0]
    assert str(request.url) == f"{twilio_verify.TWILIO_VERIFY_BASE}/Services/{SERVICE}/Verifications"
    assert parse_qs(request.content.decode()) == {"To": [PHONE], "Channel": ["sms"]}
    assert request.headers["Authorization"].startswith("Basic ")


@pytest.mark.parametrize(("status", "approved"), [("approved", True), ("pending", False), ("canceled", False)])
def test_check_only_approved_passes(status: str, approved: bool) -> None:
    recorder = Recorder(200, {"status": status})
    assert _client(recorder).check(PHONE, "123456") is approved
    assert parse_qs(recorder.requests[0].content.decode()) == {"To": [PHONE], "Code": ["123456"]}


def test_expired_check_is_not_approved() -> None:
    assert _client(Recorder(404, {"code": 20404})).check(PHONE, "123456") is False


@pytest.mark.parametrize("recorder", [
    Recorder(500, {"message": "down"}),
    Recorder(200, None),
    Recorder(200, ["not", "an", "object"]),
    Recorder(0, error=httpx.ConnectError("down")),
    Recorder(0, error=httpx.ReadTimeout("slow")),
])
def test_failures_raise_verify_error(recorder: Recorder) -> None:
    with pytest.raises(twilio_verify.VerifyError):
        _client(recorder).check(PHONE, "123456")
    with pytest.raises(twilio_verify.VerifyError):
        _client(recorder).send(PHONE)


def test_verifier_from_settings_requires_all_three() -> None:
    full = Settings(env="test", twilio_account_sid=SID, twilio_auth_token=SecretStr(TOKEN),
                    twilio_verify_service_sid=SERVICE)
    assert isinstance(twilio_verify.verifier_from_settings(full), twilio_verify.TwilioVerifier)
    assert twilio_verify.verifier_from_settings(Settings(env="test", twilio_account_sid=SID)) is None


class FakeSmtp:
    """smtplib.SMTP stand-in that records the conversation."""

    instances: list[FakeSmtp] = []
    fail = False

    def __init__(self, host: str, port: int, timeout: float) -> None:
        """Open a fake connection.

        Args:
            host: SMTP host.
            port: SMTP port.
            timeout: Socket timeout.

        Raises:
            OSError: When the class is set to fail.
        """
        if FakeSmtp.fail:
            raise OSError("connection refused")
        self.address = (host, port, timeout)
        self.calls: list[str] = []
        self.messages: list[email.message.EmailMessage] = []
        FakeSmtp.instances.append(self)

    def starttls(self) -> object:
        """Record STARTTLS.

        Returns:
            Nothing useful.
        """
        self.calls.append("starttls")
        return None

    def login(self, user: str, password: str) -> object:
        """Record a login.

        Args:
            user: User.
            password: Password.

        Returns:
            Nothing useful.
        """
        self.calls.append(f"login:{user}:{len(password)}")
        return None

    def send_message(self, msg: email.message.EmailMessage) -> object:
        """Record a message.

        Args:
            msg: Message.

        Returns:
            Nothing useful.
        """
        self.messages.append(msg)
        return None

    def quit(self) -> object:
        """Record QUIT.

        Returns:
            Nothing useful.
        """
        self.calls.append("quit")
        return None


@pytest.fixture(autouse=True)
def reset_smtp() -> None:
    """Reset the fake SMTP class state between tests."""
    FakeSmtp.instances = []
    FakeSmtp.fail = False


def test_smtp_mailer_sends_with_starttls_and_login() -> None:
    sender = mailer.SmtpMailer("smtp.test", 587, "user", SecretStr("pw"), "login@manceps.test", factory=FakeSmtp)
    sender.send("owner@apex.test", "Your link", "Click https://x")
    connection = FakeSmtp.instances[0]
    assert connection.address == ("smtp.test", 587, mailer.SMTP_TIMEOUT_SECONDS)
    assert connection.calls == ["starttls", "login:user:2", "quit"]
    message = connection.messages[0]
    assert message["To"] == "owner@apex.test" and message["From"] == "login@manceps.test"
    assert message["Subject"] == "Your link" and "https://x" in message.get_content()


def test_smtp_mailer_without_login_and_failure() -> None:
    sender = mailer.SmtpMailer("smtp.test", 25, None, None, "login@manceps.test", factory=FakeSmtp)
    sender.send("owner@apex.test", "s", "b")
    assert FakeSmtp.instances[0].calls == ["starttls", "quit"]
    FakeSmtp.fail = True
    with pytest.raises(mailer.MailError):
        sender.send("owner@apex.test", "s", "b")


def test_mailer_from_settings_needs_flag_host_sender_and_base_url() -> None:
    ready = Settings(env="test", email_login_enabled=True, smtp_host="smtp.test", mail_from="a@b.test",
                     public_base_url="https://app.test")
    assert isinstance(mailer.mailer_from_settings(ready), mailer.SmtpMailer)
    for missing in ("email_login_enabled", "smtp_host", "mail_from", "public_base_url"):
        values = ready.model_dump()
        values[missing] = False if missing == "email_login_enabled" else None
        assert mailer.mailer_from_settings(Settings(**values)) is None, missing


def test_integrations_from_settings_default_is_unconfigured() -> None:
    bundle = configured.Integrations.from_settings(Settings(env="test"))
    assert bundle.verifier is None and bundle.mailer is None
