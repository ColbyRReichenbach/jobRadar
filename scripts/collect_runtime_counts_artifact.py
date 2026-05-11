#!/usr/bin/env python3
"""Generate a local runtime table-count artifact.

The output distinguishes missing tables from existing tables with zero rows.
It intentionally records a sanitized database source label, not credentials.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from backend.database_url import normalize_asyncpg_database_url
from backend.services.runtime_count_artifacts import collect_runtime_table_counts, database_source_label


DEFAULT_OUTPUT = Path("docs/interview-artifacts/generated/local-runtime-counts.json")


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT_DIR, text=True).strip()
    except Exception:
        return "unknown"


def _default_database_url() -> str:
    configured = os.getenv("DATABASE_URL")
    if configured:
        return configured
    local_db = ROOT_DIR / "apptrail-local.db"
    if local_db.exists():
        return f"sqlite+aiosqlite:///{local_db}"
    return "sqlite+aiosqlite:///:memory:"


async def _run(args: argparse.Namespace) -> dict:
    raw_database_url = args.database_url or _default_database_url()
    database_url, connect_args = normalize_asyncpg_database_url(raw_database_url)
    engine = create_async_engine(database_url, connect_args=connect_args)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        artifact = await collect_runtime_table_counts(
            session,
            database_label=args.database_label or database_source_label(raw_database_url),
            git_sha=args.git_sha or _git_sha(),
            tables=args.table or None,
        )
    await engine.dispose()
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=None, help="Database URL. Defaults to DATABASE_URL or apptrail-local.db.")
    parser.add_argument("--database-label", default=None, help="Sanitized source label to write into the artifact.")
    parser.add_argument("--git-sha", default=None, help="Git SHA override for reproducible tests.")
    parser.add_argument("--table", action="append", help="Specific table to count. Can be repeated.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    artifact = asyncio.run(_run(args))
    output = args.output
    if not output.is_absolute():
        output = ROOT_DIR / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(str(output.relative_to(ROOT_DIR) if output.is_relative_to(ROOT_DIR) else output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
