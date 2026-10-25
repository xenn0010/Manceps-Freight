"""Broker vetting: FMCSA operating status and authority, domain age, email DNS.

Every check fails closed: a lookup error yields "unknown", never "pass". The verdict
is "looks_ok" only when operating status, broker authority, and the bond all pass
and nothing fails or warns.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any

import dns.exception
import dns.resolver
import pymongo.errors

from . import reference, store, tenant

FMCSA_BASE = "https://mobile.fmcsa.dot.gov/qc/services/carriers"
FMCSA_KEY_ENV = "FMCSA_WEBKEY"
RDAP_BASE = "https://rdap.org/domain/"
HTTP_TIMEOUT_SECONDS = 15
DNS_TIMEOUT_SECONDS = 8.0
USER_AGENT = "hermes-freight/0.1 (+broker vetting)"
DOMAIN_MIN_AGE_DAYS = 365
DOMAIN_FAIL_AGE_DAYS = 90
FREE_EMAIL_DOMAINS = frozenset({
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "aol.com", "icloud.com",
    "proton.me", "protonmail.com", "gmx.com", "mail.com", "yandex.com",
})
CRITICAL = ("fmcsa_operating", "broker_authority", "bond")

PASS, FAIL, WARN, UNKNOWN = "pass", "fail", "warn", "unknown"


def _check(name: str, status: str, detail: str, **data: Any) -> dict[str, Any]:
    """Build one check result.

    Args:
        name: Check id.
        status: pass, fail, warn, or unknown.
        detail: Human-readable explanation.
        **data: Raw values backing the result.

    Returns:
        Check result mapping.
    """
    return {"check": name, "status": status, "detail": detail, **data}


def http_get_json(url: str) -> Any:
    """GET a URL and decode JSON.

    Args:
        url: Absolute URL.

    Returns:
        Decoded JSON body.

    Raises:
        urllib.error.URLError: On network or HTTP errors.
        ValueError: If the body is not JSON.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def resolve_txt(name: str, rdtype: str) -> list[str]:
    """Resolve DNS records as strings; empty list when the name has none.

    Args:
        name: DNS name.
        rdtype: Record type, e.g. "MX" or "TXT".

    Returns:
        Record texts.

    Raises:
        dns.exception.DNSException: On resolver failure other than "no records".
    """
    try:
        answer = dns.resolver.resolve(name, rdtype, lifetime=DNS_TIMEOUT_SECONDS)
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return []
    return [b"".join(r.strings).decode() if rdtype == "TXT" else r.to_text() for r in answer]


def _fmcsa_key() -> str | None:
    """Read the FMCSA QCMobile web key through Hermes's secret scope.

    Returns:
        The key, or None when unset.
    """
    return tenant.secret(FMCSA_KEY_ENV)


def _fmcsa_carrier(dot: str, mc: str, key: str) -> dict[str, Any] | None:
    """Look up the FMCSA carrier record by DOT, falling back to MC docket.

    Args:
        dot: USDOT number digits, may be empty.
        mc: MC docket digits, may be empty.
        key: QCMobile web key.

    Returns:
        The carrier record, or None if FMCSA has no match.

    Raises:
        urllib.error.URLError: On network or HTTP errors.
        ValueError: On malformed responses.
    """
    query = urllib.parse.urlencode({"webKey": key})
    if dot:
        content = (http_get_json(f"{FMCSA_BASE}/{dot}?{query}") or {}).get("content")
        return (content or {}).get("carrier") if isinstance(content, dict) else None
    content = (http_get_json(f"{FMCSA_BASE}/docket-number/{mc}?{query}") or {}).get("content")
    if isinstance(content, list) and content:
        return content[0].get("carrier")
    return None


def _fmcsa_checks(dot: str, mc: str) -> tuple[list[dict[str, Any]], str]:
    """Run the FMCSA operating-status and broker-authority checks.

    Args:
        dot: USDOT number digits, may be empty.
        mc: MC docket digits, may be empty.

    Returns:
        Check results and the resolved DOT number ("" if unknown).
    """
    key = _fmcsa_key()
    if not key:
        msg = f"{FMCSA_KEY_ENV} not set; get a free key at mobile.fmcsa.dot.gov"
        return [_check(n, UNKNOWN, msg) for n in CRITICAL], dot
    try:
        carrier = _fmcsa_carrier(dot, mc, key)
        if carrier is None:
            return [_check(n, FAIL, "no FMCSA record for this MC/DOT") for n in CRITICAL], dot
        dot = str(carrier.get("dotNumber") or dot)
        allowed = carrier.get("allowedToOperate")
        operating = {"Y": PASS, "N": FAIL}.get(str(allowed), UNKNOWN)
        results = [_check("fmcsa_operating", operating, f"allowedToOperate={allowed!r}",
                          legal_name=carrier.get("legalName"), dot_number=dot)]
        authority = http_get_json(f"{FMCSA_BASE}/{dot}/authority?{urllib.parse.urlencode({'webKey': key})}")
        results.append(_authority_check(authority))
        return results, dot
    except (urllib.error.URLError, ValueError, AttributeError, TimeoutError) as exc:
        return [_check(n, UNKNOWN, f"FMCSA lookup failed: {exc}") for n in CRITICAL], dot


