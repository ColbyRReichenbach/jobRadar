import os

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "apptrail",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["backend.tasks.poll_gmail", "backend.tasks.check_followups", "backend.tasks.check_dead_apps", "backend.tasks.compute_ats_metrics", "backend.tasks.send_weekly_digest"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_default_retry_delay=60,
    task_default_max_retries=3,
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
    },
)
