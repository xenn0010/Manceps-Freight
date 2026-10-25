"""structlog JSON logging with secret redaction.

Redaction runs last before rendering, over every value: sensitive keys are masked whole, and strings are scrubbed of
token query parameters (the SSE route accepts `?access_token=`) and bearer credentials.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any, TextIO

import structlog
from pydantic import SecretStr
from structlog.typing import EventDict, Processor, WrappedLogger

REDACTED = "[REDACTED]"
SENSITIVE_KEY = re.compile(
    r"pass(word)?|secret|token|authorization|api_?key|webkey|cookie|private_pem|credential|signature", re.IGNORECASE,
)
SENSITIVE_QUERY_PARAMS: frozenset[str] = frozenset({
    "access_token", "refresh_token", "id_token", "token", "api_key", "password", "secret", "mc_refresh",
})
QUERY_PARAM_IN_TEXT = re.compile(
    r"(?i)\b(" + "|".join(sorted(SENSITIVE_QUERY_PARAMS)) + r")=([^&\s\"'#]+)",
)
BEARER_IN_TEXT = re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]+")


def redact_text(text: str) -> str:
    """Scrub token query parameters and bearer credentials from free text.

    Args:
        text: Any string (URL, message, traceback).

    Returns:
        The string with secret values replaced.
    """
    text = QUERY_PARAM_IN_TEXT.sub(lambda match: f"{match.group(1)}={REDACTED}", text)
    return BEARER_IN_TEXT.sub(lambda match: f"{match.group(1)} {REDACTED}", text)


def redact_query_string(query: str) -> str:
    """Mask sensitive parameters in a raw query string, preserving order and the other values.

    Args:
        query: Query string without the leading '?'.

    Returns:
        The masked query string.
    """
    if not query:
        return query
    parts: list[str] = []
    for part in query.split("&"):
        name, sep, _value = part.partition("=")
        parts.append(f"{name}={REDACTED}" if sep and name.lower() in SENSITIVE_QUERY_PARAMS else part)
    return "&".join(parts)


def _redact_value(value: Any) -> Any:
    """Recursively redact one value.

    Args:
        value: Any logged value.

    Returns:
        A redacted copy.
    """
    if isinstance(value, SecretStr):
        return REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return _redact_mapping(value)  # pyright: ignore[reportUnknownArgumentType]
    if isinstance(value, list | tuple):
        return [_redact_value(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
    return value


def _redact_mapping(mapping: Mapping[Any, Any]) -> dict[Any, Any]:
    """Redact a mapping: sensitive keys masked whole, other values scrubbed recursively.

    Args:
        mapping: Mapping to redact.

    Returns:
        A redacted copy.
    """
    return {
        key: REDACTED if isinstance(key, str) and SENSITIVE_KEY.search(key) else _redact_value(item)
        for key, item in mapping.items()
    }


def redact_event(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    """structlog processor that redacts the whole event.

    Args:
        _logger: Wrapped logger.
        _method: Log method name.
        event_dict: Event to redact.

    Returns:
        The redacted event.
    """
    return _redact_mapping(event_dict)


def configure_logging(level: str, stream: TextIO | None = None) -> None:
    """Configure structlog to emit redacted JSON lines.

    Args:
        level: Minimum level name (DEBUG, INFO, WARNING, ERROR).
        stream: Output stream; standard output when None.

    Raises:
        KeyError: If the level name is unknown.
    """
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
        structlog.processors.format_exc_info,
        redact_event,
        structlog.processors.JSONRenderer(),
    ]
    factory = structlog.WriteLoggerFactory(file=stream) if stream is not None else structlog.PrintLoggerFactory()
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[level.upper()]),
        logger_factory=factory,
        cache_logger_on_first_use=False,
    )
