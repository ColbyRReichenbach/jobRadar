from fastapi import Request
import pytest

from tests.conftest import TEST_USER_ID


def _request_with_headers(**headers: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/auth/google",
            "headers": [
                (key.encode("latin-1"), value.encode("latin-1"))
                for key, value in headers.items()
            ],
        }
    )


def test_local_frontend_origin_is_allowed():
    from backend.main import _is_allowed_frontend_origin

    assert _is_allowed_frontend_origin("http://localhost:5173")


def test_local_frontend_origins_are_not_allowed_in_production(monkeypatch):
    from backend.main import _configured_cors_origins, _is_allowed_frontend_origin

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.delenv("DASHBOARD_URL", raising=False)
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("VERCEL_PREVIEW_ORIGINS", raising=False)

    assert "http://localhost:5173" not in _configured_cors_origins()
    assert not _is_allowed_frontend_origin("http://localhost:5173")


def test_preview_vercel_origin_is_rejected_by_default():
    from backend.main import _is_allowed_frontend_origin

    assert not _is_allowed_frontend_origin(
        "https://apptrail-git-local-dev-colbys-projects-24eca82b.vercel.app"
    )


def test_unrelated_vercel_origin_is_rejected():
    from backend.main import _is_allowed_frontend_origin

    assert not _is_allowed_frontend_origin("https://evil.vercel.app")


def test_resolve_frontend_origin_prefers_exact_allowed_query_value():
    from backend.main import _resolve_frontend_origin

    request = _request_with_headers(
        origin="http://localhost:5173",
        referer="http://localhost:5173/inbox",
    )

    resolved = _resolve_frontend_origin(
        "http://localhost:3000",
        request,
    )

    assert resolved == "http://localhost:3000"


def test_frontend_callback_url_embeds_auth_code_in_query():
    from backend.main import _build_frontend_callback_url

    callback_url = _build_frontend_callback_url(
        "https://apptrail1.vercel.app",
        "one-time-auth-code-123",
    )

    assert callback_url == "https://apptrail1.vercel.app/auth/callback?code=one-time-auth-code-123"


def test_oauth_context_roundtrip_survives_missing_padding():
    from backend.main import _decode_oauth_context, _encode_oauth_context

    payload = {
        "connect_gmail": True,
        "connect_calendar": False,
        "code_verifier": "abc123verifier",
        "frontend_origin": "https://apptrail1.vercel.app",
        "oauth_state": "google-generated-state",
    }

    encoded = _encode_oauth_context(payload)
    assert "=" not in encoded
    assert _decode_oauth_context(encoded) == payload


def test_google_authorization_response_uses_configured_callback_origin():
    from backend.main import GOOGLE_REDIRECT_URI, _build_google_authorization_response

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/auth/google/callback",
            "query_string": b"code=abc&state=xyz",
            "headers": [],
        }
    )

    assert _build_google_authorization_response(request) == f"{GOOGLE_REDIRECT_URI}?code=abc&state=xyz"


def test_google_authorization_response_can_replace_wrapped_state():
    from backend.main import GOOGLE_REDIRECT_URI, _build_google_authorization_response

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/auth/google/callback",
            "query_string": b"code=abc&state=wrapped-state&scope=email",
            "headers": [],
        }
    )

    assert _build_google_authorization_response(request, "google-state") == (
        f"{GOOGLE_REDIRECT_URI}?code=abc&state=google-state&scope=email"
    )


def test_google_authorization_kwargs_only_include_incremental_scopes_for_connect_flows():
    from backend.main import _google_authorization_kwargs

    assert _google_authorization_kwargs(False, False) == {
        "prompt": "consent",
        "access_type": "offline",
    }
    assert _google_authorization_kwargs(True, False) == {
        "prompt": "consent",
        "access_type": "offline",
        "include_granted_scopes": "true",
    }


@pytest.mark.asyncio
async def test_refresh_rejects_disallowed_origin(client):
    from backend.dependencies import REFRESH_COOKIE_NAME, create_refresh_token

    response = await client.post(
        "/api/auth/refresh",
        cookies={REFRESH_COOKIE_NAME: create_refresh_token(str(TEST_USER_ID))},
        headers={"Origin": "https://evil.example"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_refresh_accepts_exact_allowed_origin(client):
    from backend.dependencies import REFRESH_COOKIE_NAME, create_refresh_token

    response = await client.post(
        "/api/auth/refresh",
        cookies={REFRESH_COOKIE_NAME: create_refresh_token(str(TEST_USER_ID))},
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_local_login_stays_disabled_in_production_even_if_flag_is_set(client, monkeypatch):
    monkeypatch.setenv("LOCAL_DEV_AUTH", "true")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("TESTING", raising=False)

    response = await client.post(
        "/api/auth/local-login",
        json={"email": "local@example.com", "name": "Local User"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_refresh_token_cannot_be_used_as_bearer_access_token(client):
    from backend.dependencies import create_refresh_token

    response = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {create_refresh_token(str(TEST_USER_ID))}"},
    )

    assert response.status_code == 401
