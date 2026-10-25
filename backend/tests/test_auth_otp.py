"""Phone OTP login and signup: new users queue a signup, codes fail closed, Twilio unset is 503, limits bite."""

from __future__ import annotations

from datetime import timedelta

from authkit import NATIVE, PHONE_NEW, PHONE_OWNER_A, bearer, one, otp_login, platform, seed_firm
from conftest import GOOD_CODE, TENANT_A, FakeClock, FakeVerifier
from fastapi.testclient import TestClient

from manceps_api.app import create_app
from manceps_api.integrations.configured import Integrations
from manceps_api.settings import Settings
from manceps_core.mongo import MongoClientT

SIGNUP = {"firm_name": "Lone Star Dispatch", "accept_terms": True}


def test_otp_new_user_creates_signup_and_tokens(client: TestClient, mongo_client: MongoClientT) -> None:
    body = otp_login(client, "(214) 555-0199", **SIGNUP)
    assert body["state"] == "provisioning"
    assert body["tenant_id"] is None
    assert body["role"] == "owner"
    assert body["token_type"] == "bearer"  # noqa: S105 - the token type name
    assert body["expires_in"] == 15 * 60
    assert body["refresh_token"]
    db = platform(mongo_client)
    user = db["users"].find_one({"phone": PHONE_NEW})
    assert user is not None and user["token_epoch"] == 0
    signup = db["signups"].find_one({"_id": body["signup_token"]})
    assert signup is not None
    assert signup["status"] == "pending"
    assert signup["user_id"] == user["_id"]
    assert signup["firm_name"] == "Lone Star Dispatch"
    assert signup["terms_accepted_at"] is not None
    me = client.get("/v1/me", headers=bearer(body["access_token"]))
    assert me.status_code == 200
    firm = client.get("/v1/firm", headers=bearer(body["access_token"]))
    assert firm.status_code == 409
    assert firm.json()["error"]["code"] == "firm_provisioning"


