from __future__ import annotations

from typing import Any, TypedDict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


class ResearchRadarState(TypedDict, total=False):
    db: AsyncSession
    run_id: UUID
    profile_id: UUID
    user_id: UUID
    mode: str
    trigger: str
    tracker: dict[str, Any]
    user_context: dict[str, Any]
    normalized_brief: dict[str, Any]
    research_plan: dict[str, Any]
    search_tasks: list[dict[str, Any]]
    source_items: list[dict[str, Any]]
    evidence_items: list[dict[str, Any]]
    diff_summary: dict[str, Any]
    report_sections: list[dict[str, Any]]
    report_actions: list[dict[str, Any]]
    verification_result: dict[str, Any]
    final_report: dict[str, Any]
    step_metrics: dict[str, Any]
    errors: list[str]
    report_id: str | None
