"""Dev-only phone verifier: one fixed DEV_OTP_CODE approves every phone and no SMS is sent.

It exists so the API and web frontend can run locally without Twilio. It is built only when ENV=dev and
DEV_OTP_CODE is set (settings refuse DEV_OTP_CODE in any other environment), and only when Twilio Verify is not
configured: if both are set, Twilio wins and the dev code is ignored. The code is compared in constant time and is
never logged. The OTP routes keep every rate limit, because the verifier sits behind them.
"""

from __future__ import annotations

import hmac

import structlog
from pydantic import SecretStr

from ..settings import DEV_ENV, Settings
from .twilio_verify import Verifier, verifier_from_settings

log = structlog.get_logger(__name__)


class DevCodeVerifier:
    """Approves exactly one configured code for any phone; sends nothing."""

    def __init__(self, code: SecretStr) -> None:
        """Store the code.

        Args:
            code: The six-digit dev code (validated by Settings).
        """
        self._code = code.get_secret_value().encode("ascii")

    def __repr__(self) -> str:
        """Describe the verifier without the code.

        Returns:
            A redacted representation.
        """
        return "DevCodeVerifier(code='******')"

    def send(self, phone: str) -> None:
        """Send nothing: the dev code is fixed and known to the developer.

        Args:
            phone: E.164 number (unused).
        """
        del phone

    def check(self, phone: str, code: str) -> bool:
        """Compare the typed code with the dev code in constant time.

        Args:
            phone: E.164 number (every phone shares the dev code).
            code: Code the user typed.

        Returns:
            True only when the code equals the dev code.
        """
        del phone
        return hmac.compare_digest(code.encode("utf-8"), self._code)


def phone_verifier_from_settings(settings: Settings) -> Verifier | None:
    """Pick the phone verifier: Twilio when configured, else the dev code in dev, else none (routes answer 503).

    Args:
        settings: Application settings.

    Returns:
        The verifier, or None when phone sign-in is not configured.
    """
    twilio = verifier_from_settings(settings)
    dev_code = settings.dev_otp_code if settings.env == DEV_ENV else None
    if twilio is not None:
        if dev_code is not None:
            log.warning("verify.dev_code_ignored", reason="twilio_configured")
        return twilio
    if dev_code is None:
        return None
    log.warning("verify.dev_code_enabled", env=settings.env)
    return DevCodeVerifier(dev_code)
