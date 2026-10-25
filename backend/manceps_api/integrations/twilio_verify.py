"""Phone verification through Twilio Verify (SMS one-time codes), ported from signup-api's verify.py.

Only an explicit "approved" from Twilio verifies a phone. Network errors, timeouts, non-JSON bodies and service errors
raise VerifyError (the API answers 502); they never count as approval. Neither call is retried: a send triggers an
SMS and a check consumes an attempt, so neither is idempotent.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from ..settings import Settings

TWILIO_VERIFY_BASE = "https://verify.twilio.com/v2"
HTTP_TIMEOUT_SECONDS = 15.0
HTTP_NOT_FOUND = 404
HTTP_ERROR_FROM = 400
APPROVED = "approved"


class VerifyError(RuntimeError):
    """The verification service could not be reached or rejected the request."""


class Verifier(Protocol):
    """Sends and checks one-time codes for a phone number."""

    @abstractmethod
    def send(self, phone: str) -> None:
        """Send a code to an E.164 phone number.

        Args:
            phone: E.164 number.

        Raises:
            VerifyError: If the service fails.
        """

    @abstractmethod
    def check(self, phone: str, code: str) -> bool:
        """Check a code.

        Args:
            phone: E.164 number.
            code: Code the user typed.

        Returns:
            True only when the code is approved for the phone.

        Raises:
            VerifyError: If the service fails.
        """


class TwilioVerifier:
    """Twilio Verify v2 client using HTTP basic auth over httpx."""

    def __init__(self, account_sid: str, auth_token: str, service_sid: str,
                 transport: httpx.BaseTransport | None = None, timeout: float = HTTP_TIMEOUT_SECONDS) -> None:
        """Store credentials and the transport.

        Args:
            account_sid: Twilio Account SID.
            auth_token: Twilio Auth Token.
            service_sid: Verify Service SID (starts with VA).
            transport: httpx transport; a MockTransport in tests, the default network transport otherwise.
            timeout: Per-request timeout in seconds.
        """
        self._auth = httpx.BasicAuth(account_sid, auth_token)
        self._base = f"{TWILIO_VERIFY_BASE}/Services/{quote(service_sid, safe='')}"
        self._transport = transport
        self._timeout = timeout

    def _post(self, path: str, form: dict[str, str]) -> tuple[int, dict[str, Any]]:
        """POST a form to the Verify service.

        Args:
            path: Path under the service, e.g. "/Verifications".
            form: Form fields.

        Returns:
            (HTTP status, decoded JSON object).

        Raises:
            VerifyError: On network failure, timeout or a body that is not a JSON object.
        """
        try:
            with httpx.Client(transport=self._transport, timeout=self._timeout, auth=self._auth) as client:
                response = client.post(self._base + path, data=form)
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise VerifyError(f"verification service unavailable: {type(exc).__name__}") from exc
        if not isinstance(body, dict):
            raise VerifyError("verification service returned an unexpected body")
        return response.status_code, body  # pyright: ignore[reportUnknownVariableType]

    def send(self, phone: str) -> None:
        """Send an SMS code.

        Args:
            phone: E.164 number.

        Raises:
            VerifyError: If Twilio cannot be reached or rejects the request.
        """
        status, _body = self._post("/Verifications", {"To": phone, "Channel": "sms"})
        if status >= HTTP_ERROR_FROM:
            raise VerifyError(f"verification send failed: HTTP {status}")

    def check(self, phone: str, code: str) -> bool:
        """Check a code.

        Args:
            phone: E.164 number.
            code: Code the user typed.

        Returns:
            True only when Twilio reports the code approved. An expired or already used verification (HTTP 404) is
            False.

        Raises:
            VerifyError: If Twilio cannot be reached or fails otherwise.
        """
        status, body = self._post("/VerificationCheck", {"To": phone, "Code": code})
        if status == HTTP_NOT_FOUND:
            return False
        if status >= HTTP_ERROR_FROM:
            raise VerifyError(f"verification check failed: HTTP {status}")
        return body.get("status") == APPROVED


def verifier_from_settings(settings: Settings, transport: httpx.BaseTransport | None = None) -> TwilioVerifier | None:
    """Build the Twilio verifier from settings.

    Args:
        settings: Application settings.
        transport: Optional httpx transport.

    Returns:
        The verifier, or None when any of the three credentials is missing (OTP routes then answer 503).
    """
    sid, token, service = settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_verify_service_sid
    if not sid or token is None or not token.get_secret_value() or not service:
        return None
    return TwilioVerifier(sid, token.get_secret_value(), service, transport=transport)
