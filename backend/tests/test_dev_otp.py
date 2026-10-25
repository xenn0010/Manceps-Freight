"""Dev-only OTP verifier: DEV_OTP_CODE works only with ENV=dev, never leaks, loses to Twilio, keeps every limit."""

from __future__ import annotations

import pytest
from authkit import PHONE_NEW, bearer, platform
from conftest import TEST_KEYS_JSON, TEST_KID, FakeClock
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from structlog.testing import capture_logs

from manceps_api.app import create_app
from manceps_api.integrations import configured, dev_verifier, twilio_verify
from manceps_api.settings import Settings, load_settings
from manceps_core.mongo import MongoClientT

DEV_CODE = "482915"
WRONG_CODE = "482916"
SIGNUP = {"firm_name": "Lone Star Dispatch", "accept_terms": True}
TWILIO = {"twilio_account_sid": "AC123", "twilio_auth_token": SecretStr("tok"), "twilio_verify_service_sid": "VA456"}
PRODUCTION = {
    "mongodb_uri": SecretStr("mongodb://db.test/"), "jwt_active_kid": "k1",
    "jwt_keys_json": SecretStr('{"k1": {"public_pem": "pub"}}'), "secrets_key": SecretStr("c2VjcmV0"),
    "public_base_url": "https://app.manceps.test",
}
SEND_PER_PHONE = 3


def _dev_settings(**extra: object) -> Settings:
    """Build dev settings with test JWT keys and the dev code.

    Args:
        **extra: Extra settings fields.

    Returns:
        The settings.
    """
    return Settings.model_validate({"env": "dev", "jwt_active_kid": TEST_KID,
                                    "jwt_keys_json": SecretStr(TEST_KEYS_JSON),
                                    "dev_otp_code": SecretStr(DEV_CODE), **extra})


@pytest.mark.parametrize(("env", "extra"), [("test", {}), ("production", PRODUCTION)])
def test_dev_otp_code_refused_outside_dev(env: str, extra: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="DEV_OTP_CODE") as caught:
        Settings.model_validate({"env": env, "dev_otp_code": SecretStr(DEV_CODE), **extra})
    assert DEV_CODE not in str(caught.value)


def test_dev_otp_code_refused_from_env_outside_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEV_OTP_CODE", DEV_CODE)
    for env in ("test", "staging"):
        monkeypatch.setenv("ENV", env)
        with pytest.raises(ValidationError) as caught:
            load_settings()
        assert DEV_CODE not in str(caught.value)


@pytest.mark.parametrize("bad", ["12345", "1234567", "12345a", " 482915", "٤٨٢٩١٥"])
def test_dev_otp_code_must_be_six_ascii_digits(bad: str) -> None:
    with pytest.raises(ValidationError, match="6 digits") as caught:
        Settings(env="dev", dev_otp_code=SecretStr(bad))
    assert bad not in str(caught.value)


def test_dev_otp_code_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEV_OTP_CODE", DEV_CODE)
    loaded = load_settings().dev_otp_code
    assert loaded is not None and loaded.get_secret_value() == DEV_CODE
    assert DEV_CODE not in repr(load_settings())
    monkeypatch.setenv("DEV_OTP_CODE", "")
    assert load_settings().dev_otp_code is None


def test_dev_verifier_approves_only_its_code() -> None:
    verifier = dev_verifier.DevCodeVerifier(SecretStr(DEV_CODE))
    verifier.send(PHONE_NEW)
    assert verifier.check(PHONE_NEW, DEV_CODE) is True
    assert verifier.check(PHONE_NEW, WRONG_CODE) is False
    assert verifier.check(PHONE_NEW, DEV_CODE + "0") is False
    assert verifier.check(PHONE_NEW, "") is False
    assert DEV_CODE not in repr(verifier)


def test_phone_verifier_selection() -> None:
    with capture_logs() as logs:
        chosen = dev_verifier.phone_verifier_from_settings(_dev_settings())
        preferred = dev_verifier.phone_verifier_from_settings(_dev_settings(**TWILIO))
    assert isinstance(chosen, dev_verifier.DevCodeVerifier)
    assert isinstance(preferred, twilio_verify.TwilioVerifier)
    assert [entry["event"] for entry in logs] == ["verify.dev_code_enabled", "verify.dev_code_ignored"]
    assert DEV_CODE not in repr(logs)
    assert dev_verifier.phone_verifier_from_settings(Settings(env="dev")) is None
    twilio_only = Settings.model_validate({"env": "dev", **TWILIO})
    assert isinstance(dev_verifier.phone_verifier_from_settings(twilio_only), twilio_verify.TwilioVerifier)
    assert isinstance(configured.Integrations.from_settings(_dev_settings()).verifier, dev_verifier.DevCodeVerifier)


def test_dev_verifier_never_built_outside_dev() -> None:
    """Defense in depth: even settings that skipped validation never get the dev verifier outside dev."""
    unchecked = Settings.model_construct(env="test", dev_otp_code=SecretStr(DEV_CODE))
    assert dev_verifier.phone_verifier_from_settings(unchecked) is None


def test_dev_code_signup_end_to_end(mongo_client: MongoClientT, clock: FakeClock) -> None:
    app = create_app(_dev_settings(), mongo_client, clock=clock)
    with TestClient(app) as client:
        assert client.post("/v1/auth/otp/start", json={"phone": PHONE_NEW}).status_code == 202
        wrong = client.post("/v1/auth/otp/verify", json={"phone": PHONE_NEW, "code": WRONG_CODE, **SIGNUP})
        assert wrong.status_code == 400 and wrong.json()["error"]["code"] == "invalid_code"
        details = client.post("/v1/auth/otp/verify", json={"phone": PHONE_NEW, "code": DEV_CODE})
        assert details.status_code == 422
        ticket = details.json()["error"]["details"]["signup_ticket"]
        signed = client.post("/v1/auth/otp/verify", json={"phone": PHONE_NEW, "signup_ticket": ticket, **SIGNUP})
        assert signed.status_code == 200, signed.text
        body = signed.json()
        assert body["state"] == "provisioning" and body["role"] == "owner"
        assert client.get(f"/v1/signup/status/{body['signup_token']}").json()["status"] == "pending"
        assert client.get("/v1/me", headers=bearer(body["access_token"])).status_code == 200
    assert platform(mongo_client)["signups"].count_documents({"phone": PHONE_NEW}) == 1


def test_dev_code_keeps_send_limits(mongo_client: MongoClientT, clock: FakeClock) -> None:
    app = create_app(_dev_settings(), mongo_client, clock=clock)
    with TestClient(app) as client:
        for _ in range(SEND_PER_PHONE):
            assert client.post("/v1/auth/otp/start", json={"phone": PHONE_NEW}).status_code == 202
        assert client.post("/v1/auth/otp/start", json={"phone": PHONE_NEW}).status_code == 429
