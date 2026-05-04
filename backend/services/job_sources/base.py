from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class SourceConfig:
    provider_type: str
    provider_key: str
    access_mode: str
    company_name: str | None = None
    company_domain: str | None = None
    career_url: str | None = None
    public_jobs_endpoint: str | None = None
    source_config: dict = field(default_factory=dict)
    verification_status: str = "pending"
    terms_risk: str = "unknown"


@dataclass(frozen=True)
class SearchQuery:
    query: str = ""
    location: str = ""
    limit: int = 50


@dataclass(frozen=True)
class NormalizedJobPosting:
    external_job_id: str | None
    title: str
    company_name: str
    company_domain: str | None
    description_text: str | None
    location_text: str | None
    remote_status: str | None
    employment_type: str | None
    department: str | None
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    salary_period: str | None
    date_posted: datetime | None
    valid_through: datetime | None
    canonical_url: str
    source_type: str
    source_confidence: float
    redacted_metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class VerificationResult:
    status: str
    access_mode: str
    job_count: int | None = None
    http_status: int | None = None
    error_type: str | None = None
    error_message_redacted: str | None = None
    terms_risk: str = "unknown"


class JobSourceAdapter(Protocol):
    provider_type: str

    def parse_source_from_url(self, url: str) -> SourceConfig | None: ...

    async def verify_source(self, config: SourceConfig) -> VerificationResult: ...

    async def fetch_jobs(self, config: SourceConfig, query: SearchQuery) -> list[NormalizedJobPosting]: ...

    async def fetch_job_detail(self, config: SourceConfig, external_id_or_path: str) -> NormalizedJobPosting | None: ...


def text_or_none(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_datetime(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
