import os

from backend.env import load_app_env


def test_load_app_env_prefers_local_dotenv_for_development(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text(
        "ENVIRONMENT=development\n"
        "DATABASE_URL=postgresql+asyncpg://neon.example/neondb\n"
        "OPENAI_API_KEY=from-env\n",
        encoding="utf-8",
    )
    (tmp_path / ".env.local").write_text(
        "DATABASE_URL=postgresql+asyncpg://apptrail:apptrail@localhost:5432/apptrail\n"
        "OPENAI_API_KEY=\n"
        "LOCAL_DEV_AUTH=1\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LOCAL_DEV_AUTH", raising=False)

    load_app_env(root_dir=tmp_path)

    assert (
        os.environ["DATABASE_URL"]
        == "postgresql+asyncpg://apptrail:apptrail@localhost:5432/apptrail"
    )
    assert os.environ["OPENAI_API_KEY"] == ""
    assert os.environ["LOCAL_DEV_AUTH"] == "1"


def test_load_app_env_keeps_process_env_by_default(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text(
        "ENVIRONMENT=development\n"
        "DATABASE_URL=postgresql+asyncpg://neon.example/neondb\n",
        encoding="utf-8",
    )
    (tmp_path / ".env.local").write_text(
        "DATABASE_URL=postgresql+asyncpg://apptrail:apptrail@localhost:5432/apptrail\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://explicit.example/app")
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    load_app_env(root_dir=tmp_path)

    assert os.environ["DATABASE_URL"] == "postgresql+asyncpg://explicit.example/app"


def test_load_app_env_skips_local_dotenv_for_production(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text(
        "ENVIRONMENT=production\n"
        "DATABASE_URL=postgresql+asyncpg://neon.example/neondb\n",
        encoding="utf-8",
    )
    (tmp_path / ".env.local").write_text(
        "DATABASE_URL=postgresql+asyncpg://apptrail:apptrail@localhost:5432/apptrail\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    load_app_env(root_dir=tmp_path)

    assert os.environ["ENVIRONMENT"] == "production"
    assert os.environ["DATABASE_URL"] == "postgresql+asyncpg://neon.example/neondb"
