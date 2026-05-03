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

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url):
            return httpx.Response(
                302,
                headers={"location": "https://127.0.0.1/admin"},
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(url_safety.httpx, "AsyncClient", FakeClient)

    with pytest.raises(ValueError, match="Local or private network addresses are not allowed"):
        await url_safety.fetch_public_https("https://8.8.8.8/start", timeout=1)
