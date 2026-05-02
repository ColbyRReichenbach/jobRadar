from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx


_MAX_REDIRECTS = 5


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
) -> httpx.Response:
    current_url = await validate_public_https_url(url)
    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=False) as client:
        for _ in range(max_redirects + 1):
            response = await client.get(current_url)
            if not response.is_redirect:
                return response

            location = response.headers.get("location")
            if not location:
                return response

            next_url = urljoin(str(response.url), location)
            current_url = await validate_public_https_url(next_url)

    raise httpx.HTTPError("Too many redirects while fetching public URL")
