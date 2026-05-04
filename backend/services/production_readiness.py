"""Production readiness checks for deployment gates.

These checks are intentionally environment-driven. They do not prove a provider
is healthy, but they prevent promoting a production deployment with missing
secrets, implicit AI caps, disabled Redis-backed rate limits, or no backup
posture recorded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


PRODUCTION_AI_CAP_DEFAULTS: dict[str, str] = {
    "AI_MAX_INPUT_TOKENS_PER_REQUEST": "12000",
    "AI_DAILY_TOKEN_CAP_PER_USER": "150000",
    "AI_GLOBAL_DAILY_TOKEN_CAP": "1000000",
    "AI_TASK_DAILY_TOKEN_CAP": "500000",
    "AI_RATE_LIMIT_PER_MINUTE_PER_USER": "20",
    "AI_RATE_LIMIT_PER_MINUTE_PER_TASK": "120",
    "AI_RATE_LIMIT_PER_MINUTE_GLOBAL": "300",
    "AI_QUARANTINE_PROMPT_RISK_THRESHOLD": "0.70",
    "AI_ADMIN_ALERTS_ENABLED": "true",
}

REQUIRED_PRODUCTION_KEYS = (
    "DATABASE_URL",
    "REDIS_URL",
    "JWT_SECRET",
    "APPTRAIL_GMAIL_TOKEN_ENCRYPTION_KEY",
    "OPENAI_API_KEY",
    "GMAIL_CLIENT_ID",
    "GMAIL_CLIENT_SECRET",
    "DASHBOARD_URL",
    "API_URL",
    "SOURCE_LINK_ENCRYPTION_KEY",
    "SOURCE_LINK_HASH_KEY",
)

BACKUP_EVIDENCE_KEYS = (
    "POSTGRES_BACKUPS_ENABLED",
    "POSTGRES_BACKUP_PROVIDER",
)


@dataclass(frozen=True)
class ReadinessIssue:
    key: str
    message: str
    severity: str = "error"


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_positive_int(value: str | None) -> bool:
    try:
        return int(str(value or "").strip()) > 0
    except ValueError:
        return False


def _is_probability(value: str | None, *, minimum: float = 0.0, maximum: float = 1.0) -> bool:
    try:
        number = float(str(value or "").strip())
    except ValueError:
        return False
    return minimum <= number <= maximum


def validate_production_environment(values: Mapping[str, str | None]) -> list[ReadinessIssue]:
    issues: list[ReadinessIssue] = []

    for key in REQUIRED_PRODUCTION_KEYS:
        if not (values.get(key) or "").strip():
            issues.append(ReadinessIssue(key, f"{key} must be set for production."))

    for key in (
        "AI_MAX_INPUT_TOKENS_PER_REQUEST",
        "AI_DAILY_TOKEN_CAP_PER_USER",
        "AI_GLOBAL_DAILY_TOKEN_CAP",
        "AI_TASK_DAILY_TOKEN_CAP",
        "AI_RATE_LIMIT_PER_MINUTE_PER_USER",
        "AI_RATE_LIMIT_PER_MINUTE_PER_TASK",
        "AI_RATE_LIMIT_PER_MINUTE_GLOBAL",
    ):
        if not (values.get(key) or "").strip():
            issues.append(ReadinessIssue(key, f"{key} must be explicitly configured; do not rely on code defaults."))
        elif not _is_positive_int(values.get(key)):
            issues.append(ReadinessIssue(key, f"{key} must be a positive integer for beta production."))

    if not (values.get("AI_QUARANTINE_PROMPT_RISK_THRESHOLD") or "").strip():
        issues.append(ReadinessIssue("AI_QUARANTINE_PROMPT_RISK_THRESHOLD", "AI quarantine risk threshold must be explicitly configured."))
    elif not _is_probability(values.get("AI_QUARANTINE_PROMPT_RISK_THRESHOLD"), minimum=0.5, maximum=1.0):
        issues.append(ReadinessIssue("AI_QUARANTINE_PROMPT_RISK_THRESHOLD", "AI quarantine threshold should be between 0.50 and 1.00."))

    if not _truthy(values.get("AI_ADMIN_ALERTS_ENABLED")):
        issues.append(ReadinessIssue("AI_ADMIN_ALERTS_ENABLED", "Admin AI safety alerts must be enabled for beta production."))

    if not _truthy(values.get("POSTGRES_BACKUPS_ENABLED")):
        issues.append(ReadinessIssue("POSTGRES_BACKUPS_ENABLED", "PostgreSQL automated backups must be enabled before real-user beta."))
    if not (values.get("POSTGRES_BACKUP_PROVIDER") or "").strip():
        issues.append(ReadinessIssue("POSTGRES_BACKUP_PROVIDER", "Record the backup provider or plan, for example Neon automated backups."))

    for key in (
        "JOB_SEARCH_DIRECT_SOURCES_ENABLED",
        "JOB_SEARCH_WORKDAY_ENABLED",
        "JOB_SEARCH_CUSTOM_CRAWL_ENABLED",
        "JOB_SEARCH_BROAD_PROVIDER_ENABLED",
    ):
        if not (values.get(key) or "").strip():
            issues.append(ReadinessIssue(key, f"{key} must be explicitly set for source intelligence rollout."))

    for key in (
        "JOB_SEARCH_SERPAPI_MONTHLY_CAP",
        "JOB_SEARCH_SERPAPI_USER_MONTHLY_CAP",
        "SOURCE_VERIFICATION_MAX_SOURCES_PER_RUN",
        "SOURCE_FETCH_MAX_BYTES",
        "SOURCE_FETCH_TIMEOUT_SECONDS",
    ):
        if not (values.get(key) or "").strip():
            issues.append(ReadinessIssue(key, f"{key} must be explicitly configured; do not rely on source-intelligence defaults."))
        elif not _is_positive_int(values.get(key)):
            issues.append(ReadinessIssue(key, f"{key} must be a positive integer."))

    return issues
