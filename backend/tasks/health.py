"""Operational health tasks for production readiness checks."""

import os
from datetime import datetime, timezone

import redis

from backend.celery_app import celery_app


@celery_app.task(name="backend.tasks.health.record_beat_heartbeat")
def record_beat_heartbeat() -> str:
    """Record that Celery beat scheduled work and a worker executed it."""
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return "redis_not_configured"

    now = datetime.now(timezone.utc).isoformat()
    client = redis.from_url(redis_url, decode_responses=True)
    try:
        client.setex("apptrail:celery:beat:last_seen", 300, now)
    finally:
        client.close()
    return now
