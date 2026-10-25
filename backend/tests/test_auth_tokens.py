"""Access tokens: EdDSA with kid, 15-minute expiry on the injected clock, audience and key checks are 401."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import jwt
from authkit import PHONE_OWNER_A, bearer, otp_login, owner_token
from conftest import TENANT_A, TEST_KID, TEST_PRIVATE_PEM, FakeClock, ed25519_pem_pair
from fastapi.testclient import TestClient

from manceps_core.mongo import MongoClientT


def _claims(token: str) -> dict[str, Any]:
    """Decode a token without verification to read its claims.

    Args:
        token: Access token.

    Returns:
        The claims.
    """
    return jwt.decode(token, options={"verify_signature": False})


def _forge(claims: dict[str, Any], private_pem: str, kid: str) -> str:
    """Sign claims with a given key and kid.

    Args:
        claims: Token claims.
        private_pem: Ed25519 private key PEM.
        kid: Header key id.

    Returns:
        The token.
    """
    return jwt.encode(claims, private_pem, algorithm="EdDSA", headers={"kid": kid})


def test_access_token_shape(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    token = owner_token(client, mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "EdDSA" and header["kid"] == TEST_KID
    claims = _claims(token)
    assert claims["iss"] == "manceps" and claims["aud"] == "firm"
    assert claims["tid"] == TENANT_A and claims["role"] == "owner" and claims["epoch"] == 0
    assert claims["exp"] - claims["iat"] == 15 * 60
    assert claims["sid"].startswith("ses_") and claims["sub"].startswith("usr_")


def test_token_expiry_clock(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    token = owner_token(client, mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    clock.advance(timedelta(minutes=14, seconds=59))
    assert client.get("/v1/firm", headers=bearer(token)).status_code == 200
    clock.advance(timedelta(seconds=1))
    expired = client.get("/v1/firm", headers=bearer(token))
    assert expired.status_code == 401
    assert expired.json()["error"]["code"] == "token_expired"
    assert expired.headers["WWW-Authenticate"] == "Bearer"


def test_wrong_aud_kid_401(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    token = owner_token(client, mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    claims = _claims(token)
    other_private, _other_public = ed25519_pem_pair()
    forged = {
        "wrong_aud": _forge({**claims, "aud": "portal"}, TEST_PRIVATE_PEM, TEST_KID),
        "unknown_kid": _forge(claims, TEST_PRIVATE_PEM, "k-unknown"),
        "wrong_key": _forge(claims, other_private, TEST_KID),
        "wrong_iss": _forge({**claims, "iss": "someone"}, TEST_PRIVATE_PEM, TEST_KID),
        "hs256": jwt.encode(claims, "x" * 32, algorithm="HS256", headers={"kid": TEST_KID}),
    }
    for name, bad in forged.items():
        response = client.get("/v1/firm", headers=bearer(bad))
        assert response.status_code == 401, name
        assert response.json()["error"]["code"] == "invalid_token", name
    assert client.get("/v1/firm", headers=bearer(token)).status_code == 200


def test_missing_or_malformed_credentials_401(client: TestClient) -> None:
    for headers in ({}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer"}, bearer("not.a.jwt")):
        response = client.get("/v1/me", headers=headers)
        assert response.status_code == 401
        assert response.json()["error"]["code"] in {"unauthorized", "invalid_token"}


def test_disabled_user_401(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    token = owner_token(client, mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    mongo_client["platform"]["users"].update_one({"phone": PHONE_OWNER_A}, {"$set": {"status": "disabled"}})
    assert client.get("/v1/me", headers=bearer(token)).status_code == 401


def test_new_login_after_expiry_works(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    owner_token(client, mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    clock.advance(timedelta(hours=2))
    fresh = otp_login(client, PHONE_OWNER_A)["access_token"]
    assert client.get("/v1/firm", headers=bearer(fresh)).status_code == 200
