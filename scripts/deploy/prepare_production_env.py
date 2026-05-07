#!/usr/bin/env python3
"""Create a local, ignored production env bundle for provider setup.

The script intentionally prints only key names and status, never secret values.
"""

from __future__ import annotations

import base64
import os
import secrets
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services.production_readiness import PRODUCTION_AI_CAP_DEFAULTS  # noqa: E402

SOURCE_FILES = [
    ROOT / ".env",
    ROOT / ".deploy.secrets.local",
]
OUTPUT_FILE = ROOT / ".deploy.generated.env"


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def merge_sources() -> dict[str, str]:
    merged: dict[str, str] = {}
    for source_file in SOURCE_FILES:
        for key, value in read_env_file(source_file).items():
            if value:
                merged[key] = value
    return merged


def normalize_database_url(raw_url: str) -> str:
    url = raw_url.strip()
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    return url


def random_fernet_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


def existing_generated_values() -> dict[str, str]:
    return read_env_file(OUTPUT_FILE)


def first_present(values: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = values.get(key, "").strip()
        if value:
            return value
    return ""


def main() -> int:
    source = merge_sources()
    deploy_source = {
        key: value
        for key, value in read_env_file(ROOT / ".deploy.secrets.local").items()
        if value
    }
    existing = existing_generated_values()

    api_url = first_present(deploy_source, "API_URL")
    google_redirect_uri = first_present(deploy_source, "GOOGLE_REDIRECT_URI")
    if not google_redirect_uri and api_url:
        google_redirect_uri = api_url.rstrip("/") + "/api/auth/google/callback"
    dashboard_url = first_present(deploy_source, "DASHBOARD_URL")

    database_url = first_present(source, "NEON_DATABASE_URL", "DATABASE_URL")
    output = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": normalize_database_url(database_url),
        "REDIS_URL": first_present(source, "REDIS_URL"),
        "JWT_SECRET": first_present(source, "JWT_SECRET")
        or existing.get("JWT_SECRET", "")
        or secrets.token_urlsafe(48),
        "APPTRAIL_GMAIL_TOKEN_ENCRYPTION_KEY": first_present(
            source, "APPTRAIL_GMAIL_TOKEN_ENCRYPTION_KEY"
        )
        or existing.get("APPTRAIL_GMAIL_TOKEN_ENCRYPTION_KEY", "")
        or random_fernet_key(),
        "METRICS_BEARER_TOKEN": first_present(source, "METRICS_BEARER_TOKEN")
        or existing.get("METRICS_BEARER_TOKEN", "")
        or secrets.token_urlsafe(32),
        "DASHBOARD_URL": dashboard_url,
        "API_URL": api_url,
        "GOOGLE_REDIRECT_URI": google_redirect_uri,
        "GMAIL_CLIENT_ID": first_present(source, "GMAIL_CLIENT_ID"),
        "GMAIL_CLIENT_SECRET": first_present(source, "GMAIL_CLIENT_SECRET"),
        "GMAIL_CLASSIFIER_MODE": first_present(source, "GMAIL_CLASSIFIER_MODE") or "hybrid",
        "OPENAI_API_KEY": first_present(source, "OPENAI_API_KEY"),
        "HUNTER_API_KEY": first_present(source, "HUNTER_API_KEY"),
        "SERPAPI_KEY": first_present(source, "SERPAPI_KEY"),
        "SENTRY_DSN": first_present(source, "SENTRY_DSN"),
        "SENTRY_ENVIRONMENT": "production",
        "READINESS_REQUIRE_CELERY": "true",
        "RADAR_ENABLED": first_present(source, "RADAR_ENABLED") or "true",
        "RADAR_RESEARCH_ENABLED": first_present(source, "RADAR_RESEARCH_ENABLED") or "false",
        "RADAR_ALERT_MAX_PER_USER_PER_DAY": first_present(
            source, "RADAR_ALERT_MAX_PER_USER_PER_DAY"
        )
        or "5",
        "COPILOT_ENABLED": first_present(source, "COPILOT_ENABLED") or "false",
        "COPILOT_DAILY_COST_CAP_CENTS_PER_USER": first_present(
            source, "COPILOT_DAILY_COST_CAP_CENTS_PER_USER"
        )
        or "50",
        "COPILOT_GLOBAL_DAILY_COST_CAP_CENTS": first_present(
            source, "COPILOT_GLOBAL_DAILY_COST_CAP_CENTS"
        )
        or "5000",
        "COPILOT_MAX_REQUESTS_PER_MINUTE": first_present(
            source, "COPILOT_MAX_REQUESTS_PER_MINUTE"
        )
        or "10",
        "COPILOT_MAX_CONTEXT_DOCS": first_present(source, "COPILOT_MAX_CONTEXT_DOCS") or "8",
        "COPILOT_MAX_CONTEXT_TOKENS": first_present(source, "COPILOT_MAX_CONTEXT_TOKENS")
        or "12000",
        "COPILOT_MAX_MESSAGE_CHARS": first_present(source, "COPILOT_MAX_MESSAGE_CHARS")
        or "4000",
        "COPILOT_MAX_CONVERSATION_MESSAGES": first_present(
            source, "COPILOT_MAX_CONVERSATION_MESSAGES"
        )
        or "40",
        "COPILOT_SHADOW_TEST_RATE": first_present(source, "COPILOT_SHADOW_TEST_RATE") or "0.10",
        "COPILOT_EXPERIMENTS_ENABLED": first_present(
            source, "COPILOT_EXPERIMENTS_ENABLED"
        )
        or "false",
        "SEARCH_BACKEND": first_present(source, "SEARCH_BACKEND") or "postgres",
        "OPENSEARCH_URL": first_present(source, "OPENSEARCH_URL"),
        "SEARCH_OPENSEARCH_FALLBACK_TO_POSTGRES": first_present(
            source, "SEARCH_OPENSEARCH_FALLBACK_TO_POSTGRES"
        )
        or "true",
        "AI_TRACE_FULL_PAYLOADS_ENABLED": first_present(
            source, "AI_TRACE_FULL_PAYLOADS_ENABLED"
        )
        or "false",
        "AI_FULL_TRACE_EXPORT_ENABLED": first_present(source, "AI_FULL_TRACE_EXPORT_ENABLED")
        or "false",
        "AI_TRACE_RETENTION_DAYS": first_present(source, "AI_TRACE_RETENTION_DAYS") or "30",
        "AI_PROMOTION_REPORT_MIN_CALLS": first_present(
            source, "AI_PROMOTION_REPORT_MIN_CALLS"
        )
        or "1000",
        "AI_PROMOTION_REPORT_MIN_FEEDBACK": first_present(
            source, "AI_PROMOTION_REPORT_MIN_FEEDBACK"
        )
        or "50",
        "AI_MODEL_PRICING_CONFIG": first_present(source, "AI_MODEL_PRICING_CONFIG"),
        "AI_MAX_INPUT_TOKENS_PER_REQUEST": first_present(
            source, "AI_MAX_INPUT_TOKENS_PER_REQUEST"
        )
        or PRODUCTION_AI_CAP_DEFAULTS["AI_MAX_INPUT_TOKENS_PER_REQUEST"],
        "AI_DAILY_TOKEN_CAP_PER_USER": first_present(source, "AI_DAILY_TOKEN_CAP_PER_USER")
        or PRODUCTION_AI_CAP_DEFAULTS["AI_DAILY_TOKEN_CAP_PER_USER"],
        "AI_GLOBAL_DAILY_TOKEN_CAP": first_present(source, "AI_GLOBAL_DAILY_TOKEN_CAP")
        or PRODUCTION_AI_CAP_DEFAULTS["AI_GLOBAL_DAILY_TOKEN_CAP"],
        "AI_TASK_DAILY_TOKEN_CAP": first_present(source, "AI_TASK_DAILY_TOKEN_CAP")
        or PRODUCTION_AI_CAP_DEFAULTS["AI_TASK_DAILY_TOKEN_CAP"],
        "AI_RATE_LIMIT_PER_MINUTE_PER_USER": first_present(
            source, "AI_RATE_LIMIT_PER_MINUTE_PER_USER"
        )
        or PRODUCTION_AI_CAP_DEFAULTS["AI_RATE_LIMIT_PER_MINUTE_PER_USER"],
        "AI_RATE_LIMIT_PER_MINUTE_PER_TASK": first_present(
            source, "AI_RATE_LIMIT_PER_MINUTE_PER_TASK"
        )
        or PRODUCTION_AI_CAP_DEFAULTS["AI_RATE_LIMIT_PER_MINUTE_PER_TASK"],
        "AI_RATE_LIMIT_PER_MINUTE_GLOBAL": first_present(
            source, "AI_RATE_LIMIT_PER_MINUTE_GLOBAL"
        )
        or PRODUCTION_AI_CAP_DEFAULTS["AI_RATE_LIMIT_PER_MINUTE_GLOBAL"],
        "AI_QUARANTINE_PROMPT_RISK_THRESHOLD": first_present(
            source, "AI_QUARANTINE_PROMPT_RISK_THRESHOLD"
        )
        or PRODUCTION_AI_CAP_DEFAULTS["AI_QUARANTINE_PROMPT_RISK_THRESHOLD"],
        "AI_ADMIN_ALERTS_ENABLED": first_present(source, "AI_ADMIN_ALERTS_ENABLED")
        or PRODUCTION_AI_CAP_DEFAULTS["AI_ADMIN_ALERTS_ENABLED"],
        "AI_SEMANTIC_PROMPT_GUARD_ENABLED": first_present(
            source, "AI_SEMANTIC_PROMPT_GUARD_ENABLED"
        )
        or "false",
        "POSTGRES_BACKUPS_ENABLED": first_present(source, "POSTGRES_BACKUPS_ENABLED")
        or "false",
        "POSTGRES_BACKUP_PROVIDER": first_present(source, "POSTGRES_BACKUP_PROVIDER"),
    }

    missing_required = [
        key
        for key in (
            "DATABASE_URL",
            "OPENAI_API_KEY",
            "GMAIL_CLIENT_ID",
            "GMAIL_CLIENT_SECRET",
        )
        if not output[key]
    ]

    lines = [
        "# Generated by scripts/deploy/prepare_production_env.py",
        "# Local provider setup only. Do not commit this file.",
        "",
    ]
    lines.extend(f"{key}={value}" for key, value in output.items())
    OUTPUT_FILE.write_text("\n".join(lines) + "\n")
    OUTPUT_FILE.chmod(0o600)

    print(f"Wrote {OUTPUT_FILE.relative_to(ROOT)}")
    print("Generated/preserved: JWT_SECRET, APPTRAIL_GMAIL_TOKEN_ENCRYPTION_KEY, METRICS_BEARER_TOKEN")
    print("Configured keys:", ", ".join(key for key, value in output.items() if value))
    if missing_required:
        print("Missing required keys:", ", ".join(missing_required))
        return 1
    if not output["REDIS_URL"]:
        print("Pending: REDIS_URL should be filled after Redis is provisioned.")
    if not output["DASHBOARD_URL"] or not output["API_URL"]:
        print("Pending: DASHBOARD_URL/API_URL should be filled after provider domains exist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
