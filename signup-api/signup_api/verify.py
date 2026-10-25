"""Phone verification through Twilio Verify (SMS one-time codes).

Only an explicit "approved" from Twilio verifies a phone. Network and service errors
raise VerifyError so the API answers 502; they never count as approval.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Protocol

TWILIO_VERIFY = "https://verify.twilio.com/v2"
TWILIO_ENV = ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_VERIFY_SERVICE_SID")
HTTP_TIMEOUT_SECONDS = 15
HTTP_NOT_FOUND = 404
APPROVED = "approved"

_urlopen = urllib.request.urlopen


class VerifyError(RuntimeError):
    """The verification service could not be reached or rejected the request."""


class Verifier(Protocol):
    """Sends and checks one-time codes for a phone number."""

    def send(self, phone: str) -> None:
        """Send a code to an E.164 phone number."""
        ...

    def check(self, phone: str, code: str) -> bool:
        """Return True only when the code is approved for the phone."""
        ...


class TwilioVerifier:
    """Twilio Verify v2 client using HTTP basic auth."""

    def __init__(self, account_sid: str, auth_token: str, service_sid: str) -> None:
        """Store credentials.

        Args:
            account_sid: Twilio Account SID.
            auth_token: Twilio Auth Token.
            service_sid: Verify Service SID (starts with VA).
        """
        self._auth = "Basic " + base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
        self._base = f"{TWILIO_VERIFY}/Services/{urllib.parse.quote(service_sid)}"

    def _post(self, path: str, form: dict[str, str]) -> dict[str, Any]:
        """POST a form to the Verify service.

        Args:
            path: Path under the service, e.g. "/Verifications".
            form: Form fields.

        Returns:
            Decoded JSON response.

        Raises:
            urllib.error.HTTPError: On HTTP error status.
            VerifyError: On network failure or a non-JSON body.
        """
        request = urllib.request.Request(self._base + path, data=urllib.parse.urlencode(form).encode(),
                                         method="POST", headers={"Authorization": self._auth})
        try:
            with _urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise VerifyError(f"verification service unavailable: {exc}") from exc

    def send(self, phone: str) -> None:
        """Send an SMS code.

        Args:
            phone: E.164 number.

        Raises:
            VerifyError: If Twilio cannot be reached or rejects the request.
        """
        try:
            self._post("/Verifications", {"To": phone, "Channel": "sms"})
        except urllib.error.HTTPError as exc:
            raise VerifyError(f"verification send failed: HTTP {exc.code}") from exc

    def check(self, phone: str, code: str) -> bool:
        """Check a code.

        Args:
            phone: E.164 number.
            code: Code the user typed.

        Returns:
            True only when Twilio reports the code approved. An expired or already used
            verification (HTTP 404) is False.

        Raises:
            VerifyError: If Twilio cannot be reached or fails otherwise.
        """
        try:
            reply = self._post("/VerificationCheck", {"To": phone, "Code": code})
        except urllib.error.HTTPError as exc:
            if exc.code == HTTP_NOT_FOUND:
                return False
            raise VerifyError(f"verification check failed: HTTP {exc.code}") from exc
        return reply.get("status") == APPROVED


def from_env() -> TwilioVerifier | None:
    """Build the Twilio verifier from environment variables.

    Returns:
        The verifier, or None when any credential is missing (signups then stay closed).
    """
    values = [os.environ.get(name, "").strip() for name in TWILIO_ENV]
    if not all(values):
        return None
    return TwilioVerifier(*values)
