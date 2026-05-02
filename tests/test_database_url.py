from backend.database_url import normalize_asyncpg_database_url


def test_normalize_asyncpg_database_url_converts_neon_ssl_params_to_connect_args():
    url = (
        "postgresql+asyncpg://user:pass@example.neon.tech/db"
        "?sslmode=require&channel_binding=require"
    )

    normalized_url, connect_args = normalize_asyncpg_database_url(url)

    assert normalized_url == "postgresql+asyncpg://user:pass@example.neon.tech/db"
    assert connect_args == {"ssl": True}


def test_normalize_asyncpg_database_url_preserves_other_query_params():
    url = (
        "postgresql+asyncpg://user:pass@example.neon.tech/db"
        "?sslmode=require&application_name=apptrail"
    )

    normalized_url, connect_args = normalize_asyncpg_database_url(url)

    assert normalized_url == "postgresql+asyncpg://user:pass@example.neon.tech/db?application_name=apptrail"
    assert connect_args == {"ssl": True}


def test_normalize_asyncpg_database_url_leaves_sqlite_urls_unchanged():
    url = "sqlite+aiosqlite:///:memory:"

    normalized_url, connect_args = normalize_asyncpg_database_url(url)

    assert normalized_url == url
    assert connect_args == {}
