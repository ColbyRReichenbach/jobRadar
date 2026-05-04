from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def source_intelligence_lock(db: AsyncSession, key: str) -> AsyncIterator[bool]:
    """Best-effort durable lock for source intelligence background work.

    Postgres uses transaction-scoped advisory locks so duplicate Celery workers
    skip the same source/user instead of racing. SQLite unit tests and local
    metadata runs use a no-op lock because they execute in one process.
    """

    dialect = db.get_bind().dialect.name
    if dialect != "postgresql":
        yield True
        return

    lock_key = advisory_lock_key(key)
    result = await db.execute(text("select pg_try_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})
    locked = bool(result.scalar_one())
    yield locked


def advisory_lock_key(key: str) -> int:
    digest = hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)
