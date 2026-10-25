"""EdDSA access tokens with a `kid` header, verified against a keyring and the injected clock.

Claims: iss="manceps", aud ("firm" or "portal"), sub, tid, role, sid, epoch, iat, exp. Expiry is checked against the
application clock (not the system clock), so tests can move time deterministically.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal, cast

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key

from manceps_core.clock import Clock
from manceps_core.tenancy import ROLES, Role

from ..settings import Settings

ISSUER = "manceps"
AUD_FIRM = "firm"
AUD_PORTAL = "portal"
ALGORITHM = "EdDSA"
REQUIRED_CLAIMS = ("iss", "aud", "sub", "sid", "role", "exp", "iat")

Audience = Literal["firm", "portal"]


class TokenError(Exception):
    """A token is malformed, expired, or not ours."""

    def __init__(self, code: str, message: str) -> None:
        """Create the error.

        Args:
            code: Stable error code (invalid_token or token_expired).
            message: Safe explanation.
        """
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class TokenClaims:
    """Verified claims of an access token."""

    sub: str
    tid: str | None
    role: Role
    sid: str
    epoch: int
    aud: Audience
    exp: int


@dataclass(frozen=True)
class IssuedToken:
    """A freshly signed token."""

    token: str
    expires_in: int


@dataclass(frozen=True)
class Keyring:
    """Signing key for the active kid plus every verification key."""

    active_kid: str
    private_key: Ed25519PrivateKey
    public_keys: dict[str, Ed25519PublicKey]

    @classmethod
    def from_settings(cls, settings: Settings) -> Keyring | None:
        """Load keys from JWT_ACTIVE_KID and JWT_KEYS_JSON.

        Args:
            settings: Application settings.

        Returns:
            The keyring, or None when either setting is absent (auth routes then answer 503).

        Raises:
            ValueError: If the JSON or a PEM is malformed, a key is not Ed25519, or the active kid has no private key.
        """
        if not settings.jwt_active_kid or settings.jwt_keys_json is None:
            return None
        entries: Any = json.loads(settings.jwt_keys_json.get_secret_value())
        if not isinstance(entries, dict) or settings.jwt_active_kid not in entries:
            raise ValueError("JWT_KEYS_JSON must be an object containing JWT_ACTIVE_KID")
        public_keys: dict[str, Ed25519PublicKey] = {}
        for kid, entry in cast(dict[str, Any], entries).items():
            key = load_pem_public_key(str(entry["public_pem"]).encode("ascii"))
            if not isinstance(key, Ed25519PublicKey):
                raise ValueError(f"key {kid!r} is not Ed25519")
            public_keys[kid] = key
        private_pem = cast(dict[str, Any], entries[settings.jwt_active_kid]).get("private_pem")
        if not private_pem:
            raise ValueError("the active JWT key has no private_pem")
        private_key = load_pem_private_key(str(private_pem).encode("ascii"), password=None)
        if not isinstance(private_key, Ed25519PrivateKey):
            raise ValueError("the active JWT private key is not Ed25519")
        return cls(settings.jwt_active_kid, private_key, public_keys)


def _parse_claims(payload: dict[str, Any]) -> TokenClaims:
    """Type-check decoded claims.

    Args:
        payload: Claims from PyJWT.

    Returns:
        The typed claims.

    Raises:
        TokenError: If a claim has the wrong type or value.
    """
    sub, sid, role, tid, epoch = (payload.get(name) for name in ("sub", "sid", "role", "tid", "epoch"))
    aud, exp = payload.get("aud"), payload.get("exp")
    valid = (isinstance(sub, str) and sub and isinstance(sid, str) and sid and role in ROLES
             and (tid is None or isinstance(tid, str)) and isinstance(epoch, int) and isinstance(exp, int)
             and aud in (AUD_FIRM, AUD_PORTAL))
    if not valid:
        raise TokenError("invalid_token", "the access token is not valid")
    return TokenClaims(sub=cast(str, sub), tid=cast(str | None, tid), role=cast(Role, role), sid=cast(str, sid),
                       epoch=cast(int, epoch), aud=cast(Audience, aud), exp=cast(int, exp))


class TokenService:
    """Issues and verifies access tokens."""

    def __init__(self, keyring: Keyring, clock: Clock, access_ttl: timedelta, scoped_ttl: timedelta) -> None:
        """Bind keys, clock and lifetimes.

        Args:
            keyring: Keys.
            clock: Time source.
            access_ttl: Lifetime of firm access tokens.
            scoped_ttl: Lifetime of portal tokens.
        """
        self._keyring = keyring
        self._clock = clock
        self._ttl: dict[Audience, timedelta] = {AUD_FIRM: access_ttl, AUD_PORTAL: scoped_ttl}

    @classmethod
    def from_settings(cls, settings: Settings, clock: Clock) -> TokenService | None:
        """Build the service from settings.

        Args:
            settings: Application settings.
            clock: Time source.

        Returns:
            The service, or None when JWT keys are not configured.

        Raises:
            ValueError: If the configured keys are malformed.
        """
        keyring = Keyring.from_settings(settings)
        if keyring is None:
            return None
        return cls(keyring, clock, timedelta(minutes=settings.access_token_minutes),
                   timedelta(minutes=settings.scoped_token_minutes))

    def issue(self, *, sub: str, tid: str | None, role: Role, sid: str, epoch: int,
              audience: Audience) -> IssuedToken:
        """Sign a token.

        Args:
            sub: User id (or carrier id for portal tokens).
            tid: Firm id, or None while provisioning.
            role: Role claim.
            sid: Session id (or scoped link id).
            epoch: The user's token epoch at issue time.
            audience: "firm" or "portal".

        Returns:
            The token and its lifetime in seconds.
        """
        ttl = self._ttl[audience]
        issued_at = int(self._clock().timestamp())
        claims = {"iss": ISSUER, "aud": audience, "sub": sub, "tid": tid, "role": role, "sid": sid, "epoch": epoch,
                  "iat": issued_at, "exp": issued_at + int(ttl.total_seconds())}
        token = jwt.encode(claims, self._keyring.private_key, algorithm=ALGORITHM,
                           headers={"kid": self._keyring.active_kid})
        return IssuedToken(token=token, expires_in=int(ttl.total_seconds()))

    def verify(self, token: str, audience: Audience) -> TokenClaims:
        """Verify signature, kid, issuer, audience and expiry.

        Args:
            token: Compact JWT.
            audience: Required audience.

        Returns:
            The verified claims.

        Raises:
            TokenError: invalid_token for any verification failure, token_expired after `exp`.
        """
        try:
            kid = jwt.get_unverified_header(token).get("kid")
            key = self._keyring.public_keys.get(kid) if isinstance(kid, str) else None
            if key is None:
                raise TokenError("invalid_token", "the access token is not valid")
            payload = jwt.decode(token, key, algorithms=[ALGORITHM], audience=audience, issuer=ISSUER,
                                 options={"require": list(REQUIRED_CLAIMS), "verify_exp": False,
                                          "verify_iat": False})
        except jwt.InvalidTokenError as exc:
            raise TokenError("invalid_token", "the access token is not valid") from exc
        claims = _parse_claims(payload)
        if claims.exp <= int(self._clock().timestamp()):
            raise TokenError("token_expired", "the access token has expired")
        return claims
