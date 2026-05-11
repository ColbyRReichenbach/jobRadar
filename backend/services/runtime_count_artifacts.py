"""Local runtime table-count artifact helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import inspect as sa_inspect, text
from sqlalchemy.ext.asyncio import AsyncSession


DEFAULT_RUNTIME_COUNT_TABLES = [
    "users",
    "applications",
    "contacts",
    "interviews",
    "email_events",
    "email_classification_traces",
    "action_candidates",
    "alerts",
    "recommended_actions",
    "search_documents",
    "research_reports",
    "research_evidence_items",
    "research_source_items",
    "ai_model_calls",
    "ai_safety_decisions",
    "ai_artifacts",
]


def database_source_label(database_url: str | None) -> str:
    if not database_url:
        return "unset"
    parts = urlsplit(database_url)
    if parts.scheme.startswith("sqlite"):
        path = Path(parts.path)
        return f"{parts.scheme}:{path.name if path.name else ':memory:'}"
    database = parts.path.lstrip("/") or "unknown-db"
    host = parts.hostname or "unknown-host"
    return f"{parts.scheme}://{host}/{database}"


async def _table_names(db: AsyncSession) -> set[str]:
    connection = await db.connection()
    return set(await connection.run_sync(lambda sync_conn: sa_inspect(sync_conn).get_table_names()))


async def collect_runtime_table_counts(
    db: AsyncSession,
    *,
    database_label: str,
    git_sha: str,
    tables: list[str] | None = None,
    queried_at: datetime | None = None,
) -> dict[str, Any]:
    table_names = await _table_names(db)
    selected_tables = tables or DEFAULT_RUNTIME_COUNT_TABLES
    counts: dict[str, int | None] = {}
    warnings: list[str] = []
    for table_name in selected_tables:
        if table_name not in table_names:
            counts[table_name] = None
            warnings.append(f"missing_table:{table_name}")
            continue
        count = (await db.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))).scalar_one()
        counts[table_name] = int(count or 0)

    migration_version = None
    if "alembic_version" in table_names:
        migration_version = (await db.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))).scalar_one_or_none()
    else:
        warnings.append("missing_table:alembic_version")

    return {
        "artifact_type": "local_runtime_table_counts",
        "database_source": database_label,
        "git_sha": git_sha,
        "migration_version": migration_version,
        "queried_at": (queried_at or datetime.now(timezone.utc)).isoformat(),
        "table_counts": counts,
        "warnings": warnings,
        "notes": [
            "Missing tables are represented as null counts and missing_table warnings.",
            "Zero means the table exists and returned zero rows.",
            "Local counts are not production usage metrics.",
        ],
    }
