import logging
import re
import sys
from typing import TextIO

import structlog


_LOGGING_CONFIGURED = False
_REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "password",
    "secret",
    "token",
    "auth",
    "session",
    "jwt",
    "candidate",
    "candidateid",
    "applicationid",
    "profileid",
    "magic",
    "invite",
    "interview",
    "access_token",
    "refresh_token",
    "api_key",
    "x-api-key",
    "x-smarttoken",
}
_SENSITIVE_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"(api[_-]?key=)([^&\s]+)", re.IGNORECASE),
    re.compile(r"(token=)([^&\s]+)", re.IGNORECASE),
    re.compile(r"((?:auth|session|jwt|candidate|candidateId|applicationId|profileId|magic|invite|interview)=)([^&\s]+)", re.IGNORECASE),
    re.compile(r"(https?://[^\s\"']*(?:calendly|schedule|interview)[^\s\"']*)", re.IGNORECASE),
]


def _redact_string(value: str) -> str:
    redacted = value.replace("\r", " ").replace("\n", " ")
    for pattern in _SENSITIVE_PATTERNS:
        redacted = pattern.sub(lambda match: match.group(1) + _REDACTED if match.lastindex and match.lastindex > 1 else _REDACTED, redacted)
    return redacted


def _sanitize_value(value):
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            if key.lower() in _SENSITIVE_KEYS:
                sanitized[key] = _REDACTED
            else:
                sanitized[key] = _sanitize_value(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_value(item) for item in value)
    if isinstance(value, str):
        return _redact_string(value)
    return value


def redact_sensitive_data(_, __, event_dict):
    return _sanitize_value(event_dict)


def configure_logging(
    level: int = logging.INFO,
    stream: TextIO | None = None,
    force: bool = False,
) -> None:
    global _LOGGING_CONFIGURED

    if _LOGGING_CONFIGURED and not force:
        return

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        redact_sensitive_data,
    ]

    structlog.reset_defaults()
    structlog.configure(
        processors=shared_processors
        + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared_processors,
    )
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    _LOGGING_CONFIGURED = True
