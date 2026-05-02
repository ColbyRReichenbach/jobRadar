"""Sanitized search document builders."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from backend.models import Application, Contact, EmailEvent, ResearchReport

SOURCE_APPLICATION = "application"
SOURCE_CONTACT = "contact"
SOURCE_EMAIL = "email"
SOURCE_RADAR_REPORT = "radar_report"
SUPPORTED_SOURCE_TYPES = {SOURCE_APPLICATION, SOURCE_CONTACT, SOURCE_EMAIL, SOURCE_RADAR_REPORT}


@dataclass(frozen=True)
class SearchDocumentInput:
    user_id: uuid.UUID
    source_type: str
    source_id: uuid.UUID
    title: str
    subtitle: str | None = None
    body: str | None = None
    keywords: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    source_updated_at: datetime | None = None

    @property
    def search_text(self) -> str:
        return normalize_search_text([self.title, self.subtitle, self.body, *self.keywords])

    @property
    def content_hash(self) -> str:
        payload = {
            "source_type": self.source_type,
            "source_id": str(self.source_id),
            "title": self.title,
            "subtitle": self.subtitle,
            "body": self.body,
            "keywords": self.keywords,
            "metadata": self.metadata,
        }
        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def normalize_search_text(parts: list[Any]) -> str:
    text_parts: list[str] = []
    for part in parts:
        if part is None:
            continue
        if isinstance(part, (list, tuple, set)):
            text_parts.extend(str(item) for item in part if item)
            continue
        value = " ".join(str(part).split())
        if value:
            text_parts.append(value)
    return " ".join(text_parts)


def _coerce_user_id(value: uuid.UUID | None, source_type: str) -> uuid.UUID:
    if value is None:
        raise ValueError(f"{source_type} cannot be indexed without user_id")
    return value


def _keyword_values(*values: Any) -> list[str]:
    seen: set[str] = set()
    keywords: list[str] = []
    for value in values:
        if value is None:
            continue
        items = value if isinstance(value, list) else [value]
        for item in items:
            cleaned = " ".join(str(item).split())
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            keywords.append(cleaned)
    return keywords


def build_application_document(app: Application) -> SearchDocumentInput:
    title = f"{app.company} {app.role_title}".strip()
    body = normalize_search_text(
        [
            app.department,
            app.location,
            app.status,
            app.description_text,
            app.notes,
            app.salary,
        ]
    )
    return SearchDocumentInput(
        user_id=_coerce_user_id(app.user_id, SOURCE_APPLICATION),
        source_type=SOURCE_APPLICATION,
        source_id=app.id,
        title=title or "Tracked application",
        subtitle=app.location,
        body=body,
        keywords=_keyword_values(app.company, app.role_title, app.tech_stack, app.source),
        metadata={
            "company": app.company,
            "role_title": app.role_title,
            "status": app.status,
            "job_url": app.job_url,
            "location": app.location,
            "application_id": str(app.id),
        },
        source_updated_at=app.status_updated_at or app.applied_at,
    )


def build_contact_document(contact: Contact) -> SearchDocumentInput:
    title = contact.name or contact.email or "Contact"
    subtitle = normalize_search_text([contact.title, contact.company_name]) or None
    return SearchDocumentInput(
        user_id=_coerce_user_id(contact.user_id, SOURCE_CONTACT),
        source_type=SOURCE_CONTACT,
        source_id=contact.id,
        title=title,
        subtitle=subtitle,
        body=normalize_search_text([contact.email, contact.linkedin_url, contact.source]),
        keywords=_keyword_values(contact.company_name, contact.title, contact.source),
        metadata={
            "application_id": str(contact.application_id) if contact.application_id else None,
            "company_name": contact.company_name,
            "email": contact.email,
            "source": contact.source,
            "contact_id": str(contact.id),
        },
    )


def build_email_document(event: EmailEvent) -> SearchDocumentInput:
    # Deliberately avoid indexing raw email body. Summary/snippet/key sentence are
    # already product-facing and limit exposure if a search payload is inspected.
    title = event.subject or event.summary or "Email update"
    subtitle = normalize_search_text([event.sender, event.sender_email, event.company_name]) or None
    body = normalize_search_text(
        [
            event.summary,
            event.snippet,
            event.key_sentence,
            event.classification,
            event.email_type,
            event.pipeline,
        ]
    )
    return SearchDocumentInput(
        user_id=_coerce_user_id(event.user_id, SOURCE_EMAIL),
        source_type=SOURCE_EMAIL,
        source_id=event.id,
        title=title,
        subtitle=subtitle,
        body=body,
        keywords=_keyword_values(event.company_name, event.sender_domain, event.classification, event.email_type),
        metadata={
            "application_id": str(event.application_id) if event.application_id else None,
            "thread_id": event.thread_id,
            "classification": event.classification,
            "email_type": event.email_type,
            "company_name": event.company_name,
            "email_id": str(event.id),
        },
        source_updated_at=event.received_at,
    )


def build_radar_report_document(report: ResearchReport) -> SearchDocumentInput:
    structured = report.structured_json if isinstance(report.structured_json, dict) else {}
    body = normalize_search_text([report.summary_markdown, report.diff_summary, structured.get("summary")])
    return SearchDocumentInput(
        user_id=_coerce_user_id(report.user_id, SOURCE_RADAR_REPORT),
        source_type=SOURCE_RADAR_REPORT,
        source_id=report.id,
        title=report.title,
        subtitle=report.status,
        body=body,
        keywords=_keyword_values("Radar", "research report", report.status),
        metadata={
            "profile_id": str(report.profile_id) if report.profile_id else None,
            "run_id": str(report.run_id) if report.run_id else None,
            "report_id": str(report.id),
            "status": report.status,
            "finding_count": report.finding_count,
            "source_count": report.source_count,
            "report_date": report.report_date.isoformat() if report.report_date else None,
        },
        source_updated_at=report.report_date,
    )


def build_search_document(record: Any) -> SearchDocumentInput:
    if isinstance(record, Application):
        return build_application_document(record)
    if isinstance(record, Contact):
        return build_contact_document(record)
    if isinstance(record, EmailEvent):
        return build_email_document(record)
    if isinstance(record, ResearchReport):
        return build_radar_report_document(record)
    raise TypeError(f"Unsupported search document record: {type(record).__name__}")
