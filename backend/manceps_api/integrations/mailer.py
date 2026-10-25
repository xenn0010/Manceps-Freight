"""SMTP sender for magic-link emails, behind a connection-factory seam so tests never open a socket.

The connection always upgrades with STARTTLS before optional login; a server without STARTTLS fails the send rather
than sending credentials or login links in clear text. Sends are not retried (a duplicate email is worse than an
error the user can retry).
"""

from __future__ import annotations

import smtplib
from abc import abstractmethod
from email.message import EmailMessage
from typing import Protocol

from pydantic import SecretStr

from ..settings import Settings

SMTP_TIMEOUT_SECONDS = 10.0


class MailError(RuntimeError):
    """The mail server could not be reached or refused the message."""


class Mailer(Protocol):
    """Sends one plain-text email."""

    @abstractmethod
    def send(self, to: str, subject: str, body: str) -> None:
        """Send a message.

        Args:
            to: Recipient address.
            subject: Subject line.
            body: Plain-text body.

        Raises:
            MailError: If the message could not be sent.
        """


class SmtpConnection(Protocol):
    """The subset of smtplib.SMTP the mailer uses."""

    @abstractmethod
    def starttls(self) -> object:
        """Upgrade to TLS.

        Returns:
            Server reply.
        """

    @abstractmethod
    def login(self, user: str, password: str) -> object:
        """Authenticate.

        Args:
            user: User name.
            password: Password.

        Returns:
            Server reply.
        """

    @abstractmethod
    def send_message(self, msg: EmailMessage) -> object:
        """Send a message.

        Args:
            msg: Message.

        Returns:
            Refused recipients.
        """

    @abstractmethod
    def quit(self) -> object:
        """Close the session.

        Returns:
            Server reply.
        """


class SmtpFactory(Protocol):
    """Opens an SMTP connection (smtplib.SMTP in production)."""

    @abstractmethod
    def __call__(self, host: str, port: int, timeout: float) -> SmtpConnection:
        """Connect.

        Args:
            host: Server host.
            port: Server port.
            timeout: Socket timeout in seconds.

        Returns:
            The connection.
        """


def _smtplib_factory(host: str, port: int, timeout: float) -> SmtpConnection:
    """Open a real SMTP connection.

    Args:
        host: Server host.
        port: Server port.
        timeout: Socket timeout in seconds.

    Returns:
        The smtplib connection.

    Raises:
        OSError: If the server is unreachable.
        smtplib.SMTPException: If the greeting fails.
    """
    return smtplib.SMTP(host, port, timeout=timeout)


class SmtpMailer:
    """Plain-text mail over SMTP with mandatory STARTTLS."""

    def __init__(self, host: str, port: int, user: str | None, password: SecretStr | None, mail_from: str,
                 factory: SmtpFactory = _smtplib_factory, timeout: float = SMTP_TIMEOUT_SECONDS) -> None:
        """Store server settings.

        Args:
            host: SMTP host.
            port: SMTP port (587 for submission).
            user: Login user, or None for no login.
            password: Login password.
            mail_from: Sender address.
            factory: Connection factory.
            timeout: Socket timeout in seconds.
        """
        self._host, self._port, self._user, self._password = host, port, user, password
        self._from, self._factory, self._timeout = mail_from, factory, timeout

    def send(self, to: str, subject: str, body: str) -> None:
        """Send one message.

        Args:
            to: Recipient address.
            subject: Subject line.
            body: Plain-text body.

        Raises:
            MailError: If connecting, TLS, login or sending fails.
        """
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = self._from, to, subject
        message.set_content(body)
        try:
            connection = self._factory(self._host, self._port, timeout=self._timeout)
            try:
                connection.starttls()
                if self._user and self._password is not None:
                    connection.login(self._user, self._password.get_secret_value())
                connection.send_message(message)
            finally:
                connection.quit()
        except (OSError, smtplib.SMTPException) as exc:
            raise MailError(f"mail delivery failed: {type(exc).__name__}") from exc


def mailer_from_settings(settings: Settings, factory: SmtpFactory = _smtplib_factory) -> SmtpMailer | None:
    """Build the magic-link mailer when email login is fully configured.

    Args:
        settings: Application settings.
        factory: Connection factory.

    Returns:
        The mailer, or None unless EMAIL_LOGIN_ENABLED, SMTP_HOST, MAIL_FROM and PUBLIC_BASE_URL are all set.
    """
    if not (settings.email_login_enabled and settings.smtp_host and settings.mail_from and settings.public_base_url):
        return None
    return SmtpMailer(settings.smtp_host, settings.smtp_port, settings.smtp_user, settings.smtp_password,
                      settings.mail_from, factory=factory)
