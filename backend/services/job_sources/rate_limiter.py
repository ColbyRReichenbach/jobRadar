from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any


class ProviderRateLimitExceeded(RuntimeError):
    pass


@dataclass
class _Bucket:
    count: int
    reset_at: float


_redis_client: Any | None = None
_memory_lock = asyncio.Lock()
_memory_buckets: dict[str, _Bucket] = {}
_memory_last_seen: dict[str, float] = {}


async def enforce_provider_rate_limit(
    provider_type: str,
    scope: str,
    *,
    limit: int,
    window_seconds: int = 60,
    min_interval_seconds: float = 0,
) -> None:
    key_scope = _normalize_scope(scope)
    counter_key = f"job_source_rate:{provider_type}:{key_scope}:{int(time.time() // window_seconds)}"
    interval_key = f"job_source_interval:{provider_type}:{key_scope}"
    client = await _get_redis_client()
    if client is not None:
        await _enforce_redis(client, counter_key, interval_key, limit=limit, window_seconds=window_seconds, min_interval_seconds=min_interval_seconds)
        return
    await _enforce_memory(counter_key, interval_key, limit=limit, window_seconds=window_seconds, min_interval_seconds=min_interval_seconds)


async def _get_redis_client() -> Any | None:
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return None
    try:
        import redis.asyncio as redis  # type: ignore

        _redis_client = redis.from_url(redis_url, decode_responses=True)
        await _redis_client.ping()
        return _redis_client
    except Exception:
        _redis_client = None
        return None


async def _enforce_redis(client: Any, counter_key: str, interval_key: str, *, limit: int, window_seconds: int, min_interval_seconds: float) -> None:
    if min_interval_seconds > 0:
        raw_last_seen = await client.get(interval_key)
        if raw_last_seen:
            wait_seconds = min_interval_seconds - (time.time() - float(raw_last_seen))
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
        await client.set(interval_key, str(time.time()), ex=max(window_seconds, int(min_interval_seconds) + 2))
    count = await client.incr(counter_key)
    if count == 1:
        await client.expire(counter_key, window_seconds)
    if count > limit:
        raise ProviderRateLimitExceeded("provider_rate_limit_exceeded")


async def _enforce_memory(counter_key: str, interval_key: str, *, limit: int, window_seconds: int, min_interval_seconds: float) -> None:
    async with _memory_lock:
        now = time.time()
        if min_interval_seconds > 0:
            last_seen = _memory_last_seen.get(interval_key)
            if last_seen:
                wait_seconds = min_interval_seconds - (now - last_seen)
                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)
                    now = time.time()
            _memory_last_seen[interval_key] = now
        bucket = _memory_buckets.get(counter_key)
        if bucket is None or bucket.reset_at <= now:
            bucket = _Bucket(count=0, reset_at=now + window_seconds)
            _memory_buckets[counter_key] = bucket
        bucket.count += 1
        if bucket.count > limit:
            raise ProviderRateLimitExceeded("provider_rate_limit_exceeded")


def _normalize_scope(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-", ":"} else "_" for ch in value.lower())[:120] or "unknown"
