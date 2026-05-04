import pytest

from backend.services.url_safety import validate_public_https_url


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/jobs",
        "https://localhost/admin",
        "https://app.localhost/admin",
        "https://127.0.0.1/admin",
        "https://[::1]/admin",
        "https://10.0.0.5/admin",
        "https://100.64.0.1/admin",
        "https://169.254.169.254/latest/meta-data",
        "https://example.com@127.0.0.1/admin",
    ],
)
async def test_validate_public_https_url_rejects_non_public_targets(url):
    with pytest.raises(ValueError):
        await validate_public_https_url(url)


@pytest.mark.asyncio
async def test_validate_public_https_url_rejects_private_dns_resolution(monkeypatch):
    async def fake_getaddrinfo(*args, **kwargs):
        return [(None, None, None, None, ("10.0.0.5", 443))]

    class FakeLoop:
        getaddrinfo = fake_getaddrinfo

    monkeypatch.setattr("asyncio.get_running_loop", lambda: FakeLoop())

    with pytest.raises(ValueError, match="Local or private network addresses are not allowed"):
        await validate_public_https_url("https://public-looking.example/jobs")


@pytest.mark.asyncio
async def test_fetch_public_https_rejects_redirect_to_private_target(monkeypatch):
    import httpx
    from backend.services import url_safety

    class FakeStream:
        def __init__(self, response):
            self.response = response

        async def __aenter__(self):
            return self.response

        async def __aexit__(self, *args):
            return False

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def stream(self, method, url):
            return FakeStream(
                httpx.Response(
                    302,
                    headers={"location": "https://127.0.0.1/admin"},
                    request=httpx.Request(method, url),
                )
            )

    monkeypatch.setattr(url_safety.httpx, "AsyncClient", FakeClient)

    with pytest.raises(ValueError, match="Local or private network addresses are not allowed"):
        await url_safety.fetch_public_https("https://8.8.8.8/start", timeout=1)


@pytest.mark.asyncio
async def test_fetch_public_https_rejects_oversized_response(monkeypatch):
    import httpx
    from backend.services import url_safety

    class FakeResponse:
        is_redirect = False
        status_code = 200
        headers = {}
        request = httpx.Request("GET", "https://8.8.8.8/start")

        async def aiter_bytes(self):
            yield b"12345"
            yield b"67890"

    class FakeStream:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, *args):
            return False

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def stream(self, method, url):
            return FakeStream()

    monkeypatch.setattr(url_safety.httpx, "AsyncClient", FakeClient)

    with pytest.raises(httpx.HTTPError, match="max byte limit"):
        await url_safety.fetch_public_https("https://8.8.8.8/start", timeout=1, max_bytes=8)


@pytest.mark.asyncio
async def test_fetch_public_https_strips_decoded_content_headers(monkeypatch):
    import httpx
    from backend.services import url_safety

    class FakeResponse:
        is_redirect = False
        status_code = 200
        headers = {"content-encoding": "gzip", "content-length": "99"}
        request = httpx.Request("GET", "https://8.8.8.8/start")

        async def aiter_bytes(self):
            yield b'{"status":"ok"}'

    class FakeStream:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, *args):
            return False

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def stream(self, method, url):
            return FakeStream()

    monkeypatch.setattr(url_safety.httpx, "AsyncClient", FakeClient)

    response = await url_safety.fetch_public_https("https://8.8.8.8/start", timeout=1)

    assert response.headers.get("content-encoding") is None
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_fetch_public_https_drops_sensitive_request_headers(monkeypatch):
    import httpx
    from backend.services import url_safety

    captured_headers = {}

    class FakeResponse:
        is_redirect = False
        status_code = 200
        headers = {}
        request = httpx.Request("GET", "https://8.8.8.8/start")

        async def aiter_bytes(self):
            yield b"ok"

    class FakeStream:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, *args):
            return False

    class FakeClient:
        def __init__(self, *args, **kwargs):
            captured_headers.update(kwargs.get("headers") or {})

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def stream(self, method, url, **kwargs):
            return FakeStream()

    monkeypatch.setattr(url_safety.httpx, "AsyncClient", FakeClient)

    await url_safety.fetch_public_https(
        "https://8.8.8.8/start",
        timeout=1,
        headers={
            "Accept": "application/json",
            "Authorization": "Bearer secret",
            "Cookie": "session=secret",
            "X-API-Key": "secret",
        },
    )

    assert captured_headers["Accept"] == "application/json"
    assert "Authorization" not in captured_headers
    assert "Cookie" not in captured_headers
    assert "X-API-Key" not in captured_headers
