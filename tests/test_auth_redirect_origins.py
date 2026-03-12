from fastapi import Request


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


def test_preview_vercel_origin_is_allowed():
    from backend.main import _is_allowed_frontend_origin

    assert _is_allowed_frontend_origin(
        "https://apptrail-git-local-dev-colbys-projects-24eca82b.vercel.app"
    )


def test_unrelated_vercel_origin_is_rejected():
    from backend.main import _is_allowed_frontend_origin

    assert not _is_allowed_frontend_origin("https://evil.vercel.app")


def test_resolve_frontend_origin_prefers_allowed_preview_query_value():
    from backend.main import _resolve_frontend_origin

    request = _request_with_headers(
        origin="https://apptrail1.vercel.app",
        referer="https://apptrail1.vercel.app/inbox",
    )

    resolved = _resolve_frontend_origin(
        "https://apptrail-git-local-dev-colbys-projects-24eca82b.vercel.app",
        request,
    )

    assert resolved == "https://apptrail-git-local-dev-colbys-projects-24eca82b.vercel.app"


def test_frontend_callback_url_embeds_access_token_in_fragment():
    from backend.main import _build_frontend_callback_url

    callback_url = _build_frontend_callback_url(
        "https://apptrail1.vercel.app",
        "header.payload.signature",
    )

    assert callback_url == "https://apptrail1.vercel.app/auth/callback#access_token=header.payload.signature"


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
