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
