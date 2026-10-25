"""Run the API with uvicorn. The built-in access log is disabled: it prints raw query strings (SSE access tokens);
RequestContextMiddleware writes a redacted access line instead."""

from __future__ import annotations

import uvicorn

from .settings import load_settings

APP_FACTORY = "manceps_api.app:create_app_from_env"


def main() -> None:
    """Start the server on API_HOST:API_PORT.

    Raises:
        pydantic.ValidationError: If settings are invalid.
    """
    settings = load_settings()
    uvicorn.run(
        APP_FACTORY, factory=True, host=settings.api_host, port=settings.api_port, access_log=False,
        proxy_headers=settings.trust_proxy, log_config=None,
    )


if __name__ == "__main__":
    main()
