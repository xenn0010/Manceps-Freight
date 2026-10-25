"""Regression tests for the WP1.1-1.3 review findings on auth, team, idempotency, proxies, body size and activation."""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from authkit import NATIVE, PHONE_NEW, PHONE_OWNER_A, add_member, bearer, otp_login, platform
from conftest import GOOD_CODE, TENANT_A, TEST_KEYS_JSON, TEST_KID, FakeClock, FakeVerifier
from datakit import CARRIER, error_code, seed_firms
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from test_firm_activate import _ready_signup  # pyright: ignore[reportPrivateUsage]

from manceps_api.app import body_limit_rules, create_app
from manceps_api.auth import sessions
from manceps_api.errors import ApiError
from manceps_api.integrations.configured import Integrations
from manceps_api.middleware import BodyLimitMiddleware, BodyLimitRule
from manceps_api.requestinfo import client_ip
from manceps_api.routes import members as members_routes
from manceps_api.settings import Settings
from manceps_core import accounts
from manceps_core.mongo import Doc, MongoClientT
from manceps_core.tenancy import PlatformRepo, TenantDb
from manceps_worker.firm_activate import firm_activate

SIGNUP = {"firm_name": "Lone Star Dispatch", "accept_terms": True}
ONE_MIB = 1024 * 1024
SECOND_OWNER = "+12145550777"


def _refresh(client: TestClient, raw: str) -> Any:
    """Call the refresh route as a native client.

    Args:
        client: Test client.
        raw: Refresh token.

    Returns:
        The response.
    """
    return client.post("/v1/auth/refresh", json={"refresh_token": raw}, headers=NATIVE)


def _logout_all(mongo_client: MongoClientT, user_id: str, clock: FakeClock) -> None:
    """Run exactly what POST /v1/auth/logout-all does.

    Args:
        mongo_client: Database client.
        user_id: User id.
        clock: Fake clock.
    """
    accounts.bump_epoch(platform(mongo_client), user_id)
    sessions.revoke_user(platform(mongo_client), user_id, clock())


@pytest.mark.parametrize("moment", ["before_successor", "after_successor"])
def test_f4_refresh_racing_logout_all_fails(client: TestClient, mongo_client: MongoClientT, clock: FakeClock,
                                            monkeypatch: pytest.MonkeyPatch, moment: str) -> None:
    seed_firms(client, mongo_client, clock)
    login = otp_login(client, PHONE_OWNER_A)
    real_create = sessions.create_session

    def interleaved(*args: Any, **kwargs: Any) -> tuple[Doc, str]:
        if moment == "before_successor":
            _logout_all(mongo_client, login["user_id"], clock)
            return real_create(*args, **kwargs)
        created = real_create(*args, **kwargs)
        _logout_all(mongo_client, login["user_id"], clock)
        return created

    monkeypatch.setattr(sessions, "create_session", interleaved)
    refreshed = _refresh(client, login["refresh_token"])
    monkeypatch.undo()
    assert refreshed.status_code == 401
    assert sessions.active_sessions(platform(mongo_client), login["user_id"], clock()) == []


