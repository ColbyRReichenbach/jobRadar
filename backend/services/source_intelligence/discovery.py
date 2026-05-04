from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import DataConsent, SourceDiscoveryEvent
from backend.metrics import observe_job_source_discovered
from backend.services.job_sources import ashby, greenhouse, icims, lever, smartrecruiters, structured_data, workable, workday
from backend.services.job_sources.base import SourceConfig
from backend.services.job_sources.registry import upsert_company_job_source
from backend.services.source_intelligence.link_store import StoredApplicationLink


_ADAPTERS = (
    greenhouse,
    lever,
    ashby,
    workable,
    smartrecruiters,
    icims,
    workday,
    structured_data,
)


@dataclass(frozen=True)
class SourceDiscoveryResult:
    source_id: uuid.UUID | None
    event_id: uuid.UUID | None
    created_event: bool


async def has_source_intelligence_consent(db: AsyncSession, user_id: uuid.UUID) -> bool:
    return bool(
        (
            await db.execute(
                select(DataConsent.id).where(
                    DataConsent.user_id == user_id,
                    DataConsent.consent_type == "source_intelligence",
                    DataConsent.granted.is_(True),
                )
            )
        ).scalar_one_or_none()
    )


async def process_stored_links_for_source_discovery(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    stored_links: list[StoredApplicationLink],
    discovered_from: str,
) -> list[SourceDiscoveryResult]:
    if not stored_links or not await has_source_intelligence_consent(db, user_id):
        return []
    results: list[SourceDiscoveryResult] = []
    for stored in stored_links:
        result = await process_stored_link_for_source_discovery(
            db,
            user_id=user_id,
            stored_link=stored,
            discovered_from=discovered_from,
        )
        if result:
            results.append(result)
    return results


async def process_stored_link_for_source_discovery(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    stored_link: StoredApplicationLink,
    discovered_from: str,
) -> SourceDiscoveryResult | None:
    sanitized = stored_link.sanitized
    if sanitized.sanitization_status != "safe_public" or not sanitized.canonical_public_url:
        return None
    config = parse_source_config(sanitized.canonical_public_url)
    if not config:
        return None
    source = await upsert_company_job_source(db, config, discovered_from=discovered_from)
    event, created_event = await _upsert_discovery_event(
        db,
        user_id=user_id,
        source_id=source.id,
        stored_link=stored_link,
        config=config,
        discovered_from=discovered_from,
    )
    if created_event:
        observe_job_source_discovered(
            provider_type=config.provider_type,
            discovered_from=discovered_from,
            status=source.verification_status,
        )
        _enqueue_source_verification(source.id)
    return SourceDiscoveryResult(source_id=source.id, event_id=event.id, created_event=created_event)


def parse_source_config(url: str) -> SourceConfig | None:
    for adapter in _ADAPTERS:
        config = adapter.parse_source_from_url(url)
        if config:
            return config
    return None


async def _upsert_discovery_event(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    source_id: uuid.UUID,
    stored_link: StoredApplicationLink,
    config: SourceConfig,
    discovered_from: str,
) -> tuple[SourceDiscoveryEvent, bool]:
    user_link = stored_link.user_link
    event_type = f"{discovered_from}_source_candidate"
    existing = (
        await db.execute(
            select(SourceDiscoveryEvent).where(
                SourceDiscoveryEvent.source_id == source_id,
                SourceDiscoveryEvent.user_id == user_id,
                SourceDiscoveryEvent.email_event_id == user_link.email_event_id,
                SourceDiscoveryEvent.application_id == user_link.application_id,
                SourceDiscoveryEvent.event_type == event_type,
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing, False
    event = SourceDiscoveryEvent(
        source_id=source_id,
        user_id=user_id,
        email_event_id=user_link.email_event_id,
        application_id=user_link.application_id,
        event_type=event_type,
        provider_type=config.provider_type,
        company_domain=config.company_domain,
        confidence_delta=_confidence_delta(config),
        redacted_evidence=_redacted_evidence(stored_link, config, discovered_from),
    )
    db.add(event)
    await db.flush()
    return event, True


def _confidence_delta(config: SourceConfig) -> float:
    if config.verification_status == "pending" and config.access_mode == "public":
        return 0.15
    if config.verification_status == "needs_review":
        return 0.05
    return 0.1


def _redacted_evidence(stored_link: StoredApplicationLink, config: SourceConfig, discovered_from: str) -> dict:
    classification = stored_link.sanitized.classification
    return {
        "discovered_from": _clean(discovered_from),
        "provider_type": _clean(config.provider_type),
        "provider_key_hashable_public": bool(config.provider_key),
        "hostname": _clean(classification.hostname),
        "link_type": _clean(classification.link_type),
        "sanitization_status": _clean(stored_link.sanitized.sanitization_status),
        "rule_ids": [_clean(rule_id) for rule_id in classification.rule_ids],
        "parser_version": _clean(stored_link.user_link.parser_version),
    }


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    return str(value).replace("\r", " ").replace("\n", " ")[:160]


def _enqueue_source_verification(source_id: uuid.UUID) -> None:
    if os.getenv("TESTING") == "1":
        return
    try:
        from backend.tasks.verify_job_sources import verify_source_by_id

        verify_source_by_id.delay(str(source_id))
    except Exception:
        return