def _authority_check(payload: Any) -> dict[str, Any]:
    """Interpret the FMCSA authority response for broker authority.

    Args:
        payload: Decoded /authority response.

    Returns:
        The broker_authority check result.
    """
    content = (payload or {}).get("content") if isinstance(payload, dict) else None
    statuses = [
        (item.get("carrierAuthority") or {}).get("brokerAuthorityStatus")
        for item in content or [] if isinstance(item, dict)
    ]
    if "A" in statuses:
        return _check("broker_authority", PASS, "active broker authority", statuses=statuses)
    if statuses and all(s in ("I", "N") for s in statuses):
        return _check("broker_authority", FAIL, "no active broker authority", statuses=statuses)
    return _check("broker_authority", UNKNOWN, "broker authority status not reported", statuses=statuses)


def _domain_age_check(domain: str) -> dict[str, Any]:
    """Check domain registration age through RDAP.

    Args:
        domain: Registrable domain.

    Returns:
        The domain_age check result.
    """
    try:
        events = (http_get_json(RDAP_BASE + urllib.parse.quote(domain)) or {}).get("events") or []
        registered = next(e["eventDate"] for e in events if e.get("eventAction") == "registration")
        when = datetime.fromisoformat(registered.replace("Z", "+00:00"))
    except (urllib.error.URLError, ValueError, KeyError, StopIteration, TimeoutError) as exc:
        return _check("domain_age", UNKNOWN, f"RDAP lookup failed: {exc}", domain=domain)
    days = (datetime.now(UTC) - when).days
    status = PASS if days >= DOMAIN_MIN_AGE_DAYS else FAIL if days < DOMAIN_FAIL_AGE_DAYS else WARN
    return _check("domain_age", status, f"registered {days} days ago", domain=domain, registered=registered)


def _email_dns_check(domain: str) -> dict[str, Any]:
    """Check MX, SPF, and DMARC records for the broker's email domain.

    Args:
        domain: Email domain.

    Returns:
        The email_dns check result.
    """
    try:
        mx = resolve_txt(domain, "MX")
        spf = [t for t in resolve_txt(domain, "TXT") if t.lower().startswith("v=spf1")]
        dmarc = [t for t in resolve_txt(f"_dmarc.{domain}", "TXT") if t.lower().startswith("v=dmarc1")]
    except dns.exception.DNSException as exc:
        return _check("email_dns", UNKNOWN, f"DNS lookup failed: {exc}", domain=domain)
    if not mx:
        return _check("email_dns", FAIL, "domain has no MX records", domain=domain)
    missing = [name for name, found in (("SPF", spf), ("DMARC", dmarc)) if not found]
    status = WARN if missing else PASS
    detail = f"missing {', '.join(missing)}" if missing else "MX, SPF and DMARC present"
    return _check("email_dns", status, detail, domain=domain, mx=mx, spf=spf, dmarc=dmarc)


def _email_checks(email: str) -> list[dict[str, Any]]:
    """Run the domain checks for a broker email address.

    Args:
        email: Broker contact email, may be empty.

    Returns:
        Check results (empty when no email given).
    """
    match = re.fullmatch(r"[^@\s]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})", email.strip())
    if not match:
        return [_check("email_domain", UNKNOWN, "no valid email given")] if email else []
    domain = match.group(1).lower()
    if domain in FREE_EMAIL_DOMAINS:
        return [_check("email_domain", WARN, f"free email provider {domain}; brokers use company domains")]
    return [_domain_age_check(domain), _email_dns_check(domain)]


def verdict(checks: list[dict[str, Any]]) -> str:
    """Combine check results into a booking verdict.

    Args:
        checks: Check results.

    Returns:
        "do_not_book" on any failure, "looks_ok" when both FMCSA checks pass and
        nothing warns, otherwise "review".
    """
    statuses = {c["check"]: c["status"] for c in checks}
    if FAIL in statuses.values():
        return "do_not_book"
    if all(statuses.get(name) == PASS for name in CRITICAL) and WARN not in statuses.values():
        return "looks_ok"
    return "review"


def broker_check(args: dict[str, Any], **kwargs: Any) -> str:
    """Vet a broker by MC or DOT number and optional contact email.

    Args:
        args: {"mc_number": str, "dot_number": str, "email": str}; MC or DOT required.
        **kwargs: Hermes context (session_id is recorded).

    Returns:
        JSON with each check, the verdict, and caveats.
    """
    mc = re.sub(r"\D", "", str(args.get("mc_number", "")))
    dot = re.sub(r"\D", "", str(args.get("dot_number", "")))
    if not mc and not dot:
        return json.dumps({"error": "give mc_number or dot_number"})
    checks, dot = _fmcsa_checks(dot, mc)
    checks += _email_checks(str(args.get("email", "")))
    checks.append(reference.bond_status(mc, dot))
    result = {"mc_number": mc or None, "dot_number": dot or None, "verdict": verdict(checks), "checks": checks}
    try:
        store.collection(store.BROKER_CHECKS).insert_one({**result, "checked_at": store.now(),
                                                          "session_id": kwargs.get("session_id")})
    except (RuntimeError, pymongo.errors.PyMongoError) as exc:
        result["storage_error"] = f"check not saved: {exc}"
    return json.dumps(result, default=str)
