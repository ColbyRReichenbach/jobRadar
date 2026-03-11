import importlib


def test_configure_sentry_skips_without_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monitoring = importlib.import_module("backend.monitoring")
    monitoring._SENTRY_CONFIGURED = False

    assert monitoring.configure_sentry() is False


def test_configure_sentry_initializes_sdk(monkeypatch):
    monitoring = importlib.import_module("backend.monitoring")
    monitoring._SENTRY_CONFIGURED = False

    init_calls = []

    def fake_init(**kwargs):
        init_calls.append(kwargs)

    monkeypatch.setenv("SENTRY_DSN", "https://examplePublicKey@o0.ingest.sentry.io/0")
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "0.25")
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "production")
    monkeypatch.setenv("APP_VERSION", "test-release")
    monkeypatch.setattr(monitoring.sentry_sdk, "init", fake_init)

    assert monitoring.configure_sentry() is True
    assert len(init_calls) == 1
    assert init_calls[0]["dsn"] == "https://examplePublicKey@o0.ingest.sentry.io/0"
    assert init_calls[0]["environment"] == "production"
    assert init_calls[0]["release"] == "test-release"
    assert init_calls[0]["traces_sample_rate"] == 0.25

    monitoring._SENTRY_CONFIGURED = False
