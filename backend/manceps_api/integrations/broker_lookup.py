"""Network transport for broker vetting: FMCSA QCMobile and RDAP over httpx, DNS over dnspython.

GETs are idempotent, so transport errors, 429 and 5xx are retried a bounded number of times with exponential
backoff. Every failure becomes `LookupFailed` with a message that names only the error type or HTTP status, never the
URL (FMCSA URLs carry the web key). Without `FMCSA_WEBKEY` the feature is not configured and the check route
answers 503.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import dns.exception
import dns.resolver
import httpx

from manceps_core.brokers.check import CheckTransport, LookupFailed

from ..settings import Settings

HTTP_TIMEOUT_SECONDS = 15.0
DNS_TIMEOUT_SECONDS = 8.0
MAX_RETRIES = 2
BACKOFF_SECONDS = 0.5
BACKOFF_FACTOR = 2
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
HTTP_ERROR_FROM = 400
USER_AGENT = "manceps/0.1 (+broker vetting)"
TXT = "TXT"

DnsResolve = Callable[[str, str], list[str]]


class TransientLookupFailure(LookupFailed):
    """A lookup failure worth retrying (network error, 429 or 5xx)."""


def resolve_dns(name: str, rdtype: str) -> list[str]:
    """Resolve DNS records as text with dnspython.

    Args:
        name: DNS name.
        rdtype: Record type, e.g. "MX" or "TXT".

    Returns:
        Record texts; empty when the name does not exist or has no such records.

    Raises:
        LookupFailed: On any other resolver failure (timeout, no nameservers...).
    """
    try:
        answer: Any = dns.resolver.resolve(name, rdtype, lifetime=DNS_TIMEOUT_SECONDS)
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return []
    except dns.exception.DNSException as exc:
        raise LookupFailed(type(exc).__name__) from exc
    if rdtype == TXT:
        return [b"".join(record.strings).decode("utf-8", "replace") for record in answer]
    return [str(record.to_text()) for record in answer]


class HttpLookupTransport:
    """The production `CheckTransport`."""

    def __init__(self, transport: httpx.BaseTransport | None = None, timeout: float = HTTP_TIMEOUT_SECONDS,
                 retries: int = MAX_RETRIES, sleep: Callable[[float], None] = time.sleep,
                 dns_resolve: DnsResolve = resolve_dns) -> None:
        """Configure the transport.

        Args:
            transport: httpx transport; a MockTransport in tests, the network otherwise.
            timeout: Per-request timeout in seconds.
            retries: Extra attempts after a retryable failure.
            sleep: Backoff sleep (injected in tests).
            dns_resolve: DNS resolver function.
        """
        self._transport = transport
        self._timeout = timeout
        self._retries = retries
        self._sleep = sleep
        self._dns_resolve = dns_resolve

    def _attempt(self, client: httpx.Client, url: str) -> Any:
        """Make one GET.

        Args:
            client: httpx client.
            url: URL.

        Returns:
            Decoded JSON.

        Raises:
            TransientLookupFailure: When the attempt may be retried (network error, 429, 5xx).
            LookupFailed: On a failure that must not be retried (other HTTP errors, invalid JSON).
        """
        try:
            response = client.get(url)
        except httpx.HTTPError as exc:
            raise TransientLookupFailure(type(exc).__name__) from exc
        if response.status_code in RETRY_STATUSES:
            raise TransientLookupFailure(f"HTTP {response.status_code}")
        if response.status_code >= HTTP_ERROR_FROM:
            raise LookupFailed(f"HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise LookupFailed("invalid JSON") from exc

    def get_json(self, url: str) -> Any:
        """GET a URL and decode JSON, retrying transient failures with exponential backoff.

        Args:
            url: Absolute URL.

        Returns:
            Decoded JSON.

        Raises:
            LookupFailed: When every attempt fails or the failure is not transient.
        """
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        with httpx.Client(transport=self._transport, timeout=self._timeout, headers=headers) as client:
            for attempt in range(self._retries):
                try:
                    return self._attempt(client, url)
                except TransientLookupFailure:
                    self._sleep(BACKOFF_SECONDS * BACKOFF_FACTOR ** attempt)
            return self._attempt(client, url)

    def resolve(self, name: str, rdtype: str) -> list[str]:
        """Resolve DNS records.

        Args:
            name: DNS name.
            rdtype: Record type.

        Returns:
            Record texts.

        Raises:
            LookupFailed: On resolver failure.
        """
        return self._dns_resolve(name, rdtype)


@dataclass(frozen=True)
class BrokerLookup:
    """A configured broker-vetting integration: the FMCSA key and the transport."""

    fmcsa_key: str = field(repr=False)
    transport: CheckTransport


def broker_lookup_from_settings(settings: Settings,
                                transport: httpx.BaseTransport | None = None) -> BrokerLookup | None:
    """Build the broker lookup from settings.

    Args:
        settings: Application settings.
        transport: Optional httpx transport.

    Returns:
        The lookup, or None when FMCSA_WEBKEY is unset (the check route then answers 503).
    """
    key = settings.fmcsa_webkey
    if key is None or not key.get_secret_value():
        return None
    return BrokerLookup(key.get_secret_value(), HttpLookupTransport(transport=transport))
