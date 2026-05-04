import os

import pytest


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_POSTGRES_DATABASE_URL"),
    reason="Postgres migration test requires TEST_POSTGRES_DATABASE_URL.",
)


def test_source_intelligence_postgres_migration_indexes(monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    database_url = os.environ["TEST_POSTGRES_DATABASE_URL"]
    monkeypatch.setenv("DATABASE_URL", database_url)
    sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", sync_url)

    command.upgrade(config, "049_add_source_intelligence")
    engine = create_engine(sync_url)
    try:
        with engine.begin() as conn:
            indexes = conn.execute(
                text(
                    """
                    select indexname, indexdef
                    from pg_indexes
                    where tablename = 'company_job_sources'
                    """
                )
            ).all()
            index_defs = "\n".join(row.indexdef for row in indexes)
            assert "coalesce" in index_defs.lower() or "company_domain_key" in index_defs.lower()
    finally:
        engine.dispose()
