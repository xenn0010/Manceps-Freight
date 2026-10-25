"""Settings: secrets are SecretStr, production fails closed, list parsing."""

from __future__ import annotations

import re
import types
from typing import Union, get_args, get_origin

import pytest
from pydantic import SecretStr, ValidationError

from manceps_api.settings import SECRET_FIELDS, Settings, load_settings

SECRET_NAME = re.compile(r"(password|secret|auth_token|api_key|webkey|keys_json|mongodb_uri)")
SECRET_VALUES = {
    "MONGODB_URI": "mongodb+srv://user:pw-in-uri@cluster.test/",
    "JWT_KEYS_JSON": '{"k1": {"public_pem": "pub", "private_pem": "very-private"}}',
    "TWILIO_AUTH_TOKEN": "twilio-auth-value",
    "SMTP_PASSWORD": "smtp-pass-value",
    "FMCSA_WEBKEY": "fmcsa-key-value",
    "EIA_API_KEY": "eia-key-value",
    "GOOGLE_MAPS_API_KEY": "gmaps-key-value",
    "ORS_API_KEY": "ors-key-value",
    "SECRETS_KEY": "secrets-key-value",
    "DEV_OTP_CODE": "482915",
}
PRODUCTION_REQUIRED = {
    "ENV": "production",
    "MONGODB_URI": "mongodb://db.test/",
    "JWT_ACTIVE_KID": "k1",
    "JWT_KEYS_JSON": '{"k1": {"public_pem": "pub"}}',
    "SECRETS_KEY": "c2VjcmV0",
    "PUBLIC_BASE_URL": "https://app.manceps.test",
}


def _is_optional_secret(annotation: object) -> bool:
    """Check an annotation is exactly SecretStr or SecretStr | None.

    Args:
        annotation: Field annotation.

    Returns:
        True for a SecretStr annotation.
    """
    if annotation is SecretStr:
        return True
    if get_origin(annotation) in (Union, types.UnionType):
        return set(get_args(annotation)) == {SecretStr, type(None)}
    return False


def test_settings_secrets_are_secretstr(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every secret-looking field is SecretStr and never shows up in repr or dumps."""
    names = set(Settings.model_fields)
    looks_secret = {name for name in names if SECRET_NAME.search(name)}
    assert looks_secret <= SECRET_FIELDS
    assert {name.upper() for name in SECRET_FIELDS} == set(SECRET_VALUES)
    for name in SECRET_FIELDS:
        assert _is_optional_secret(Settings.model_fields[name].annotation), name
    for key, value in SECRET_VALUES.items():
        monkeypatch.setenv(key, value)
    settings = load_settings()
    rendered = repr(settings) + str(settings) + settings.model_dump_json()
    for value in SECRET_VALUES.values():
        assert value not in rendered
    assert settings.twilio_auth_token is not None
    assert settings.twilio_auth_token.get_secret_value() == "twilio-auth-value"


def test_settings_defaults() -> None:
    """Defaults match the documented environment table."""
    settings = Settings()
    assert settings.env == "dev"
    assert settings.platform_db == "platform"
    assert (settings.access_token_minutes, settings.refresh_token_days, settings.scoped_token_minutes) == (15, 30, 60)
    assert (settings.import_max_bytes, settings.import_max_rows, settings.import_undo_hours) == (10485760, 20000, 24)
    assert settings.trust_proxy is False
    assert settings.email_login_enabled is False
    assert settings.log_level == "INFO"
    assert settings.cors_origins == []


def test_cors_origins_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    """CORS_ORIGINS is a comma-separated list."""
    monkeypatch.setenv("CORS_ORIGINS", "https://app.manceps.test, https://admin.manceps.test,")
    assert load_settings().cors_origins == ["https://app.manceps.test", "https://admin.manceps.test"]


def test_production_requires_core_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Production refuses to start without the database, signing keys and secrets key."""
    for key, value in PRODUCTION_REQUIRED.items():
        monkeypatch.setenv(key, value)
    assert load_settings().env == "production"
    monkeypatch.delenv("JWT_KEYS_JSON")
    with pytest.raises(ValidationError, match="jwt_keys_json"):
        load_settings()


def test_production_rejects_wildcard_cors(monkeypatch: pytest.MonkeyPatch) -> None:
    """A wildcard origin is never allowed in production (refresh cookies are credentialed)."""
    for key, value in PRODUCTION_REQUIRED.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(ValidationError, match="CORS"):
        load_settings()


def test_positive_limits_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    """Numeric limits must be positive."""
    monkeypatch.setenv("IMPORT_MAX_ROWS", "0")
    with pytest.raises(ValidationError):
        load_settings()


def test_settings_never_read_env_files() -> None:
    """Settings never load a dotenv file, so local secret files cannot leak into tests or logs."""
    assert Settings.model_config.get("env_file") is None
