"""Shared duplicate-decision gate for action candidates."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (
    Application,
    Contact,
    ContactDistinctDecision,
    Interview,
    RecommendedAction,
)
from backend.services.action_candidates import build_action_dedupe_key, fingerprint_from_parts
from backend.services.source_intelligence.url_sanitizer import sanitize_public_job_url


SUPPORTED_ACTION_TYPES = {
    "add_job_to_pipeline",
    "add_network_contact",
    "schedule_interview",
    "review_radar_opportunity",
}


@dataclass(frozen=True)
class DedupeDecision:
    action_type: str
    target_entity_type: str
    target_fingerprint: str
    dedupe_key: str
    duplicate_type: str
    reason: str | None
    matches: list[dict[str, Any]]

    @property
    def policy_decision(self) -> str:
        if self.duplicate_type == "hard":
            return "suppress_duplicate"
        if self.duplicate_type == "soft":
            return "require_review"
        return "propose"


def _normalize_match_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _normalize_contact_email(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _sorted_contact_email_pair(email_a: str | None, email_b: str | None) -> tuple[str, str] | None:
    normalized_a = _normalize_contact_email(email_a)
    normalized_b = _normalize_contact_email(email_b)
    if not normalized_a or not normalized_b or normalized_a == normalized_b:
        return None
    return tuple(sorted((normalized_a, normalized_b)))


def _iso(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _uuid_text(value: object) -> str | None:
    if not value:
        return None
    return str(value)


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        from dateutil import parser as dateparser

        return dateparser.parse(text)
    except (ValueError, TypeError):
        return None


def _application_match(app: Application) -> dict[str, Any]:
    return {
        "entity_type": "application",
        "id": str(app.id),
        "company": app.company,
        "role_title": app.role_title,
        "location": app.location,
        "job_url": app.job_url,
        "status": app.status,
    }


def _contact_match(contact: Contact) -> dict[str, Any]:
    return {
        "entity_type": "contact",
        "id": str(contact.id),
        "name": contact.name,
        "email": contact.email,
        "company_name": contact.company_name,
        "title": contact.title,
    }


def _interview_match(interview: Interview) -> dict[str, Any]:
    return {
        "entity_type": "interview",
        "id": str(interview.id),
        "application_id": str(interview.application_id) if interview.application_id else None,
        "scheduled_at": _iso(interview.scheduled_at),
        "interviewer_email": interview.interviewer_email,
        "interviewer_name": interview.interviewer_name,
        "interview_type": interview.interview_type,
    }


def _recommended_action_match(action: RecommendedAction) -> dict[str, Any]:
    return {
        "entity_type": "recommended_action",
        "id": str(action.id),
        "profile_id": str(action.profile_id) if action.profile_id else None,
        "signal_id": str(action.signal_id) if action.signal_id else None,
        "action_type": action.action_type,
        "title": action.title,
        "status": action.status,
        "dedupe_key": action.dedupe_key,
    }


def _decision(
    *,
    user_id: uuid.UUID,
    action_type: str,
    target_entity_type: str,
    target_fingerprint: str,
    duplicate_type: str,
    reason: str | None,
    matches: list[dict[str, Any]] | None = None,
) -> DedupeDecision:
    return DedupeDecision(
        action_type=action_type,
        target_entity_type=target_entity_type,
        target_fingerprint=target_fingerprint,
        dedupe_key=build_action_dedupe_key(
            user_id=user_id,
            action_type=action_type,
            target_entity_type=target_entity_type,
            target_fingerprint=target_fingerprint,
        ),
        duplicate_type=duplicate_type,
        reason=reason,
        matches=matches or [],
    )


async def evaluate_action_dedupe(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    action_type: str,
    payload: dict[str, Any],
) -> DedupeDecision:
    if action_type == "add_job_to_pipeline":
        return await _dedupe_job(db, user_id=user_id, payload=payload)
    if action_type == "add_network_contact":
        return await _dedupe_contact(db, user_id=user_id, payload=payload)
    if action_type == "schedule_interview":
        return await _dedupe_interview(db, user_id=user_id, payload=payload)
    if action_type == "review_radar_opportunity":
        return await _dedupe_radar_opportunity(db, user_id=user_id, payload=payload)
    raise ValueError(f"Unsupported dedupe action type: {action_type}")


class DedupeGate:
    async def evaluate(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        action_type: str,
        payload: dict[str, Any],
    ) -> DedupeDecision:
        return await evaluate_action_dedupe(db, user_id=user_id, action_type=action_type, payload=payload)


async def _dedupe_job(db: AsyncSession, *, user_id: uuid.UUID, payload: dict[str, Any]) -> DedupeDecision:
    normalized_job_url = sanitize_public_job_url(payload.get("job_url"))
    target_fingerprint = (
        fingerprint_from_parts("job_url", normalized_job_url, hash_value=True)
        if normalized_job_url
        else fingerprint_from_parts(
            "company_role_location",
            payload.get("company"),
            payload.get("role_title"),
            payload.get("location"),
        )
    )
    result = await db.execute(
        select(Application).where(
            Application.user_id == user_id,
            Application.job_url.is_not(None),
        )
    )
    apps = list(result.scalars().all())
    if normalized_job_url:
        for app_row in apps:
            if sanitize_public_job_url(app_row.job_url) == normalized_job_url:
                return _decision(
                    user_id=user_id,
                    action_type="add_job_to_pipeline",
                    target_entity_type="application",
                    target_fingerprint=target_fingerprint,
                    duplicate_type="hard",
                    reason="job_url_already_tracked",
                    matches=[_application_match(app_row)],
                )

    company_key = _normalize_match_text(payload.get("company"))
    role_key = _normalize_match_text(payload.get("role_title"))
    location_key = _normalize_match_text(payload.get("location"))
    soft_matches = []
    all_apps_result = await db.execute(select(Application).where(Application.user_id == user_id))
    for app_row in all_apps_result.scalars().all():
        if _normalize_match_text(app_row.company) != company_key:
            continue
        if _normalize_match_text(app_row.role_title) != role_key:
            continue
        if location_key and _normalize_match_text(app_row.location) not in {"", location_key}:
            continue
        soft_matches.append(_application_match(app_row))
    if soft_matches:
        return _decision(
            user_id=user_id,
            action_type="add_job_to_pipeline",
            target_entity_type="application",
            target_fingerprint=target_fingerprint,
            duplicate_type="soft",
            reason="same_company_role_location",
            matches=soft_matches[:5],
        )
    return _decision(
        user_id=user_id,
        action_type="add_job_to_pipeline",
        target_entity_type="application",
        target_fingerprint=target_fingerprint,
        duplicate_type="none",
        reason=None,
    )


async def _dedupe_contact(db: AsyncSession, *, user_id: uuid.UUID, payload: dict[str, Any]) -> DedupeDecision:
    exclude_contact_id = uuid.UUID(str(payload["contact_id"])) if payload.get("contact_id") else None
    email_value = _normalize_contact_email(payload.get("email"))
    normalized_name = _normalize_match_text(payload.get("name"))
    target_fingerprint = (
        fingerprint_from_parts("email", email_value)
        if email_value
        else fingerprint_from_parts("name", normalized_name)
    )

    separate_pairs_result = await db.execute(
        select(ContactDistinctDecision.email_a, ContactDistinctDecision.email_b).where(
            ContactDistinctDecision.user_id == user_id
        )
    )
    separate_pairs = {
        tuple(sorted((email_a, email_b)))
        for email_a, email_b in separate_pairs_result.all()
        if email_a and email_b
    }

    result = await db.execute(select(Contact).where(Contact.user_id == user_id))
    hard_matches = []
    soft_matches = []
    for contact in result.scalars().all():
        if exclude_contact_id and contact.id == exclude_contact_id:
            continue
        contact_email = _normalize_contact_email(contact.email)
        if email_value and contact_email == email_value:
            hard_matches.append(_contact_match(contact))
            continue
        if normalized_name and _normalize_match_text(contact.name) == normalized_name:
            decision_pair = _sorted_contact_email_pair(email_value, contact_email)
            if decision_pair and decision_pair in separate_pairs:
                continue
            soft_matches.append(_contact_match(contact))

    if hard_matches:
        return _decision(
            user_id=user_id,
            action_type="add_network_contact",
            target_entity_type="contact",
            target_fingerprint=target_fingerprint,
            duplicate_type="hard",
            reason="contact_email_already_exists",
            matches=hard_matches[:5],
        )
    if soft_matches:
        return _decision(
            user_id=user_id,
            action_type="add_network_contact",
            target_entity_type="contact",
            target_fingerprint=target_fingerprint,
            duplicate_type="soft",
            reason="same_contact_name",
            matches=soft_matches[:5],
        )
    return _decision(
        user_id=user_id,
        action_type="add_network_contact",
        target_entity_type="contact",
        target_fingerprint=target_fingerprint,
        duplicate_type="none",
        reason=None,
    )


async def _dedupe_interview(db: AsyncSession, *, user_id: uuid.UUID, payload: dict[str, Any]) -> DedupeDecision:
    scheduled_at = _parse_datetime(payload.get("scheduled_at"))
    interviewer_email = _normalize_contact_email(payload.get("interviewer_email"))
    application_id = _uuid_text(payload.get("application_id"))
    exclude_interview_id = uuid.UUID(str(payload["exclude_interview_id"])) if payload.get("exclude_interview_id") else None
    target_fingerprint = fingerprint_from_parts("interview", application_id, _iso(scheduled_at), interviewer_email)
    if scheduled_at and interviewer_email:
        conditions = [
            Interview.user_id == user_id,
            Interview.scheduled_at == scheduled_at,
            Interview.interviewer_email == interviewer_email,
        ]
        if exclude_interview_id:
            conditions.append(Interview.id != exclude_interview_id)
        hard = (
            await db.execute(
                select(Interview).where(*conditions)
            )
        ).scalar_one_or_none()
        if hard:
            return _decision(
                user_id=user_id,
                action_type="schedule_interview",
                target_entity_type="interview",
                target_fingerprint=target_fingerprint,
                duplicate_type="hard",
                reason="same_time_and_interviewer",
                matches=[_interview_match(hard)],
            )

    if scheduled_at and application_id:
        conditions = [
            Interview.user_id == user_id,
            Interview.application_id == uuid.UUID(application_id),
            Interview.scheduled_at == scheduled_at,
        ]
        if exclude_interview_id:
            conditions.append(Interview.id != exclude_interview_id)
        result = await db.execute(
            select(Interview).where(*conditions)
        )
        soft_matches = [_interview_match(row) for row in result.scalars().all()]
        if soft_matches:
            return _decision(
                user_id=user_id,
                action_type="schedule_interview",
                target_entity_type="interview",
                target_fingerprint=target_fingerprint,
                duplicate_type="soft",
                reason="same_application_and_time",
                matches=soft_matches[:5],
            )

    return _decision(
        user_id=user_id,
        action_type="schedule_interview",
        target_entity_type="interview",
        target_fingerprint=target_fingerprint,
        duplicate_type="none",
        reason=None,
    )


async def _dedupe_radar_opportunity(db: AsyncSession, *, user_id: uuid.UUID, payload: dict[str, Any]) -> DedupeDecision:
    signal_id = _uuid_text(payload.get("signal_id"))
    source_url = payload.get("source_url")
    if signal_id:
        target_fingerprint = fingerprint_from_parts("signal", signal_id)
    elif source_url:
        target_fingerprint = fingerprint_from_parts("source_url", source_url, hash_value=True)
    else:
        target_fingerprint = fingerprint_from_parts(
            "profile_topic_week",
            payload.get("profile_id"),
            payload.get("title"),
            payload.get("week_bucket"),
            hash_value=True,
        )
    decision = _decision(
        user_id=user_id,
        action_type="review_radar_opportunity",
        target_entity_type="radar_opportunity",
        target_fingerprint=target_fingerprint,
        duplicate_type="none",
        reason=None,
    )

    existing_by_key = list(
        (
            await db.execute(
                select(RecommendedAction).where(
                    RecommendedAction.user_id == user_id,
                    RecommendedAction.dedupe_key == decision.dedupe_key,
                )
            )
        ).scalars().all()
    )
    if existing_by_key:
        return _decision(
            user_id=user_id,
            action_type="review_radar_opportunity",
            target_entity_type="radar_opportunity",
            target_fingerprint=target_fingerprint,
            duplicate_type="hard",
            reason="recommended_action_dedupe_key_exists",
            matches=[_recommended_action_match(item) for item in existing_by_key[:5]],
        )

    profile_id = payload.get("profile_id")
    title_key = _normalize_match_text(payload.get("title"))
    if profile_id and title_key:
        result = await db.execute(
            select(RecommendedAction).where(
                RecommendedAction.user_id == user_id,
                RecommendedAction.profile_id == uuid.UUID(str(profile_id)),
                RecommendedAction.action_type == payload.get("recommended_action_type", "review_opportunity"),
            )
        )
        soft_matches = [
            _recommended_action_match(action)
            for action in result.scalars().all()
            if _normalize_match_text(action.title) == title_key
        ]
        if soft_matches:
            return _decision(
                user_id=user_id,
                action_type="review_radar_opportunity",
                target_entity_type="radar_opportunity",
                target_fingerprint=target_fingerprint,
                duplicate_type="soft",
                reason="same_radar_profile_and_title",
                matches=soft_matches[:5],
            )

    return decision
