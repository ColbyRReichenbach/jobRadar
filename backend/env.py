from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values


ROOT_DIR = Path(__file__).resolve().parents[1]


def load_app_env(*, root_dir: Path | None = None, override: bool = False) -> None:
    """Load AppTrail dotenv files without letting local dev wake hosted services.

    The checked-in local workflow writes `.env.local` for Docker/manual dev. When
    it exists, it should beat `.env` so commands like `uvicorn` and `alembic`
    use local Postgres instead of a hosted Neon database. Existing process env
    vars keep priority by default, which is what production and tests need.
    """

    base_dir = root_dir or ROOT_DIR
    default_values = _read_dotenv(base_dir / ".env")

    environment = (
        os.environ.get("ENVIRONMENT")
        or default_values.get("ENVIRONMENT")
        or "development"
    ).strip().lower()

    merged_values = dict(default_values)
    if environment != "production":
        merged_values.update(_read_dotenv(base_dir / ".env.local"))

    for key, value in merged_values.items():
        if value is None:
            continue
        if override or key not in os.environ:
            os.environ[key] = value


def _read_dotenv(path: Path) -> dict[str, str | None]:
    if not path.exists():
        return {}
    return dict(dotenv_values(path))
