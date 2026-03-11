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
