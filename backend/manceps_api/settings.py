"""Typed configuration from environment variables. Secrets are SecretStr; dotenv files are never read."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_ACCESS_TOKEN_MINUTES = 15
DEFAULT_REFRESH_TOKEN_DAYS = 30
DEFAULT_SCOPED_TOKEN_MINUTES = 60
DEFAULT_SMTP_PORT = 587
DEFAULT_IMPORT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_IMPORT_MAX_ROWS = 20_000
DEFAULT_IMPORT_UNDO_HOURS = 24
DEFAULT_API_PORT = 8000
DEFAULT_TRUSTED_PROXY_HOPS = 1
MAX_TRUSTED_PROXY_HOPS = 10
DEFAULT_MAX_BODY_BYTES = 1024 * 1024
DEFAULT_EVENTS_POLL_SECONDS = 1.0
DEFAULT_SSE_KEEPALIVE_SECONDS = 15.0
DEFAULT_SSE_IDLE_STOP_SECONDS = 30.0
DEFAULT_SSE_MAX_STREAM_SECONDS = 300.0
DEFAULT_SSE_MAX_CONNECTIONS_PER_USER = 5
DEFAULT_SSE_QUEUE_SIZE = 100
MAX_TCP_PORT = 65_535
WILDCARD_ORIGIN = "*"
DEV_OTP_CODE_FORMAT = re.compile(r"[0-9]{6}")
DEV_ENV = "dev"

SECRET_FIELDS: frozenset[str] = frozenset({
    "mongodb_uri", "jwt_keys_json", "twilio_auth_token", "smtp_password", "fmcsa_webkey", "eia_api_key",
    "google_maps_api_key", "ors_api_key", "secrets_key", "dev_otp_code",
})
PRODUCTION_REQUIRED: tuple[str, ...] = (
    "mongodb_uri", "jwt_active_kid", "jwt_keys_json", "secrets_key", "public_base_url",
)

Env = Literal["dev", "test", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class Settings(BaseSettings):
    """All runtime configuration. Field names map case-insensitively to environment variables (ENV, MONGODB_URI...)."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False, frozen=True,
                                      hide_input_in_errors=True)

    env: Env = "dev"
    mongodb_uri: SecretStr | None = None
    platform_db: str = Field(default="platform", min_length=1)
    jwt_active_kid: str | None = None
    jwt_keys_json: SecretStr | None = None
    access_token_minutes: int = Field(default=DEFAULT_ACCESS_TOKEN_MINUTES, gt=0)
    refresh_token_days: int = Field(default=DEFAULT_REFRESH_TOKEN_DAYS, gt=0)
    scoped_token_minutes: int = Field(default=DEFAULT_SCOPED_TOKEN_MINUTES, gt=0)
    public_base_url: str | None = None
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list[str])
    cookie_domain: str | None = None
    trust_proxy: bool = False
    trusted_proxy_hops: int = Field(default=DEFAULT_TRUSTED_PROXY_HOPS, ge=1, le=MAX_TRUSTED_PROXY_HOPS)
    max_body_bytes: int = Field(default=DEFAULT_MAX_BODY_BYTES, gt=0)
    twilio_account_sid: str | None = None
    twilio_auth_token: SecretStr | None = None
    twilio_verify_service_sid: str | None = None
    dev_otp_code: SecretStr | None = None
    email_login_enabled: bool = False
    smtp_host: str | None = None
    smtp_port: int = Field(default=DEFAULT_SMTP_PORT, gt=0, le=MAX_TCP_PORT)
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    mail_from: str | None = None
    fmcsa_webkey: SecretStr | None = None
    eia_api_key: SecretStr | None = None
    google_maps_api_key: SecretStr | None = None
    ors_api_key: SecretStr | None = None
    freight_contact_email: str | None = None
    secrets_key: SecretStr | None = None
    import_max_bytes: int = Field(default=DEFAULT_IMPORT_MAX_BYTES, gt=0)
    import_max_rows: int = Field(default=DEFAULT_IMPORT_MAX_ROWS, gt=0)
    import_undo_hours: int = Field(default=DEFAULT_IMPORT_UNDO_HOURS, gt=0)
    export_dir: str | None = None
    events_poll_seconds: float = Field(default=DEFAULT_EVENTS_POLL_SECONDS, gt=0)
    sse_keepalive_seconds: float = Field(default=DEFAULT_SSE_KEEPALIVE_SECONDS, gt=0)
    sse_idle_stop_seconds: float = Field(default=DEFAULT_SSE_IDLE_STOP_SECONDS, ge=0)
    sse_max_stream_seconds: float = Field(default=DEFAULT_SSE_MAX_STREAM_SECONDS, gt=0)
    sse_max_connections_per_user: int = Field(default=DEFAULT_SSE_MAX_CONNECTIONS_PER_USER, gt=0)
    sse_queue_size: int = Field(default=DEFAULT_SSE_QUEUE_SIZE, gt=0)
    log_level: LogLevel = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=DEFAULT_API_PORT, gt=0, le=MAX_TCP_PORT)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Parse a comma-separated CORS_ORIGINS value.

        Args:
            value: Raw value from the environment or constructor.

        Returns:
            A list of trimmed, non-empty origins, or the value unchanged if already a list.
        """
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("dev_otp_code", mode="before")
    @classmethod
    def _dev_otp_code_format(cls, value: object) -> object:
        """Treat an empty DEV_OTP_CODE as unset and require exactly six ASCII digits otherwise.

        Args:
            value: Raw value from the environment or constructor.

        Returns:
            None for an empty value, else the value unchanged.

        Raises:
            ValueError: If the code is not exactly six ASCII digits (the message never contains the code).
        """
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if raw is None or raw == "":
            return None
        if not isinstance(raw, str) or DEV_OTP_CODE_FORMAT.fullmatch(raw) is None:
            raise ValueError("DEV_OTP_CODE must be exactly 6 digits")
        return value

    @model_validator(mode="after")
    def _dev_otp_code_only_in_dev(self) -> Settings:
        """Refuse the fixed dev sign-in code in every environment except dev (fail closed).

        Returns:
            The validated settings.

        Raises:
            ValueError: If DEV_OTP_CODE is set and ENV is not dev.
        """
        if self.dev_otp_code is not None and self.env != DEV_ENV:
            raise ValueError(f"DEV_OTP_CODE is only allowed when ENV={DEV_ENV}")
        return self

    @model_validator(mode="after")
    def _production_fails_closed(self) -> Settings:
        """Refuse to run production without core secrets or with a wildcard CORS origin.

        Returns:
            The validated settings.

        Raises:
            ValueError: If a required production value is missing or CORS is a wildcard.
        """
        if self.env != "production":
            return self
        missing = [name for name in PRODUCTION_REQUIRED if getattr(self, name) is None]
        if missing:
            raise ValueError(f"production requires: {', '.join(missing)}")
        if WILDCARD_ORIGIN in self.cors_origins:
            raise ValueError("CORS origin '*' is not allowed in production")
        return self


def load_settings() -> Settings:
    """Read settings from the process environment.

    Returns:
        The validated settings.

    Raises:
        pydantic.ValidationError: If a value is invalid or production requirements are not met.
    """
    return Settings()
