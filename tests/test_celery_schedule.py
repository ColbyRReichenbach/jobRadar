import importlib


def _reload_celery_app(monkeypatch, **env):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    for name in (
        "SCHEDULED_DB_JOBS_ENABLED",
        "GMAIL_POLLING_ENABLED",
        "RADAR_ENABLED",
        "JOB_SOURCE_VERIFICATION_BEAT_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    import backend.celery_app as celery_module

    return importlib.reload(celery_module)


def test_celery_beat_defaults_to_redis_only_heartbeat(monkeypatch):
    celery_module = _reload_celery_app(monkeypatch)

    assert set(celery_module.beat_schedule) == {"record-beat-heartbeat"}


def test_celery_beat_does_not_poll_gmail_when_only_db_jobs_enabled(monkeypatch):
    celery_module = _reload_celery_app(
        monkeypatch,
        SCHEDULED_DB_JOBS_ENABLED="true",
    )

    assert "check-followups-daily-9am" in celery_module.beat_schedule
    assert "poll-gmail" not in celery_module.beat_schedule
    assert "dispatch-due-research-profiles" not in celery_module.beat_schedule


def test_celery_beat_enables_explicit_pollers(monkeypatch):
    celery_module = _reload_celery_app(
        monkeypatch,
        SCHEDULED_DB_JOBS_ENABLED="true",
        GMAIL_POLLING_ENABLED="true",
        RADAR_ENABLED="true",
    )

    assert "poll-gmail" in celery_module.beat_schedule
    assert "dispatch-due-research-profiles" in celery_module.beat_schedule
