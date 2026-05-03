"""Artifact lineage helpers for generated AI outputs."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AiArtifact
from backend.services.ai_usage import sanitize_metadata


def _coerce_uuid(value: uuid.UUID | str | None) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


async def record_ai_artifact(
    db: AsyncSession,
    *,
    artifact_type: str,
    user_id: uuid.UUID | str | None = None,
    model_call_id: uuid.UUID | str | None = None,
    artifact_ref_id: uuid.UUID | str | None = None,
    title: str | None = None,
    path: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AiArtifact:
    artifact = AiArtifact(
        user_id=_coerce_uuid(user_id),
        model_call_id=_coerce_uuid(model_call_id),
        artifact_type=artifact_type,
        artifact_ref_id=_coerce_uuid(artifact_ref_id),
        title=title,
        path=path,
        metadata_json=sanitize_metadata(metadata),
    )
    db.add(artifact)
    await db.flush()
    return artifact
