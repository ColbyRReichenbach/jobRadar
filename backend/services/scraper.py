import asyncio
import ipaddress
import json
import logging
import re
import socket
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from backend.services.claude_client import extract_job_from_html
from backend.services.url_safety import fetch_public_https
from backend.utils.retry import with_retry

logger = logging.getLogger(__name__)

REALISTIC_UA = "OpportunityRadar/1.0 (+https://opportunity-radar.app)"

ALLOWED_JOB_HOST_SUFFIXES = (
    "boards.greenhouse.io",
    "greenhouse.io",
    "jobs.lever.co",
    "lever.co",
    "myworkdayjobs.com",
    "myworkday.com",
    "workdayjobs.com",
    "jobs.ashbyhq.com",
    "ashbyhq.com",
    "smartrecruiters.com",
    "jobvite.com",
    "icims.com",
    "taleo.net",
    "oraclecloud.com",
    "successfactors.com",
)


def _is_allowed_job_host(hostname: str) -> bool:
    host = hostname.lower().rstrip(".")
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in ALLOWED_JOB_HOST_SUFFIXES)


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


async def validate_job_parse_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        raise ValueError("Only HTTPS job URLs are allowed")

    if parsed.username or parsed.password:
        raise ValueError("URL credentials are not allowed")

    if not parsed.hostname:
        raise ValueError("Invalid job URL")

    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("Local or private network addresses are not allowed")

    try:
        parsed_ip = ipaddress.ip_address(hostname)
    except ValueError:
        parsed_ip = None
    if parsed_ip and _is_disallowed_ip(str(parsed_ip)):
        raise ValueError("Local or private network addresses are not allowed")

    if not _is_allowed_job_host(hostname):
        raise ValueError("Job URL host is not supported")

    loop = asyncio.get_running_loop()
    try:
        addrinfo = await loop.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Unable to resolve job URL host") from exc

    for entry in addrinfo:
        ip_value = entry[4][0]
        if _is_disallowed_ip(ip_value):
            raise ValueError("Local or private network addresses are not allowed")

    return parsed.geturl()


def detect_platform(url: str) -> str | None:
    patterns = [
        ("greenhouse", r"boards\.greenhouse\.io/([^/]+)/jobs/(\d+)"),
        ("greenhouse", r"[?&]gh_jid=(\d+)"),
        ("lever", r"jobs\.lever\.co/([^/]+)/([a-f0-9-]{36})"),
        ("workday", r"(?:[\w-]+\.)?wd\d+\.myworkday(?:jobs)?\.com/"),
        ("ashby", r"jobs\.ashbyhq\.com/([^/]+)/([a-f0-9-]{36})"),
        ("indeed", r"indeed\.com/viewjob\?jk=([a-z0-9]+)"),
        ("linkedin", r"linkedin\.com/jobs/"),
    ]
    for platform, pattern in patterns:
        if re.search(pattern, url, re.IGNORECASE):
            return platform
    if re.search(r"/careers?/|/jobs?/|careers?\.|jobs?\.", url):
        return "generic"
    return None


def strip_html(html_str: str) -> str:
    if not html_str:
        return ""
    soup = BeautifulSoup(html_str, "html.parser")
    return soup.get_text(separator="\n", strip=True)


def strip_html_noise(html_str: str) -> str:
    if not html_str:
        return ""
    soup = BeautifulSoup(html_str, "html.parser")
    for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    return text[:5000]


