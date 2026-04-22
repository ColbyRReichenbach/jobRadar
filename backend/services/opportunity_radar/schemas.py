from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class SourceCandidate:
    source_type: str
    source_name: str | None
    source_url: str
    external_id: str | None
    title: str | None
    raw_text: str | None
    raw_json: dict[str, Any] | None
    company_domain: str | None
    company_name: str | None
    role_title: str | None
    published_at: datetime | None
    content_hash: str | None
