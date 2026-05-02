import os


_TRUTHY_VALUES = {"1", "true", "yes", "on"}


def env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY_VALUES


def is_development_environment() -> bool:
    return os.getenv("ENVIRONMENT", "development").lower() == "development" or os.getenv("TESTING") == "1"


def radar_enabled() -> bool:
    return env_flag("RADAR_ENABLED", default=True)


def radar_research_enabled() -> bool:
    return radar_enabled() and env_flag("RADAR_RESEARCH_ENABLED", default=is_development_environment())


def admin_ai_ops_enabled() -> bool:
    return env_flag("ADMIN_AI_OPS_ENABLED", default=is_development_environment())
