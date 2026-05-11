from datetime import datetime, timezone

import pytest

from backend.services.runtime_count_artifacts import collect_runtime_table_counts, database_source_label


def test_database_source_label_redacts_credentials():
    label = database_source_label("postgresql://user:secret@example.neon.tech/apptrail?sslmode=require")

    assert label == "postgresql://example.neon.tech/apptrail"
    assert "secret" not in label
    assert "user" not in label


@pytest.mark.asyncio
async def test_collect_runtime_table_counts_distinguishes_zero_from_missing(db_session):
    artifact = await collect_runtime_table_counts(
        db_session,
        database_label="sqlite:test",
        git_sha="abc123",
        queried_at=datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc),
        tables=["users", "action_candidates", "definitely_missing_table"],
    )

    assert artifact["database_source"] == "sqlite:test"
    assert artifact["git_sha"] == "abc123"
    assert artifact["queried_at"] == "2026-05-11T12:00:00+00:00"
    assert artifact["table_counts"]["users"] == 1
    assert artifact["table_counts"]["action_candidates"] == 0
    assert artifact["table_counts"]["definitely_missing_table"] is None
    assert "missing_table:definitely_missing_table" in artifact["warnings"]
    assert "missing_table:alembic_version" in artifact["warnings"]
