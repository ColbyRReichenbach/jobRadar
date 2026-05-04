from backend.services.production_readiness import PRODUCTION_AI_CAP_DEFAULTS, validate_production_environment


def _valid_env() -> dict[str, str]:
    values = {
        "DATABASE_URL": "postgresql+asyncpg://user:pass@example.com/app",
        "REDIS_URL": "redis://redis.example.com:6379/0",
        "JWT_SECRET": "secret",
        "APPTRAIL_GMAIL_TOKEN_ENCRYPTION_KEY": "fernet",
        "OPENAI_API_KEY": "sk-live-test",
        "GMAIL_CLIENT_ID": "client-id",
        "GMAIL_CLIENT_SECRET": "client-secret",
        "DASHBOARD_URL": "https://app.example.com",
        "API_URL": "https://api.example.com",
        "SOURCE_LINK_ENCRYPTION_KEY": "source-fernet",
        "SOURCE_LINK_HASH_KEY": "source-hmac",
        "JOB_SEARCH_DIRECT_SOURCES_ENABLED": "true",
        "JOB_SEARCH_WORKDAY_ENABLED": "false",
        "JOB_SEARCH_CUSTOM_CRAWL_ENABLED": "false",
        "JOB_SEARCH_BROAD_PROVIDER_ENABLED": "true",
        "JOB_SEARCH_SERPAPI_MONTHLY_CAP": "250",
        "JOB_SEARCH_SERPAPI_USER_MONTHLY_CAP": "25",
        "SOURCE_VERIFICATION_MAX_SOURCES_PER_RUN": "100",
        "SOURCE_FETCH_MAX_BYTES": "1048576",
        "SOURCE_FETCH_TIMEOUT_SECONDS": "10",
        "POSTGRES_BACKUPS_ENABLED": "true",
        "POSTGRES_BACKUP_PROVIDER": "Neon automated backups",
    }
    values.update(PRODUCTION_AI_CAP_DEFAULTS)
    return values


def test_production_readiness_accepts_explicit_beta_ai_caps():
    issues = validate_production_environment(_valid_env())
    assert issues == []


def test_production_readiness_rejects_implicit_caps_and_missing_redis():
    env = _valid_env()
    env.pop("REDIS_URL")
    env.pop("AI_DAILY_TOKEN_CAP_PER_USER")
    env.pop("SOURCE_LINK_HASH_KEY")
    env["JOB_SEARCH_SERPAPI_MONTHLY_CAP"] = "0"
    env["POSTGRES_BACKUPS_ENABLED"] = "false"

    issues = validate_production_environment(env)
    issue_keys = {issue.key for issue in issues}

    assert "REDIS_URL" in issue_keys
    assert "AI_DAILY_TOKEN_CAP_PER_USER" in issue_keys
    assert "SOURCE_LINK_HASH_KEY" in issue_keys
    assert "JOB_SEARCH_SERPAPI_MONTHLY_CAP" in issue_keys
    assert "POSTGRES_BACKUPS_ENABLED" in issue_keys