def test_otp_existing_user_gets_firm_token(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    seed_firm(mongo_client, clock, TENANT_A, PHONE_OWNER_A)
    body = otp_login(client, PHONE_OWNER_A)
    assert body["state"] == "active"
    assert body["tenant_id"] == TENANT_A
    assert body["role"] == "owner"
    assert body.get("signup_token") is None
    assert one(platform(mongo_client), "users", {"phone": PHONE_OWNER_A})["last_login_at"] == clock()


def test_otp_new_user_without_signup_details_is_422(client: TestClient, verifier: FakeVerifier) -> None:
    response = client.post("/v1/auth/otp/verify", json={"phone": PHONE_NEW, "code": GOOD_CODE})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "signup_details_required"
    assert verifier.checked == []


def test_otp_wrong_code_400(client: TestClient, mongo_client: MongoClientT) -> None:
    response = client.post("/v1/auth/otp/verify", json={"phone": PHONE_NEW, "code": "999999", **SIGNUP})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_code"
    assert platform(mongo_client)["users"].count_documents({}) == 0
    assert platform(mongo_client)["signups"].count_documents({}) == 0


def test_otp_validation_errors(client: TestClient) -> None:
    assert client.post("/v1/auth/otp/start", json={"phone": "12345"}).status_code == 422
    assert client.post("/v1/auth/otp/verify", json={"phone": PHONE_NEW, "code": "ab"}).status_code == 422
    bad_terms = client.post("/v1/auth/otp/verify", json={"phone": PHONE_NEW, "code": GOOD_CODE,
                                                         "firm_name": "Lone Star", "accept_terms": False})
    assert bad_terms.status_code == 422


def test_otp_start_sends_code(client: TestClient, verifier: FakeVerifier) -> None:
    response = client.post("/v1/auth/otp/start", json={"phone": "214-555-0199"})
    assert response.status_code == 202
    assert response.json() == {"sent": True}
    assert verifier.sent == [PHONE_NEW]


def test_twilio_unset_503(settings: Settings, mongo_client: MongoClientT, clock: FakeClock) -> None:
    app = create_app(settings, mongo_client, clock=clock, integrations=Integrations(verifier=None, mailer=None))
    with TestClient(app) as client:
        start = client.post("/v1/auth/otp/start", json={"phone": PHONE_NEW})
        verify = client.post("/v1/auth/otp/verify", json={"phone": PHONE_NEW, "code": GOOD_CODE, **SIGNUP})
    for response in (start, verify):
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "twilio_not_configured"


def test_verifier_outage_is_502(client: TestClient, verifier: FakeVerifier) -> None:
    verifier.fail = True
    start = client.post("/v1/auth/otp/start", json={"phone": PHONE_NEW})
    verify = client.post("/v1/auth/otp/verify", json={"phone": PHONE_NEW, "code": GOOD_CODE, **SIGNUP})
    for response in (start, verify):
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "verify_unavailable"


def test_otp_send_limit_per_phone(client: TestClient, clock: FakeClock) -> None:
    for _ in range(3):
        assert client.post("/v1/auth/otp/start", json={"phone": PHONE_NEW}).status_code == 202
    blocked = client.post("/v1/auth/otp/start", json={"phone": PHONE_NEW})
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    clock.advance(timedelta(hours=1, seconds=1))
    assert client.post("/v1/auth/otp/start", json={"phone": PHONE_NEW}).status_code == 202


def test_otp_send_limit_per_ip(client: TestClient) -> None:
    for index in range(10):
        assert client.post("/v1/auth/otp/start", json={"phone": f"+1214555{1000 + index}"}).status_code == 202
    assert client.post("/v1/auth/otp/start", json={"phone": "+12145552000"}).status_code == 429


def test_eleventh_otp_check_per_phone_is_429(client: TestClient) -> None:
    for _ in range(10):
        response = client.post("/v1/auth/otp/verify", json={"phone": PHONE_NEW, "code": "000000", **SIGNUP})
        assert response.status_code == 400
    eleventh = client.post("/v1/auth/otp/verify", json={"phone": PHONE_NEW, "code": GOOD_CODE, **SIGNUP})
    assert eleventh.status_code == 429


def test_signup_status_route(client: TestClient, mongo_client: MongoClientT) -> None:
    body = otp_login(client, PHONE_NEW, **SIGNUP)
    token = body["signup_token"]
    assert client.get(f"/v1/signup/status/{token}").json() == {"status": "pending", "tenant_id": None,
                                                            "message": None}
    platform(mongo_client)["signups"].update_one({"_id": token}, {"$set": {"status": "ready", "tenant_id": TENANT_A}})
    assert client.get(f"/v1/signup/status/{token}").json() == {"status": "ready", "tenant_id": TENANT_A,
                                                            "message": None}
    platform(mongo_client)["signups"].update_one({"_id": token}, {"$set": {"status": "failed"}})
    failed = client.get(f"/v1/signup/status/{token}").json()
    assert failed["status"] == "failed" and failed["tenant_id"] is None
    missing = client.get("/v1/signup/status/not-a-real-token")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
    assert client.get("/v1/signup/status/" + "x" * 200).status_code == 422


def test_second_signup_for_same_phone_logs_in(client: TestClient, mongo_client: MongoClientT) -> None:
    first = otp_login(client, PHONE_NEW, **SIGNUP)
    second = otp_login(client, PHONE_NEW, **SIGNUP)
    assert second["user_id"] == first["user_id"]
    assert second["state"] == "provisioning"
    assert platform(mongo_client)["signups"].count_documents({}) == 1


def test_legacy_signup_without_user_conflicts(client: TestClient, mongo_client: MongoClientT,
                                              clock: FakeClock) -> None:
    platform(mongo_client)["signups"].insert_one({"_id": "legacy", "phone": PHONE_NEW, "firm_name": "Old",
                                                  "status": "pending", "attempts": 0, "created_at": clock()})
    response = client.post("/v1/auth/otp/verify", json={"phone": PHONE_NEW, "code": GOOD_CODE, **SIGNUP},
                           headers=NATIVE)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "already_signed_up"


def test_browser_client_gets_refresh_cookie(client: TestClient) -> None:
    response = client.post("/v1/auth/otp/verify", json={"phone": PHONE_NEW, "code": GOOD_CODE, **SIGNUP})
    assert response.status_code == 200
    assert response.json()["refresh_token"] is None
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("mc_refresh=")
    for attribute in ("HttpOnly", "Secure", "SameSite=lax", "Path=/v1/auth"):
        assert attribute.lower() in cookie.lower()


def test_auth_routes_503_without_jwt_keys(mongo_client: MongoClientT, clock: FakeClock) -> None:
    app = create_app(Settings(env="test"), mongo_client, clock=clock,
                     integrations=Integrations(verifier=FakeVerifier(), mailer=None))
    with TestClient(app) as client:
        login = client.post("/v1/auth/otp/verify", json={"phone": PHONE_NEW, "code": GOOD_CODE, **SIGNUP})
        me = client.get("/v1/me", headers=bearer("anything"))
    for response in (login, me):
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "auth_not_configured"

