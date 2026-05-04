from __future__ import annotations

import json
import os
import urllib.robotparser
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from backend.services.job_sources.base import NormalizedJobPosting, SearchQuery, SourceConfig, VerificationResult, parse_datetime, text_or_none
from backend.services.source_intelligence.url_classifier import classify_url
from backend.services.url_safety import DEFAULT_USER_AGENT, fetch_public_https


PROVIDER = "structured_data"


def parse_source_from_url(url: str) -> SourceConfig | None:
    classified = classify_url(url)
    if not classified.normalized_url or classified.contains_private_token:
        return None
    if classified.provider_type and classified.provider_type not in {"custom_career_page", "structured_data"}:
        return None
    host = classified.hostname
    if not host:
        return None
    return SourceConfig(
        provider_type=PROVIDER,
        provider_key=host,
        access_mode="public",
        company_name=host.removeprefix("www."),
        company_domain=host.removeprefix("www."),
        career_url=classified.normalized_url,
        public_jobs_endpoint=classified.normalized_url,
        source_config={"single_page_url": classified.normalized_url},
        verification_status="pending",
        terms_risk="unknown",
    )


async def verify_source(config: SourceConfig) -> VerificationResult:
    if not _custom_crawl_enabled():
        return VerificationResult(status="blocked", access_mode=config.access_mode, error_type="custom_crawl_disabled", terms_risk="unknown")
    try:
        allowed = await robots_allowed(config.public_jobs_endpoint or config.career_url or "")
        if not allowed:
            return VerificationResult(status="blocked", access_mode=config.access_mode, error_type="robots_disallowed", terms_risk="unknown")
        posting = await fetch_job_detail(config, config.public_jobs_endpoint or config.career_url or "")
        return VerificationResult(status="verified" if posting else "needs_review", access_mode=config.access_mode, job_count=1 if posting else 0, terms_risk="unknown")
    except Exception as exc:
        return VerificationResult(status="failed", access_mode=config.access_mode, error_type=type(exc).__name__, error_message_redacted=str(exc)[:240], terms_risk="unknown")


async def fetch_jobs(config: SourceConfig, query: SearchQuery) -> list[NormalizedJobPosting]:
    detail = await fetch_job_detail(config, config.public_jobs_endpoint or config.career_url or "")
    return [detail] if detail else []


async def fetch_job_detail(config: SourceConfig, external_id_or_path: str) -> NormalizedJobPosting | None:
    if not _custom_crawl_enabled():
        return None
    url = external_id_or_path or config.public_jobs_endpoint or config.career_url
    if not url or not await robots_allowed(url):
        return None
    response = await fetch_public_https(url, timeout=10)
    response.raise_for_status()
    html = response.text
    postings = _extract_job_postings(html)
    if len(postings) != 1:
        return None
    posting = postings[0]
    soup_text = _visible_text(html).lower()
    title = text_or_none(posting.get("title") or posting.get("name"))
    if not title or title.lower() not in soup_text:
        return None
    company = posting.get("hiringOrganization") or {}
    location_text = _location_text(posting.get("jobLocation"))
    return NormalizedJobPosting(
        external_job_id=text_or_none(posting.get("identifier", {}).get("value") if isinstance(posting.get("identifier"), dict) else posting.get("identifier")),
        title=title,
        company_name=text_or_none(company.get("name") if isinstance(company, dict) else company) or config.company_name or config.provider_key,
        company_domain=config.company_domain,
        description_text=BeautifulSoup(posting.get("description") or "", "html.parser").get_text(" ", strip=True) or None,
        location_text=location_text,
        remote_status=None,
        employment_type=text_or_none(posting.get("employmentType")),
        department=None,
        salary_min=None,
        salary_max=None,
        salary_currency=None,
        salary_period=None,
        date_posted=parse_datetime(posting.get("datePosted")),
        valid_through=parse_datetime(posting.get("validThrough")),
        canonical_url=url,
        source_type=PROVIDER,
        source_confidence=0.7,
        redacted_metadata={"provider_key": config.provider_key, "schema_type": "JobPosting"},
    )


async def robots_allowed(url: str) -> bool:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return False
    robots_url = urljoin(f"{parsed.scheme}://{parsed.netloc}", "/robots.txt")
    try:
        response = await fetch_public_https(robots_url, timeout=5)
        if response.status_code >= 400:
            return False
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(response.text.splitlines())
        return parser.can_fetch(DEFAULT_USER_AGENT, url)
    except Exception:
        return False


def _custom_crawl_enabled() -> bool:
    return os.getenv("JOB_SEARCH_CUSTOM_CRAWL_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


def _extract_job_postings(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    postings: list[dict] = []
    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            continue
        for item in _iter_jsonld_items(data):
            if _jsonld_type(item) == "jobposting":
                postings.append(item)
    return postings


def _iter_jsonld_items(data):
    if isinstance(data, list):
        for item in data:
            yield from _iter_jsonld_items(item)
    elif isinstance(data, dict):
        graph = data.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from _iter_jsonld_items(item)
        else:
            yield data


def _jsonld_type(item: dict) -> str:
    value = item.get("@type")
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "").lower()


def _visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template", "iframe", "form"]):
        tag.decompose()
    return soup.get_text(" ", strip=True)


def _location_text(value) -> str | None:
    if isinstance(value, list):
        return "; ".join(filter(None, (_location_text(item) for item in value))) or None
    if not isinstance(value, dict):
        return text_or_none(value)
    address = value.get("address")
    if isinstance(address, dict):
        return ", ".join(str(part) for part in [address.get("addressLocality"), address.get("addressRegion"), address.get("addressCountry")] if part) or None
    return text_or_none(value.get("name"))
