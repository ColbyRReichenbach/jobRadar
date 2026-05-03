"""Copilot input and output guardrails."""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from typing import Any

from fastapi import HTTPException

from backend.services.copilot.config import max_message_chars, requests_per_minute

_REQUEST_BUCKETS: dict[uuid.UUID, deque[float]] = defaultdict(deque)
PROMPT_ABUSE_PATTERNS = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "developer message",
    "system prompt",
    "reveal your prompt",
    "exfiltrate",
    "api key",
    "access token",
    "refresh token",
    "print every stored",
    "private identifier",
    "stored phone number",
)
UNSAFE_CONTEXT_PLACEHOLDER = "[context omitted by Copilot safety filter]"


def enforce_copilot_rate_limit(user_id: uuid.UUID) -> None:
    now = time.time()
    bucket = _REQUEST_BUCKETS[user_id]
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= requests_per_minute():
        raise HTTPException(status_code=429, detail="Too many Copilot requests")
    bucket.append(now)


def reset_rate_limit_for_tests() -> None:
    _REQUEST_BUCKETS.clear()


def validate_user_message(content: str) -> str:
    cleaned = " ".join((content or "").split())
    if not cleaned:
        raise HTTPException(status_code=422, detail="Message content is required")
    if len(cleaned) > max_message_chars():
        raise HTTPException(status_code=413, detail="Copilot message is too long")
    lowered = cleaned.lower()
    if contains_prompt_abuse(cleaned):
        raise HTTPException(status_code=422, detail="Copilot cannot process prompt-extraction or secret-seeking requests")
    return cleaned


def contains_prompt_abuse(content: str | None) -> bool:
    lowered = (content or "").lower()
    return any(pattern in lowered for pattern in PROMPT_ABUSE_PATTERNS)


def sanitize_context_snippet(snippet: str | None) -> str | None:
    if not snippet:
        return None
    if contains_prompt_abuse(snippet):
        return UNSAFE_CONTEXT_PLACEHOLDER
    return snippet


def sanitize_suggested_actions(actions: Any) -> list[dict[str, Any]]:
    if not isinstance(actions, list):
        return []
    sanitized: list[dict[str, Any]] = []
    for item in actions[:5]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        sanitized.append(
            {
                "title": title[:160],
                "description": str(item.get("description") or "").strip()[:500],
                "action_type": str(item.get("action_type") or "suggestion")[:80],
                "requires_confirmation": True,
                "read_only": True,
            }
        )
    return sanitized
