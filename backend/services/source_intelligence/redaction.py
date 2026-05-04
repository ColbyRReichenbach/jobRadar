from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


_SENSITIVE_KEY_PARTS = (
    "accesskey",
    "accesstoken",
    "apikey",
    "api-key",
    "api_key",
    "applicationid",
    "auth",
    "authorization",
    "bearer",
    "candidate",
    "clientsecret",
    "cookie",
    "credential",
    "headers",
    "invite",
    "jwt",
    "magic",
    "password",
    "profileid",
    "query",
    "rawurl",
    "raw_url",
    "refreshtoken",
    "secret",
    "session",
    "subject",
    "token",
    "url",
)

_PRIVATE_VALUE_PATTERN = re.compile(
    r"(token|api[_-]?key|authorization|bearer|candidateId|applicationId|session|jwt|magic|invite)=([^&\s]+)",
    re.IGNORECASE,
)
_SAFE_PROVIDER_METADATA_KEYS = {
    "account",
    "board",
    "board_token",
    "company_identifier",
    "host",
    "locale",
    "provider_key",
    "server",
    "shortcode",
    "site",
    "tenant",
}


def sanitize_log_text(value: Any, *, max_length: int = 240) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    text = _PRIVATE_VALUE_PATTERN.sub(r"\1=[REDACTED]", text)
    return text[:max_length]


def redact_source_config(config: Mapping[str, Any] | None) -> dict:
    """Return shared/admin-safe source_config metadata.

    Source configs are allowed to retain provider identifiers such as board token
    or tenant, but credentials, headers, raw URLs, query strings, and nested
    sensitive structures are dropped rather than masked so they cannot leak into
    admin APIs, logs, or shared source rows.
    """

    return _redact_mapping(config or {}, max_length=240, keep_urls=False)


def redact_audit_evidence(evidence: Mapping[str, Any] | None) -> dict:
    """Return audit evidence safe for admin views and persisted audit rows."""

    return _redact_mapping(evidence or {}, max_length=240, keep_urls=False)


def _redact_mapping(values: Mapping[str, Any], *, max_length: int, keep_urls: bool) -> dict:
    clean: dict[str, Any] = {}
    for key, value in values.items():
        if _is_sensitive_key(str(key), keep_urls=keep_urls):
            continue
        redacted_value = _redact_value(value, max_length=max_length, keep_urls=keep_urls)
        if redacted_value is not _Drop:
            clean[str(key)] = redacted_value
    return clean


def _redact_value(value: Any, *, max_length: int, keep_urls: bool) -> Any:
    if isinstance(value, Mapping):
        return _redact_mapping(value, max_length=max_length, keep_urls=keep_urls)
    if isinstance(value, list):
        result = []
        for item in value:
            redacted = _redact_value(item, max_length=max_length, keep_urls=keep_urls)
            if redacted is not _Drop:
                result.append(redacted)
        return result
    if isinstance(value, tuple):
        result = []
        for item in value:
            redacted = _redact_value(item, max_length=max_length, keep_urls=keep_urls)
            if redacted is not _Drop:
                result.append(redacted)
        return result
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    text = sanitize_log_text(value, max_length=max_length)
    if not keep_urls and _looks_like_url(text):
        return _Drop
    return text


def _is_sensitive_key(key: str, *, keep_urls: bool) -> bool:
    lowered = key.lower()
    if lowered in _SAFE_PROVIDER_METADATA_KEYS:
        return False
    normalized = re.sub(r"[^a-z0-9]", "", lowered)
    for part in _SENSITIVE_KEY_PARTS:
        if part == "url" and keep_urls:
            continue
        part_normalized = re.sub(r"[^a-z0-9]", "", part.lower())
        if part in lowered or part_normalized in normalized:
            return True
    return False


def _looks_like_url(value: str) -> bool:
    lowered = value.lower()
    return "://" in lowered or lowered.startswith("www.")


class _DropType:
    pass


_Drop = _DropType()
