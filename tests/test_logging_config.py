import io
import json
import logging

import structlog

from backend.logging_config import configure_logging


def test_structlog_json_logging_includes_request_context():
    stream = io.StringIO()
    configure_logging(stream=stream, force=True)
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id="req-123", path="/api/health")

    logging.getLogger("backend.test").info("hello world")

    log_line = stream.getvalue().strip()
    assert log_line
    payload = json.loads(log_line)
    assert payload["event"] == "hello world"
    assert payload["request_id"] == "req-123"
    assert payload["path"] == "/api/health"
    assert payload["logger"] == "backend.test"
    assert payload["level"] == "info"

    structlog.contextvars.clear_contextvars()


def test_structlog_redacts_sensitive_values():
    stream = io.StringIO()
    configure_logging(stream=stream, force=True)

    structlog.get_logger("backend.test").info(
        "authorization failure",
        api_key="secret-key",
        authorization="Bearer secret-token",
        nested={"refresh_token": "refresh-secret"},
    )

    payload = json.loads(stream.getvalue().strip())
    assert payload["api_key"] == "[REDACTED]"
    assert payload["authorization"] == "[REDACTED]"
    assert payload["nested"]["refresh_token"] == "[REDACTED]"


def test_stdlib_logging_redacts_bearer_tokens():
    stream = io.StringIO()
    configure_logging(stream=stream, force=True)

    logging.getLogger("backend.test").error(
        "Authorization header Bearer secret-token api_key=abc123"
    )

    payload = json.loads(stream.getvalue().strip())
    assert payload["event"] == "Authorization header [REDACTED] api_key=[REDACTED]"