def extract_json_ld(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "JobPosting":
                        data = item
                        break
                else:
                    continue
            if isinstance(data, dict) and data.get("@type") == "JobPosting":
                location = data.get("jobLocation", {})
                if isinstance(location, dict):
                    address = location.get("address", {})
                    if isinstance(address, dict):
                        loc = address.get("addressLocality")
                    else:
                        loc = None
                elif isinstance(location, list) and location:
                    address = location[0].get("address", {})
                    loc = address.get("addressLocality") if isinstance(address, dict) else None
                else:
                    loc = None
                return {
                    "title": data.get("title") or data.get("name"),
                    "company": data.get("hiringOrganization", {}).get("name") if isinstance(data.get("hiringOrganization"), dict) else None,
                    "location": loc,
                    "description": strip_html(data.get("description", "")),
                    "posted_at": data.get("datePosted"),
                }
        except (json.JSONDecodeError, AttributeError):
            continue
    return None


async def greenhouse_extract(url: str) -> dict:
    match = re.search(r"greenhouse\.io/([^/]+)/jobs/(\d+)", url)
    if not match:
        raise ValueError(f"Not a Greenhouse URL: {url}")
    token, job_id = match.group(1), match.group(2)

    async def _fetch():
        resp = await fetch_public_https(
            f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{job_id}",
            timeout=10,
            headers={"User-Agent": REALISTIC_UA},
        )
        resp.raise_for_status()
        return resp.json()

    data = await with_retry(_fetch)
    return {
        "title": data["title"],
        "company": token,
        "department": data["departments"][0]["name"] if data.get("departments") else None,
        "location": data["location"]["name"] if data.get("location") else None,
        "description": strip_html(data.get("content", "")),
        "source": "greenhouse",
    }


async def lever_extract(url: str) -> dict:
    match = re.search(r"jobs\.lever\.co/([^/]+)/([a-f0-9-]{36})", url)
    if not match:
        raise ValueError(f"Not a Lever URL: {url}")
    company, posting_uuid = match.group(1), match.group(2)

    async def _fetch():
        resp = await fetch_public_https(
            f"https://api.lever.co/v0/postings/{company}/{posting_uuid}?mode=json",
            timeout=10,
            headers={"User-Agent": REALISTIC_UA},
        )
        resp.raise_for_status()
        return resp.json()

    data = await with_retry(_fetch)
    categories = data.get("categories", {})
    return {
        "title": data.get("text"),
        "company": company,
        "department": categories.get("team"),
        "location": categories.get("location"),
        "description": data.get("descriptionPlain", ""),
        "source": "lever",
    }


async def workday_extract(url: str) -> dict:
    logger.info("Workday browser extraction disabled; using safe HTML extraction")
    return await _claude_fallback(url)


async def _claude_fallback(url: str) -> dict:
    resp = await fetch_public_https(url, timeout=15, headers={"User-Agent": REALISTIC_UA})
    resp.raise_for_status()
    html = resp.text
    cleaned = strip_html_noise(html)
    result = await extract_job_from_html(cleaned)
    result["source"] = "claude_fallback"
    return result


async def extract_job(url: str) -> dict:
    platform = detect_platform(url)

    # Tier 1: Official APIs
    if platform == "greenhouse":
        try:
            return await greenhouse_extract(url)
        except Exception as e:
            logger.warning(f"Greenhouse API failed: {e}")

    if platform == "lever":
        try:
            return await lever_extract(url)
        except Exception as e:
            logger.warning(f"Lever API failed: {e}")

    # Tier 2: JSON-LD
    try:
        resp = await fetch_public_https(url, timeout=15, headers={"User-Agent": REALISTIC_UA})
        resp.raise_for_status()
        html = resp.text
        json_ld = extract_json_ld(html)
        if json_ld and json_ld.get("title"):
            json_ld["source"] = platform or "json_ld"
            return json_ld
    except Exception as e:
        logger.warning(f"JSON-LD extraction failed: {e}")

    # Tier 3: Platform-specific Playwright
    if platform == "workday":
        try:
            return await workday_extract(url)
        except Exception as e:
            logger.warning(f"Workday extraction failed: {e}")

    # Tier 4: Claude API fallback
    try:
        return await _claude_fallback(url)
    except Exception as e:
        logger.error("All extraction methods failed for job URL: %s", e)
        return {
            "title": None,
            "company": None,
            "location": None,
            "department": None,
            "description": None,
            "source": "failed",
        }