def test_f4_refresh_requires_current_epoch(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    seed_firms(client, mongo_client, clock)
    login = otp_login(client, PHONE_OWNER_A)
    accounts.bump_epoch(platform(mongo_client), login["user_id"])
    assert _refresh(client, login["refresh_token"]).status_code == 401


def test_f6_wrong_code_is_the_same_for_known_and_unknown_phones(client: TestClient, mongo_client: MongoClientT,
                                                                clock: FakeClock) -> None:
    seed_firms(client, mongo_client, clock)
    unknown = client.post("/v1/auth/otp/verify", json={"phone": PHONE_NEW, "code": "000000"})
    known = client.post("/v1/auth/otp/verify", json={"phone": PHONE_OWNER_A, "code": "000000"})
    assert unknown.status_code == known.status_code == 400
    assert unknown.json() == known.json()


def test_f6_unknown_phones_are_rate_limited(client: TestClient) -> None:
    for _ in range(10):
        assert client.post("/v1/auth/otp/verify", json={"phone": PHONE_NEW, "code": "000000"}).status_code == 400
    assert client.post("/v1/auth/otp/verify", json={"phone": PHONE_NEW, "code": GOOD_CODE}).status_code == 429


def test_f6_signup_ticket_finishes_signup_once(client: TestClient, mongo_client: MongoClientT, clock: FakeClock,
                                               verifier: FakeVerifier) -> None:
    first = client.post("/v1/auth/otp/verify", json={"phone": PHONE_NEW, "code": GOOD_CODE})
    assert first.status_code == 422 and error_code(first) == "signup_details_required"
    ticket = first.json()["error"]["details"]["signup_ticket"]
    assert re.fullmatch(r"mcs_[A-Za-z0-9_-]{43}", ticket)
    assert platform(mongo_client)["users"].count_documents({}) == 0
    other = client.post("/v1/auth/otp/verify", json={"phone": "+12145550198", "signup_ticket": ticket, **SIGNUP})
    assert other.status_code == 400
    done = client.post("/v1/auth/otp/verify", json={"phone": PHONE_NEW, "signup_ticket": ticket, **SIGNUP},
                       headers=NATIVE)
    assert done.status_code == 200, done.text
    assert done.json()["state"] == "provisioning" and done.json()["signup_token"]
    assert verifier.checked == [(PHONE_NEW, GOOD_CODE)]
    again = client.post("/v1/auth/otp/verify", json={"phone": PHONE_NEW, "signup_ticket": ticket, **SIGNUP})
    assert again.status_code == 400 and error_code(again) == "invalid_ticket"
    late = client.post("/v1/auth/otp/verify", json={"phone": "+12145550197", "code": GOOD_CODE}).json()
    clock.advance(timedelta(hours=1))
    expired = client.post("/v1/auth/otp/verify", json={"phone": "+12145550197",
                                                       "signup_ticket": late["error"]["details"]["signup_ticket"],
                                                       **SIGNUP})
    assert expired.status_code == 400
    both = client.post("/v1/auth/otp/verify", json={"phone": PHONE_NEW, "code": GOOD_CODE, "signup_ticket": ticket})
    assert both.status_code == 422


def _race(repo: PlatformRepo, first: Doc, second: Doc, change: Any, clock: FakeClock,
          monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Run two owner changes so the second runs completely inside the first one's owner count.

    Args:
        repo: Firm-confined platform repo.
        first: Membership changed by the outer request.
        second: Membership changed by the inner request.
        change: Callable(repo, membership, now) under test.
        clock: Fake clock.
        monkeypatch: Pytest monkeypatch.

    Returns:
        Outcomes: "ok" or the error code, inner first.
    """
    outcomes: list[str] = []
    original = PlatformRepo.count_documents
    nested = {"done": False}

    def run(membership: Doc) -> None:
        try:
            change(repo, membership, clock())
            outcomes.append("ok")
        except ApiError as exc:
            outcomes.append(exc.code)

    def interleaved(self: PlatformRepo, collection: str, query: Any) -> int:
        if not nested["done"]:
            nested["done"] = True
            run(second)
        return original(self, collection, query)

    monkeypatch.setattr(PlatformRepo, "count_documents", interleaved)
    run(first)
    monkeypatch.undo()
    return outcomes


@pytest.mark.parametrize("action", ["remove", "demote"])
def test_f7_concurrent_owner_changes_keep_an_owner(client: TestClient, mongo_client: MongoClientT, clock: FakeClock,
                                                   monkeypatch: pytest.MonkeyPatch, action: str) -> None:
    seed_firms(client, mongo_client, clock)
    add_member(mongo_client, clock, TENANT_A, SECOND_OWNER, "owner")
    repo = PlatformRepo(platform(mongo_client), TENANT_A)
    first, second = repo.find("memberships", {"role": "owner"}, sort=[("created_at", 1), ("_id", 1)])

    def change(target_repo: PlatformRepo, membership: Doc, now: Any) -> None:
        if action == "remove":
            members_routes.remove_membership(target_repo, membership, now)
        else:
            members_routes.change_membership_role(target_repo, membership, "dispatcher", now)

    outcomes = _race(repo, first, second, change, clock, monkeypatch)
    assert sorted(outcomes) == ["last_owner", "ok"]
    assert repo.count_documents("memberships", {"role": "owner", "status": "active"}) == 1


def test_f8_invitation_needs_a_verified_email(client: TestClient, mongo_client: MongoClientT,
                                              clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    invite = client.post("/v1/members/invitations", json={"email": "alice@corp.com", "role": "dispatcher"},
                         headers=firms.headers("owner"))
    assert invite.status_code == 201
    mallory = otp_login(client, "+13125550000", **SIGNUP)
    claim = client.patch("/v1/me", json={"email": "alice@corp.com"}, headers=bearer(mallory["access_token"]))
    assert claim.status_code == 200 and claim.json()["user"]["email_verified"] is False
    accepted = client.post("/v1/invitations/accept", json={"token": invite.json()["token"]},
                           headers=bearer(mallory["access_token"]))
    assert accepted.status_code == 403 and error_code(accepted) == "email_not_verified"
    users = platform(mongo_client)["users"]
    users.update_one({"_id": mallory["user_id"]}, {"$set": {"email_verified_at": clock()}})
    changed = client.patch("/v1/me", json={"email": "other@corp.com"}, headers=bearer(mallory["access_token"]))
    assert changed.json()["user"]["email_verified"] is False
    same = client.patch("/v1/me", json={"name": "M"}, headers=bearer(mallory["access_token"]))
    assert same.json()["user"]["email_verified"] is False


def _request(headers: list[tuple[bytes, bytes]], peer: str = "10.9.9.9") -> Request:
    """Build a bare request with headers and a peer address.

    Args:
        headers: Raw headers.
        peer: Immediate peer IP.

    Returns:
        The request.
    """
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "client": (peer, 1234)})


def test_f9_client_ip_counts_trusted_hops_from_the_right() -> None:
    xff = [(b"x-forwarded-for", b"6.6.6.6, 203.0.113.9, 10.0.0.2")]
    assert client_ip(_request(xff), Settings(trust_proxy=True)) == "10.0.0.2"
    assert client_ip(_request(xff), Settings(trust_proxy=True, trusted_proxy_hops=2)) == "203.0.113.9"
    assert client_ip(_request(xff), Settings(trust_proxy=False)) == "10.9.9.9"
    assert client_ip(_request(xff), Settings(trust_proxy=True, trusted_proxy_hops=4)) == "10.9.9.9"
    assert client_ip(_request([]), Settings(trust_proxy=True)) == "10.9.9.9"


def test_f9_spoofed_first_hop_cannot_dodge_ip_limit(mongo_client: MongoClientT, clock: FakeClock) -> None:
    settings = Settings(env="test", jwt_active_kid=TEST_KID, jwt_keys_json=SecretStr(TEST_KEYS_JSON),
                        trust_proxy=True)
    app = create_app(settings, mongo_client, clock=clock, integrations=Integrations(verifier=FakeVerifier()))
    with TestClient(app) as test_client:
        codes = [test_client.post("/v1/auth/otp/start", json={"phone": f"+1214555{1000 + index}"},
                                  headers={"X-Forwarded-For": f"10.0.0.{index}, 203.0.113.9"}).status_code
                 for index in range(11)]
    assert codes.count(202) == 10 and codes[-1] == 429


def _chunks(total: int, size: int) -> Iterator[bytes]:
    """Yield a body in chunks so it is sent without Content-Length.

    Args:
        total: Total bytes.
        size: Chunk size.

    Yields:
        Chunks.
    """
    sent = 0
    while sent < total:
        step = min(size, total - sent)
        sent += step
        yield b"x" * step


def test_f10_request_body_limit(client: TestClient) -> None:
    declared = client.post("/v1/auth/otp/start", content=b"{" + b" " * ONE_MIB + b"}",
                           headers={"Content-Type": "application/json"})
    assert declared.status_code == 413 and error_code(declared) == "payload_too_large"
    streamed = client.post("/v1/auth/otp/start", content=_chunks(ONE_MIB + 1, 64 * 1024),
                           headers={"Content-Type": "application/json"})
    assert streamed.status_code == 413 and error_code(streamed) == "payload_too_large"
    assert "x-request-id" in streamed.headers
    assert client.post("/v1/auth/otp/start", json={"phone": "12345"}).status_code == 422


def test_f10_per_route_override_hook() -> None:
    async def echo(request: Request) -> PlainTextResponse:
        return PlainTextResponse(str(len(await request.body())))

    inner = Starlette(routes=[Route("/upload", echo, methods=["POST"]), Route("/other", echo, methods=["POST"])])
    rules = (BodyLimitRule("POST", re.compile(r"/upload"), 100),)
    with TestClient(BodyLimitMiddleware(inner, 10, rules)) as test_client:
        assert test_client.post("/upload", content=b"x" * 50).text == "50"
        assert test_client.post("/other", content=b"x" * 50).status_code == 413
        assert test_client.post("/other", content=_chunks(50, 7)).status_code == 413
        assert test_client.post("/upload", content=_chunks(101, 7)).status_code == 413
    settings = Settings(import_max_bytes=12345)
    rule = next(rule for rule in body_limit_rules(settings) if rule.pattern.fullmatch("/v1/imports"))
    assert rule.method == "POST" and rule.limit >= settings.import_max_bytes


def test_f13_idempotency_is_scoped_to_the_user(client: TestClient, mongo_client: MongoClientT,
                                               clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    key = {"Idempotency-Key": "shared-key-0001"}
    first = client.post("/v1/carriers", json=CARRIER, headers={**firms.headers("owner"), **key})
    second = client.post("/v1/carriers", json=CARRIER, headers={**firms.headers("dispatcher"), **key})
    assert first.status_code == 201
    assert second.status_code == 409 and error_code(second) == "duplicate_phone"
    assert "Idempotency-Replayed" not in second.headers
    replay = client.post("/v1/carriers", json=CARRIER, headers={**firms.headers("owner"), **key})
    assert replay.headers.get("Idempotency-Replayed") == "true"


def test_f15_firm_activate_refuses_another_signups_firm(mongo_client: MongoClientT, clock: FakeClock) -> None:
    db = platform(mongo_client)
    db["firms"].insert_one({"_id": TENANT_A, "name": "Existing", "slug": TENANT_A, "status": "active",
                            "signup_id": "someone-else"})
    signup = _ready_signup(mongo_client, clock)
    with pytest.raises(ValueError, match="another signup"):
        firm_activate(db, TenantDb(mongo_client), signup, clock)
    assert db["memberships"].count_documents({"user_id": signup["user_id"]}) == 0
