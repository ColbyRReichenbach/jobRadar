from __future__ import annotations

import hashlib
import re

from backend.services.job_sources.base import NormalizedJobPosting
from backend.services.source_intelligence.url_sanitizer import source_link_hash


def dedupe_key_for_posting(posting: NormalizedJobPosting, *, provider_key: str | None = None) -> str:
    if posting.external_job_id and provider_key:
        return f"{posting.source_type}:{provider_key}:{posting.external_job_id}".lower()
    if posting.canonical_url:
        digest, version = source_link_hash(posting.canonical_url)
        return f"url:{version}:{digest}"

    identity = "|".join(
        [
            _normalize(posting.company_name),
            _normalize(posting.title),
            _normalize(posting.location_text),
            _description_prefix(posting.description_text),
        ]
    )
    return f"semantic:{hashlib.sha256(identity.encode('utf-8')).hexdigest()}"


def _normalize(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _description_prefix(value: str | None) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
