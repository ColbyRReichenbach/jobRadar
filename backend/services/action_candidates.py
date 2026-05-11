"""Shared action-candidate scaffolding for AI-derived user actions."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import ActionCandidate


ACTION_CANDIDATE_STATUSES = {
    "proposed",
    "suppressed_duplicate",
    "linked_existing",
    "pending_review",
    "accepted",
    "dismissed",
    "expired",
    "failed_validation",
}

ACTION_POLICY_DECISIONS = {
    "propose",
    "require_review",
    "suppress_duplicate",
    "link_existing",
    "reject",
}

TERMINAL_ACTION_CANDIDATE_STATUSES = {
    "accepted",
    "dismissed",
    "expired",
    "failed_validation",
    "linked_existing",
}


@dataclass(frozen=True)
class ActionCandidateSpec:
    user_id: uuid.UUID
    source_type: str
    source_id: str
    action_type: str
    target_entity_type: str
    target_fingerprint: str
    target_entity_id: str | None = None
    dedupe_key: str | None = None
    duplicate_type: str = "none"
    duplicate_matches_json: list[dict[str, Any]] | None = None
    policy_decision: str | None = None
    status: str | None = None
    confidence: float | None = None
    requires_confirmation: bool = True
    evidence_json: dict[str, Any] | None = None
    allow_terminal_status_overwrite: bool = False


def _stable_part(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def short_hash(value: object, *, length: int = 16) -> str:
    return sha256(_stable_part(value).encode("utf-8")).hexdigest()[:length]


def fingerprint_from_parts(kind: str, *parts: object, hash_value: bool = False) -> str:
    normalized = "|".join(_stable_part(part) for part in parts if _stable_part(part))
    if not normalized:
        normalized = "unknown"
    value = short_hash(normalized) if hash_value else normalized
    return f"{_stable_part(kind)}:{value}"


def build_action_dedupe_key(
    *,
    user_id: uuid.UUID | str,
    action_type: str,
    target_entity_type: str,
    target_fingerprint: str,
) -> str:
    return ":".join(
        [
            str(user_id),
            _stable_part(action_type),
            _stable_part(target_entity_type),
            _stable_part(target_fingerprint),
        ]
    )


def status_for_duplicate_type(duplicate_type: str) -> str:
    if duplicate_type == "hard":
        return "suppressed_duplicate"
    if duplicate_type == "soft":
        return "pending_review"
    return "proposed"


def policy_for_duplicate_type(duplicate_type: str) -> str:
    if duplicate_type == "hard":
        return "suppress_duplicate"
    if duplicate_type == "soft":
        return "require_review"
    return "propose"


async def create_or_update_action_candidate(
    db: AsyncSession,
    spec: ActionCandidateSpec,
) -> ActionCandidate:
    dedupe_key = spec.dedupe_key or build_action_dedupe_key(
        user_id=spec.user_id,
        action_type=spec.action_type,
        target_entity_type=spec.target_entity_type,
        target_fingerprint=spec.target_fingerprint,
    )
    duplicate_type = spec.duplicate_type or "none"
    status = spec.status or status_for_duplicate_type(duplicate_type)
    policy_decision = spec.policy_decision or policy_for_duplicate_type(duplicate_type)
    if status not in ACTION_CANDIDATE_STATUSES:
        raise ValueError(f"Unsupported action candidate status: {status}")
    if policy_decision not in ACTION_POLICY_DECISIONS:
        raise ValueError(f"Unsupported action policy decision: {policy_decision}")

    existing = (
        await db.execute(
            select(ActionCandidate).where(
                ActionCandidate.user_id == spec.user_id,
                ActionCandidate.source_type == spec.source_type,
                ActionCandidate.source_id == str(spec.source_id),
                ActionCandidate.action_type == spec.action_type,
                ActionCandidate.dedupe_key == dedupe_key,
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.target_entity_type = spec.target_entity_type
        existing.target_entity_id = spec.target_entity_id
        existing.target_fingerprint = spec.target_fingerprint
        existing.duplicate_type = duplicate_type
        existing.duplicate_matches_json = spec.duplicate_matches_json
        existing.confidence = spec.confidence
        if spec.allow_terminal_status_overwrite or existing.status not in TERMINAL_ACTION_CANDIDATE_STATUSES:
            existing.policy_decision = policy_decision
            existing.status = status
            existing.requires_confirmation = spec.requires_confirmation
            existing.evidence_json = spec.evidence_json
        existing.updated_at = datetime.now(timezone.utc)
        return existing

    candidate = ActionCandidate(
        user_id=spec.user_id,
        source_type=spec.source_type,
        source_id=str(spec.source_id),
        action_type=spec.action_type,
        target_entity_type=spec.target_entity_type,
        target_entity_id=spec.target_entity_id,
        target_fingerprint=spec.target_fingerprint,
        dedupe_key=dedupe_key,
        duplicate_type=duplicate_type,
        duplicate_matches_json=spec.duplicate_matches_json,
        policy_decision=policy_decision,
        status=status,
        confidence=spec.confidence,
        requires_confirmation=spec.requires_confirmation,
        evidence_json=spec.evidence_json,
    )
    db.add(candidate)
    await db.flush()
    return candidate
