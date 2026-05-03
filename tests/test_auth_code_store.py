import pytest

from backend import dependencies


@pytest.fixture(autouse=True)
def reset_auth_code_store():
    dependencies._auth_code_store.clear()
    yield
    dependencies._auth_code_store.clear()


def test_in_memory_auth_code_fallback_is_one_time_and_ttl_bound(monkeypatch):
    clock = {"now": 1_000.0}
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("TESTING", "1")
    monkeypatch.setattr(dependencies, "_get_redis_client", lambda: None)
    monkeypatch.setattr(dependencies.time, "time", lambda: clock["now"])

    dependencies.store_auth_code("oauth-code", '{"user_id":"user-1"}')

    assert dependencies.consume_auth_code("oauth-code") == '{"user_id":"user-1"}'
    assert dependencies.consume_auth_code("oauth-code") is None


def test_in_memory_auth_code_fallback_rejects_expired_codes(monkeypatch):
    clock = {"now": 1_000.0}
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("TESTING", "1")
    monkeypatch.setattr(dependencies, "_get_redis_client", lambda: None)
    monkeypatch.setattr(dependencies.time, "time", lambda: clock["now"])

    dependencies.store_auth_code("oauth-code", '{"user_id":"user-1"}')
    clock["now"] += dependencies._AUTH_CODE_TTL + 1

    assert dependencies.consume_auth_code("oauth-code") is None


def test_auth_code_fallback_fails_closed_in_production_without_redis(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setattr(dependencies, "_get_redis_client", lambda: None)

    with pytest.raises(dependencies.AuthCodeStoreUnavailableError):
        dependencies.store_auth_code("oauth-code", '{"user_id":"user-1"}')

    with pytest.raises(dependencies.AuthCodeStoreUnavailableError):
        dependencies.consume_auth_code("oauth-code")
