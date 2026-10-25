"""Broker vetting: FMCSA operating status and authority, bond, domain age and email DNS (ported from hermes-freight).

Every check fails closed: a lookup error or an unexpected response is `unknown`, never `pass`. The MC and DOT must be
proven to belong to one FMCSA record (`mc_dot_match`). The verdict is `looks_ok` only when every check that ran
passed and operating status, broker authority, bond and identity are all among them.
HTTP and DNS go through an injected `CheckTransport`, so this module stays pure and tests use a fake. Check
details never contain the FMCSA key or request URLs.
"""

from __future__ import annotations

import re
import urllib.parse
from abc import abstractmethod
from datetime import datetime
from typing import Any, Protocol, cast

from ..mongo import MongoDb
from .reference import bond_status

FMCSA_BASE = "https://mobile.fmcsa.dot.gov/qc/services/carriers"
RDAP_BASE = "https://rdap.org/domain/"
DOMAIN_MIN_AGE_DAYS = 365
DOMAIN_FAIL_AGE_DAYS = 90
FREE_EMAIL_DOMAINS = frozenset({
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "aol.com", "icloud.com",
    "proton.me", "protonmail.com", "gmx.com", "mail.com", "yandex.com",
})
CRITICAL = ("fmcsa_operating", "broker_authority", "bond")
IDENTITY = "mc_dot_match"
REQUIRED_FOR_OK = (*CRITICAL, IDENTITY)
PASS, FAIL, WARN, UNKNOWN = "pass", "fail", "warn", "unknown"
EMAIL_DOMAIN = re.compile(r"[^@\s]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
NON_DIGITS = re.compile(r"[^0-9]")  # ASCII only: \D would keep Arabic-Indic and other Unicode digits
PARSE_ERRORS = (ValueError, TypeError, KeyError, AttributeError, StopIteration)


class LookupFailed(Exception):
    """A lookup could not be completed. The message is safe to store and show (no URLs or keys)."""


class CheckTransport(Protocol):
    """HTTP JSON and DNS access used by the checks."""

    @abstractmethod
    def get_json(self, url: str) -> Any:
        """GET a URL and decode its JSON body.

        Args:
            url: Absolute URL.

        Returns:
            Decoded JSON.

        Raises:
            LookupFailed: On network errors, HTTP errors or a body that is not JSON.
        """

    @abstractmethod
    def resolve(self, name: str, rdtype: str) -> list[str]:
        """Resolve DNS records as text; an empty list when the name has none.

        Args:
            name: DNS name.
            rdtype: Record type, e.g. "MX" or "TXT".

        Returns:
            Record texts.

        Raises:
            LookupFailed: On resolver failure other than "no records".
        """


def _check(name: str, status: str, detail: str, **data: Any) -> dict[str, Any]:
    """Build one check result.

    Args:
        name: Check id.
        status: pass, fail, warn or unknown.
        detail: Human-readable explanation.
        **data: Raw values backing the result.

    Returns:
        Check result mapping.
    """
    return {"check": name, "status": status, "detail": detail, **data}


def _reason(exc: Exception) -> str:
    """Describe a failure without leaking URLs, keys or response bodies.

    Args:
        exc: The failure.

    Returns:
        The LookupFailed message, or the exception type name.
    """
    return str(exc) if isinstance(exc, LookupFailed) else type(exc).__name__


def _as_dict(value: object) -> dict[str, Any] | None:
    """Narrow decoded JSON to an object.

    Args:
        value: Decoded JSON.

    Returns:
        The object, or None when it is not one.
    """
    return cast(dict[str, Any], value) if isinstance(value, dict) else None


def _as_list(value: object) -> list[Any]:
    """Narrow decoded JSON to an array.

    Args:
        value: Decoded JSON.

    Returns:
        The array, or an empty list when it is not one.
    """
    return cast(list[Any], value) if isinstance(value, list) else []


def _payload(transport: CheckTransport, url: str) -> dict[str, Any]:
    """Fetch an FMCSA response that must be a JSON object (null counts as empty, like the plugin).

    Args:
        transport: Lookup transport.
        url: URL.

    Returns:
        The object.

    Raises:
        LookupFailed: On transport failure.
        ValueError: When the body is not an object.
    """
    body = transport.get_json(url)
    payload = {} if body is None else _as_dict(body)
    if payload is None:
        raise ValueError("unexpected FMCSA response")
    return payload


def _dot_record(transport: CheckTransport, dot: str, key: str) -> dict[str, Any] | None:
    """Look up the FMCSA carrier record by USDOT number.

    Args:
        transport: Lookup transport.
        dot: USDOT digits.
        key: QCMobile web key.

    Returns:
        The carrier record, or None when FMCSA has no match.

    Raises:
        LookupFailed: On transport failure.
        ValueError: On malformed responses.
    """
    query = urllib.parse.urlencode({"webKey": key})
    content = _as_dict(_payload(transport, f"{FMCSA_BASE}/{dot}?{query}").get("content"))
    return _as_dict(content.get("carrier")) if content is not None else None


def _docket_record(transport: CheckTransport, mc: str, key: str) -> dict[str, Any] | None:
    """Look up the FMCSA carrier record that owns an MC docket.

    Args:
        transport: Lookup transport.
        mc: MC digits.
        key: QCMobile web key.

    Returns:
        The carrier record, or None when FMCSA has no match.

    Raises:
        LookupFailed: On transport failure.
        ValueError: On malformed responses.
    """
    query = urllib.parse.urlencode({"webKey": key})
    records = _as_list(_payload(transport, f"{FMCSA_BASE}/docket-number/{mc}?{query}").get("content"))
    first = _as_dict(records[0]) if records else None
    return _as_dict(first.get("carrier")) if first is not None else None


def _same_number(left: str, right: str) -> bool:
    """Compare two FMCSA numbers ignoring leading zeros.

    Args:
        left: Digits.
        right: Digits.

    Returns:
        True when they are the same number.
    """
    return left.lstrip("0") == right.lstrip("0")


def _identity(transport: CheckTransport, key: str, mc: str, dot: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Resolve the FMCSA record and prove the MC and DOT name the same entity.

    With an MC, the record is the MC docket's owner, and any DOT supplied or stored must be that record's DOT
    (a fake MC presented with a real broker's DOT is the classic double-brokering scam). A DOT alone cannot prove
    who is behind an MC, so it yields `unknown` and the verdict can never be `looks_ok`.

    Args:
        transport: Lookup transport.
        key: QCMobile web key.
        mc: MC digits, may be empty.
        dot: USDOT digits, may be empty.

    Returns:
        (carrier record or None, the mc_dot_match check).

    Raises:
        LookupFailed: On transport failure.
        ValueError: On malformed responses.
    """
    if not mc:
        return _dot_record(transport, dot, key), _check(IDENTITY, UNKNOWN, "no MC number to confirm who holds this DOT")
    carrier = _docket_record(transport, mc, key)
    if carrier is None:
        return None, _check(IDENTITY, FAIL, "no FMCSA record for this MC")
    record_dot = NON_DIGITS.sub("", str(carrier.get("dotNumber") or ""))
    if not record_dot:
        return carrier, _check(IDENTITY, UNKNOWN, "FMCSA reported no DOT number for this MC")
    if dot and not _same_number(dot, record_dot):
        return carrier, _check(IDENTITY, FAIL, "MC and DOT belong to different FMCSA entities", mc_dot=record_dot,
                               given_dot=dot)
    return carrier, _check(IDENTITY, PASS, "MC and DOT belong to the same FMCSA record", dot_number=record_dot)


def _authority_check(payload: dict[str, Any]) -> dict[str, Any]:
    """Interpret the FMCSA authority response for broker authority.

    Args:
        payload: Decoded /authority response.

    Returns:
        The broker_authority check result.
    """
    items = [_as_dict(item) for item in _as_list(payload.get("content"))]
    statuses = [(_as_dict(item.get("carrierAuthority")) or {}).get("brokerAuthorityStatus")
                for item in items if item is not None]
    if "A" in statuses:
        return _check("broker_authority", PASS, "active broker authority", statuses=statuses)
    if statuses and all(status in ("I", "N") for status in statuses):
        return _check("broker_authority", FAIL, "no active broker authority", statuses=statuses)
    return _check("broker_authority", UNKNOWN, "broker authority status not reported", statuses=statuses)


def _fmcsa_checks(transport: CheckTransport, key: str, dot: str, mc: str) -> tuple[list[dict[str, Any]], str]:
    """Run the identity, FMCSA operating-status and broker-authority checks.

    Args:
        transport: Lookup transport.
        key: QCMobile web key ("" when not configured).
        dot: USDOT digits, may be empty.
        mc: MC digits, may be empty.

    Returns:
        Check results and the verified DOT number: the MC docket's DOT, the given DOT when there is no MC, or ""
        when it could not be verified.
    """
    if not key:
        return [_check(name, UNKNOWN, "FMCSA web key not configured") for name in (*CRITICAL[:2], IDENTITY)], ""
    try:
        carrier, identity = _identity(transport, key, mc, dot)
        if carrier is None:
            return [*(_check(name, FAIL, "no FMCSA record for this MC/DOT") for name in CRITICAL[:2]), identity], ""
        if identity["status"] == FAIL:
            return [*(_check(name, FAIL, str(identity["detail"])) for name in CRITICAL[:2]), identity], ""
        verified = NON_DIGITS.sub("", str(carrier.get("dotNumber") or "")) or (dot if not mc else "")
        if not verified:
            return [*(_check(name, UNKNOWN, str(identity["detail"])) for name in CRITICAL[:2]), identity], ""
        allowed = carrier.get("allowedToOperate")
        operating = {"Y": PASS, "N": FAIL}.get(str(allowed), UNKNOWN)
        results = [_check("fmcsa_operating", operating, f"allowedToOperate={allowed!r}",
                          legal_name=carrier.get("legalName"), dot_number=verified)]
        query = urllib.parse.urlencode({"webKey": key})
        results.append(_authority_check(_payload(transport, f"{FMCSA_BASE}/{verified}/authority?{query}")))
        return [*results, identity], verified
    except (LookupFailed, *PARSE_ERRORS) as exc:
        reason = f"FMCSA lookup failed: {_reason(exc)}"
        return [_check(name, UNKNOWN, reason) for name in (*CRITICAL[:2], IDENTITY)], ""


def _domain_age_check(transport: CheckTransport, domain: str, now: datetime) -> dict[str, Any]:
    """Check domain registration age through RDAP.

    Args:
        transport: Lookup transport.
        domain: Registrable domain.
        now: Current UTC time.

    Returns:
        The domain_age check result.
    """
    try:
        body = _as_dict(transport.get_json(RDAP_BASE + urllib.parse.quote(domain))) or {}
        events = [_as_dict(event) or {} for event in _as_list(body.get("events"))]
        registered = str(next(event["eventDate"] for event in events if event.get("eventAction") == "registration"))
        when = datetime.fromisoformat(registered.replace("Z", "+00:00"))
        days = (now - when).days
    except (LookupFailed, *PARSE_ERRORS) as exc:
        return _check("domain_age", UNKNOWN, f"RDAP lookup failed: {_reason(exc)}", domain=domain)
    status = PASS if days >= DOMAIN_MIN_AGE_DAYS else FAIL if days < DOMAIN_FAIL_AGE_DAYS else WARN
    return _check("domain_age", status, f"registered {days} days ago", domain=domain, registered=registered)


def _email_dns_check(transport: CheckTransport, domain: str) -> dict[str, Any]:
    """Check MX, SPF and DMARC records for the broker's email domain.

    Args:
        transport: Lookup transport.
        domain: Email domain.

    Returns:
        The email_dns check result.
    """
    try:
        mx = transport.resolve(domain, "MX")
        spf = [txt for txt in transport.resolve(domain, "TXT") if txt.lower().startswith("v=spf1")]
        dmarc = [txt for txt in transport.resolve(f"_dmarc.{domain}", "TXT") if txt.lower().startswith("v=dmarc1")]
    except LookupFailed as exc:
        return _check("email_dns", UNKNOWN, f"DNS lookup failed: {exc}", domain=domain)
    if not mx:
        return _check("email_dns", FAIL, "domain has no MX records", domain=domain)
    missing = [name for name, found in (("SPF", spf), ("DMARC", dmarc)) if not found]
    detail = f"missing {', '.join(missing)}" if missing else "MX, SPF and DMARC present"
    return _check("email_dns", WARN if missing else PASS, detail, domain=domain, mx=mx, spf=spf, dmarc=dmarc)


def _email_checks(transport: CheckTransport, email: str, now: datetime) -> list[dict[str, Any]]:
    """Run the domain checks for a broker email address.

    Args:
        transport: Lookup transport.
        email: Broker contact email, may be empty.
        now: Current UTC time.

    Returns:
        Check results (empty when no email was given).
    """
    match = EMAIL_DOMAIN.fullmatch(email.strip())
    if not match:
        return [_check("email_domain", UNKNOWN, "no valid email given")] if email.strip() else []
    domain = match.group(1).lower()
    if domain in FREE_EMAIL_DOMAINS:
        return [_check("email_domain", WARN, f"free email provider {domain}; brokers use company domains")]
    return [_domain_age_check(transport, domain, now), _email_dns_check(transport, domain)]


def verdict(checks: list[dict[str, Any]]) -> str:
    """Combine check results into a booking verdict.

    Args:
        checks: Check results.

    Returns:
        "do_not_book" on any failure; "looks_ok" only when every required check is present and every check that ran
        passed (a single `unknown` or `warn` caps it at "review"); else "review".
    """
    statuses = [str(check["status"]) for check in checks]
    if FAIL in statuses:
        return "do_not_book"
    present = {check["check"] for check in checks}
    if all(status == PASS for status in statuses) and present.issuperset(REQUIRED_FOR_OK):
        return "looks_ok"
    return "review"


def run_check(transport: CheckTransport, fmcsa_key: str, mc: str, dot: str, email: str, reference_db: MongoDb,
              now: datetime) -> dict[str, Any]:
    """Vet a broker by MC or DOT number and optional contact email.

    Args:
        transport: Lookup transport.
        fmcsa_key: QCMobile web key ("" makes the FMCSA checks unknown).
        mc: MC number in any format, may be empty.
        dot: DOT number in any format, may be empty.
        email: Broker contact email, may be empty.
        reference_db: The shared FMCSA reference database.
        now: Current UTC time.

    Returns:
        {mc_number, dot_number, verdict, checks}.

    Raises:
        ValueError: If neither MC nor DOT has digits.
    """
    mc, dot = NON_DIGITS.sub("", mc), NON_DIGITS.sub("", dot)
    if not mc and not dot:
        raise ValueError("give mc_number or dot_number")
    checks, verified_dot = _fmcsa_checks(transport, fmcsa_key, dot, mc)
    checks += _email_checks(transport, email, now)
    checks.append(bond_status(reference_db, mc, verified_dot if mc else dot, now))
    return {"mc_number": mc or None, "dot_number": verified_dot or None, "verdict": verdict(checks),
            "checks": checks}
