from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
from urllib.parse import urljoin, urlparse

import httpx


_MAX_REDIRECTS = 5
_DEFAULT_MAX_BYTES = 1_048_576
DEFAULT_USER_AGENT = "OpportunityRadar/1.0 (+https://opportunity-radar.app)"


def _is_disallowed_ip(value: str) -> bool:
    ip = ipaddress.ip_address(value)
    return (
        not ip.is_global
        or ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def validate_public_https_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        raise ValueError("Only HTTPS public URLs are allowed")

    if parsed.username or parsed.password:
        raise ValueError("URL credentials are not allowed")

    if not parsed.hostname:
        raise ValueError("Invalid URL")

    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("Local or private network addresses are not allowed")

    try:
        parsed_ip = ipaddress.ip_address(hostname)
    except ValueError:
        parsed_ip = None
    if parsed_ip and _is_disallowed_ip(str(parsed_ip)):
        raise ValueError("Local or private network addresses are not allowed")

    loop = asyncio.get_running_loop()
    try:
        addrinfo = await loop.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Unable to resolve URL host") from exc

    for entry in addrinfo:
        ip_value = entry[4][0]
        if _is_disallowed_ip(ip_value):
            raise ValueError("Local or private network addresses are not allowed")

    return parsed.geturl()


async def fetch_public_https(
    url: str,
    *,
    timeout: float,
    headers: dict[str, str] | None = None,
    max_redirects: int = _MAX_REDIRECTS,
    max_bytes: int | None = None,
) -> httpx.Response:
    current_url = await validate_public_https_url(url)
    byte_limit = max_bytes
    if byte_limit is None:
        byte_limit = int(os.getenv("SOURCE_FETCH_MAX_BYTES", str(_DEFAULT_MAX_BYTES)))
    request_headers = {"User-Agent": DEFAULT_USER_AGENT}
    if headers:
        request_headers.update(headers)
    async with httpx.AsyncClient(timeout=timeout, headers=request_headers, follow_redirects=False, cookies={}) as client:
        for _ in range(max_redirects + 1):
            async with client.stream("GET", current_url) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        return httpx.Response(
                            status_code=response.status_code,
                            headers=response.headers,
                            request=response.request,
                            content=b"",
                        )

                    next_url = urljoin(str(response.url), location)
                    current_url = await validate_public_https_url(next_url)
                    continue

                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > byte_limit:
                        raise httpx.HTTPError("Public URL response exceeded max byte limit")
                return httpx.Response(
                    status_code=response.status_code,
                    headers=response.headers,
                    request=response.request,
                    content=bytes(content),
                )

    raise httpx.HTTPError("Too many redirects while fetching public URL")
