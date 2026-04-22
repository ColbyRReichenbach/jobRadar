from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse
import uuid as _uuid

from sqlalchemy import select

from backend.models import Company, RecommendedAction, ResearchEvidenceItem, ResearchReport, ResearchReportSection, ResearchRun


async def persist_report_node(state):
    db = state["db"]
    run = (
        await db.execute(select(ResearchRun).where(ResearchRun.id == state["run_id"]))
    ).scalars().first()
    if not run:
        raise RuntimeError("Research run could not be loaded during report persistence.")

    final_report = state["final_report"]
    report = ResearchReport(
        user_id=state["user_id"],
        profile_id=state["profile_id"],
        run_id=run.id,
        report_date=datetime.now(timezone.utc),
        title=final_report["title"],
        summary_markdown=final_report["summary_markdown"],
        structured_json=final_report.get("structured_json", {}),
        diff_summary=final_report.get("diff_summary"),
        status=final_report.get("status", "draft"),
        overall_confidence=final_report.get("overall_confidence"),
        finding_count=final_report.get("finding_count", 0),
        source_count=final_report.get("source_count", 0),
        new_findings_count=final_report.get("new_findings_count", 0),
        changed_findings_count=final_report.get("changed_findings_count", 0),
    )
    db.add(report)
    await db.flush()

    def _to_uuid(value):
        if not value:
            return None
        if isinstance(value, _uuid.UUID):
            return value
        return _uuid.UUID(str(value))

    for section in state.get("report_sections", []):
        db.add(
            ResearchReportSection(
                report_id=report.id,
                section_key=section["section_key"],
                title=section["title"],
                display_order=section["display_order"],
                markdown=section.get("markdown"),
                structured_json=section.get("structured_json", {}),
            )
        )

    for item in state.get("evidence_items", []):
        db.add(
            ResearchEvidenceItem(
                run_id=run.id,
                report_id=report.id,
                user_id=state["user_id"],
                profile_id=state["profile_id"],
                source_item_id=_to_uuid(item.get("source_item_id")),
                evidence_type=item["evidence_type"],
                title=item.get("title"),
                claim=item["claim"],
                snippet=item.get("snippet"),
                url=item.get("url"),
                domain=item.get("domain"),
                company_name=item.get("company_name"),
                role_title=item.get("role_title"),
                confidence=item.get("confidence"),
                relevance_score=item.get("relevance_score"),
                novelty_score=item.get("novelty_score"),
                structured_json={"citation_ids": item.get("citation_ids", []), "supports_objective": item.get("supports_objective", True)},
            )
        )

    for action in state.get("report_actions", []):
        company_id = None
        action_url = action.get("payload", {}).get("source_url")
        if action_url:
            domain = urlparse(action_url).netloc.lower()
            company = (
                await db.execute(select(Company).where(Company.domain == domain))
            ).scalars().first()
            if company:
                company_id = company.id
        payload = dict(action.get("payload", {}))
        payload["report_id"] = str(report.id)
        db.add(
            RecommendedAction(
                user_id=state["user_id"],
                profile_id=state["profile_id"],
                company_id=company_id,
                action_type=action["action_type"],
                title=action["title"],
                body=action.get("body"),
                payload=payload,
                priority=action.get("priority", 50),
            )
        )

    run.report_id = report.id
    run.status = final_report.get("status", "published")
    run.completed_at = datetime.now(timezone.utc)
    await db.flush()

    return {
        "report_id": str(report.id),
        "final_report": {
            **final_report,
            "id": str(report.id),
        },
    }
