import asyncio
import os

import pytest


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_POSTGRES_DATABASE_URL"),
    reason="Postgres migration test requires TEST_POSTGRES_DATABASE_URL.",
)


def test_source_intelligence_postgres_migration_indexes(monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    database_url = os.environ["TEST_POSTGRES_DATABASE_URL"]
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "049_add_source_intelligence")

    async def _fetch_company_source_indexes() -> str:
        engine = create_async_engine(database_url)
        try:
            async with engine.begin() as conn:
                indexes = await conn.execute(
                    text(
                        """
                        select indexname, indexdef
                        from pg_indexes
                        where tablename = 'company_job_sources'
                        """
                    )
                )
                return "\n".join(row.indexdef for row in indexes)
        finally:
            await engine.dispose()

    index_defs = asyncio.run(_fetch_company_source_indexes())
    assert "coalesce" in index_defs.lower() or "company_domain_key" in index_defs.lower()
