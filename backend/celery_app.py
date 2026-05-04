import os
import warnings

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    if os.getenv("ENVIRONMENT", "development") != "development":
        raise RuntimeError(
            "REDIS_URL environment variable is required in production. "
            "Set it to your Upstash Redis TLS URL (rediss://...)."
        )
    warnings.warn("REDIS_URL not set — Celery will use redis://localhost:6379/0 (dev only)")
    REDIS_URL = "redis://localhost:6379/0"

celery_app = Celery(
    "apptrail",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "backend.tasks.health",
        "backend.tasks.poll_gmail",
        "backend.tasks.check_followups",
        "backend.tasks.check_dead_apps",
        "backend.tasks.compute_ats_metrics",
        "backend.tasks.send_weekly_digest",
        "backend.tasks.run_research_radar",
        "backend.tasks.index_search_documents",
        "backend.tasks.reprocess_source_intelligence",
        "backend.tasks.verify_job_sources",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    task_default_retry_delay=60,
    task_default_max_retries=3,
    task_acks_late=True,
    worker_prefetch_multiplier=int(os.getenv("CELERY_PREFETCH_MULTIPLIER", "1")),
    worker_concurrency=int(os.getenv("CELERY_CONCURRENCY", "4")),
    worker_max_tasks_per_child=int(os.getenv("CELERY_MAX_TASKS_PER_CHILD", "100")),
    task_soft_time_limit=int(os.getenv("CELERY_SOFT_TIME_LIMIT_SECONDS", "300")),
    task_time_limit=int(os.getenv("CELERY_TIME_LIMIT_SECONDS", "600")),
    result_expires=int(os.getenv("CELERY_RESULT_EXPIRES_SECONDS", "3600")),
    beat_schedule={
        "poll-gmail-every-15-min": {
            "task": "backend.tasks.poll_gmail.poll_gmail",
            "schedule": 900.0,  # 15 minutes
        },
        "check-followups-daily-9am": {
            "task": "backend.tasks.check_followups.check_followups",
            "schedule": 86400.0,  # daily (24 hours)
        },
        "check-dead-apps-daily": {
            "task": "backend.tasks.check_dead_apps.check_dead_apps",
            "schedule": 86400.0,  # daily
        },
        "compute-ats-metrics-weekly": {
            "task": "backend.tasks.compute_ats_metrics.compute_ats_metrics_task",
            "schedule": 604800.0,  # weekly
        },
        "send-weekly-digest": {
            "task": "backend.tasks.send_weekly_digest.send_weekly_digest",
            "schedule": 604800.0,  # weekly
        },
        "dispatch-due-research-profiles": {
            "task": "backend.tasks.run_research_radar.dispatch_due_research_profiles",
            "schedule": 900.0,  # every 15 minutes
        },
        "record-beat-heartbeat": {
            "task": "backend.tasks.health.record_beat_heartbeat",
            "schedule": 60.0,
        },
        "verify-pending-job-sources": {
            "task": "backend.tasks.verify_job_sources.verify_due_sources",
            "schedule": 900.0,
        },
    },
)
