from __future__ import annotations

import ssl
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


ASYNC_PG_SSL_QUERY_KEYS = {"sslmode", "channel_binding"}


def _build_ssl_connect_arg() -> ssl.SSLContext | bool:
    try:
        import certifi
    except Exception:
        return True
    return ssl.create_default_context(cafile=certifi.where())


def normalize_asyncpg_database_url(database_url: str | None) -> tuple[str | None, dict[str, object]]:
    """Return a SQLAlchemy asyncpg URL plus driver connect args.

    Neon and other hosted Postgres providers commonly expose libpq-style URLs
    with query params such as sslmode=require. asyncpg does not accept those
    names directly, so we strip them from the URL and pass ssl via connect_args.
    """

    if not database_url:
        return database_url, {}

    parts = urlsplit(database_url)
    if parts.scheme not in {"postgresql", "postgresql+asyncpg"}:
        return database_url, {}

    query_items = parse_qsl(parts.query, keep_blank_values=True)
    cleaned_query_items: list[tuple[str, str]] = []
    ssl_requested = False

    for key, value in query_items:
        normalized_key = key.lower()
        if normalized_key == "sslmode":
            ssl_requested = value.lower() not in {"", "disable", "allow"}
            continue
        if normalized_key == "channel_binding":
            continue
        cleaned_query_items.append((key, value))

    if len(cleaned_query_items) == len(query_items) and not ssl_requested:
        return database_url, {}

    normalized_url = urlunsplit(
        (
            "postgresql+asyncpg",
            parts.netloc,
            parts.path,
            urlencode(cleaned_query_items, doseq=True),
            parts.fragment,
        )
    )
    connect_args: dict[str, object] = {"ssl": _build_ssl_connect_arg()} if ssl_requested else {}
    return normalized_url, connect_args
