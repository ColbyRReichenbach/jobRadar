from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import ApplicationSourceLink, UserApplicationLink
from backend.metrics import observe_private_url_rejected
from backend.services.source_intelligence.link_crypto import (
    encrypt_source_link,
    hash_source_link,
    source_link_encryption_key_version,
)
from backend.services.source_intelligence.url_sanitizer import SanitizedUrl, sanitize_url


PARSER_VERSION = "source-url-v1"


@dataclass(frozen=True)
class StoredApplicationLink:
    user_link: UserApplicationLink
    application_source_link: ApplicationSourceLink | None
    sanitized: SanitizedUrl


def relationship_type_for_link(link_type: str, safe_public: bool) -> str:
    if safe_public:
        return "manual_user_link"
    if link_type == "interview_scheduler":
        return "private_scheduler_link"
    if link_type in {"application_status", "candidate_home", "magic_login", "tracking_redirect"}:
        return "private_status_link"
    if not safe_public and link_type == "unknown":
        return "private_status_link"
    return "manual_user_link"


async def store_user_application_link(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    raw_url: str,
    application_id: uuid.UUID | None = None,
    email_event_id: uuid.UUID | None = None,
    created_from: str = "manual_user_link",
    parser_version: str = PARSER_VERSION,
) -> StoredApplicationLink:
    sanitized = sanitize_url(raw_url)
    classification = sanitized.classification
    if sanitized.sanitization_status != "safe_public":
        for rule_id in classification.rule_ids or ["private_url"]:
            observe_private_url_rejected(rule_id=rule_id)
    raw_hash, raw_hash_version = hash_source_link(raw_url)
    encrypted = None
    encryption_version = None
    if sanitized.sanitization_status != "safe_public":
        encrypted = encrypt_source_link(raw_url)
        encryption_version = source_link_encryption_key_version()

    existing = (
        await db.execute(
            select(UserApplicationLink).where(
                UserApplicationLink.user_id == user_id,
                UserApplicationLink.raw_url_hash == raw_hash,
            )
        )
    ).scalar_one_or_none()

    if existing:
        link = existing
        if application_id and not link.application_id:
            link.application_id = application_id
        if email_event_id and not link.email_event_id:
            link.email_event_id = email_event_id
    else:
        link = UserApplicationLink(
            user_id=user_id,
            application_id=application_id,
            email_event_id=email_event_id,
            raw_url_encrypted=encrypted,
            raw_url_hash=raw_hash,
            raw_url_hash_version=raw_hash_version,
            canonical_public_url=sanitized.canonical_public_url,
            canonical_public_url_hash=sanitized.canonical_public_url_hash,
            canonical_public_url_hash_version=sanitized.canonical_public_url_hash_version,
            link_type=classification.link_type,
            provider_type=classification.provider_type,
            provider_key=classification.provider_key,
            company_domain=_company_domain_from_hostname(classification.hostname),
            contains_private_token=classification.contains_private_token,
            sanitization_status=sanitized.sanitization_status,
            rejection_reason=sanitized.rejection_reason,
            parser_version=parser_version,
            encryption_key_version=encryption_version,
        )
        db.add(link)
        await db.flush()

    app_link = None
    if application_id:
        relationship_type = relationship_type_for_link(
            link.link_type,
            sanitized.sanitization_status == "safe_public",
        )
        app_link = (
            await db.execute(
                select(ApplicationSourceLink).where(
                    ApplicationSourceLink.application_id == application_id,
                    ApplicationSourceLink.user_application_link_id == link.id,
                    ApplicationSourceLink.relationship_type == relationship_type,
                )
            )
        ).scalar_one_or_none()
        if not app_link:
            app_link = ApplicationSourceLink(
                user_id=user_id,
                application_id=application_id,
                user_application_link_id=link.id,
                relationship_type=relationship_type,
                confidence=1.0 if sanitized.sanitization_status == "safe_public" else 0.8,
                created_from=created_from,
            )
            db.add(app_link)
            await db.flush()

    return StoredApplicationLink(user_link=link, application_source_link=app_link, sanitized=sanitized)


async def store_many_user_application_links(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    raw_urls: list[str],
    application_id: uuid.UUID | None = None,
    email_event_id: uuid.UUID | None = None,
    created_from: str,
) -> list[StoredApplicationLink]:
    stored: list[StoredApplicationLink] = []
    seen: set[str] = set()
    for raw_url in raw_urls:
        if raw_url in seen:
            continue
        seen.add(raw_url)
        stored.append(
            await store_user_application_link(
                db,
                user_id=user_id,
                raw_url=raw_url,
                application_id=application_id,
                email_event_id=email_event_id,
                created_from=created_from,
            )
        )
    return stored


def _company_domain_from_hostname(hostname: str | None) -> str | None:
    if not hostname:
        return None
    host = hostname.lower()
    ats_hosts = (
        "greenhouse.io",
        "lever.co",
        "ashbyhq.com",
        "workable.com",
        "smartrecruiters.com",
        "myworkdayjobs.com",
        "myworkdaysite.com",
        "icims.com",
    )
    if any(host == item or host.endswith(f".{item}") for item in ats_hosts):
        return None
    return host.removeprefix("www.")
