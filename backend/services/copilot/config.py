"""Copilot runtime configuration."""

from __future__ import annotations

import os


def copilot_enabled() -> bool:
    return os.getenv("COPILOT_ENABLED", "false").lower() == "true"


def max_context_docs() -> int:
    try:
        return max(1, min(int(os.getenv("COPILOT_MAX_CONTEXT_DOCS", "8")), 25))
    except ValueError:
        return 8


def max_context_tokens() -> int:
    try:
        return max(500, int(os.getenv("COPILOT_MAX_CONTEXT_TOKENS", "12000")))
    except ValueError:
        return 12000


def max_message_chars() -> int:
    try:
        return max(200, int(os.getenv("COPILOT_MAX_MESSAGE_CHARS", "4000")))
    except ValueError:
        return 4000


def max_conversation_messages() -> int:
    try:
        return max(2, int(os.getenv("COPILOT_MAX_CONVERSATION_MESSAGES", "40")))
    except ValueError:
        return 40


def per_user_daily_cost_cap_cents() -> int:
    try:
        return max(0, int(os.getenv("COPILOT_DAILY_COST_CAP_CENTS_PER_USER", "50")))
    except ValueError:
        return 50


def global_daily_cost_cap_cents() -> int:
    try:
        return max(0, int(os.getenv("COPILOT_GLOBAL_DAILY_COST_CAP_CENTS", "5000")))
    except ValueError:
        return 5000


def requests_per_minute() -> int:
    try:
        return max(1, int(os.getenv("COPILOT_MAX_REQUESTS_PER_MINUTE", "10")))
    except ValueError:
        return 10
