from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse
import uuid as _uuid

from sqlalchemy import select

from backend.models import Company, RecommendedAction, ResearchEvidenceItem, ResearchReport, ResearchReportSection, ResearchRun
from backend.services.action_candidates import ActionCandidateSpec, create_or_update_action_candidate
from backend.services.dedupe_gate import evaluate_action_dedupe
from backend.services.research_radar.lineage import record_radar_report_artifact
from backend.services.search.indexer import index_record


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
    report.structured_json = {
        **(report.structured_json or {}),
        "diff": state.get("diff_summary", {}),
        "evidence_keys": state.get("diff_summary", {}).get("all_keys", []),
        "evidence_index": state.get("diff_summary", {}).get("evidence_index", {}),
    }
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
        dedupe_decision = await evaluate_action_dedupe(
            db,
            user_id=state["user_id"],
            action_type="review_radar_opportunity",
            payload={
                **payload,
                "profile_id": state["profile_id"],
                "signal_id": action.get("signal_id") or payload.get("signal_id"),
                "title": action["title"],
                "source_url": action_url,
                "recommended_action_type": action["action_type"],
            },
        )
        candidate = await create_or_update_action_candidate(
            db,
            ActionCandidateSpec(
                user_id=state["user_id"],
                source_type="research_report",
                source_id=str(report.id),
                action_type="review_radar_opportunity",
                target_entity_type=dedupe_decision.target_entity_type,
                target_entity_id=str(action.get("signal_id") or payload.get("signal_id")) if action.get("signal_id") or payload.get("signal_id") else None,
                target_fingerprint=dedupe_decision.target_fingerprint,
                dedupe_key=dedupe_decision.dedupe_key,
                duplicate_type=dedupe_decision.duplicate_type,
                duplicate_matches_json=dedupe_decision.matches,
                policy_decision=dedupe_decision.policy_decision,
                confidence=report.overall_confidence,
                requires_confirmation=True,
                evidence_json={
                    "report_id": str(report.id),
                    "run_id": str(run.id),
                    "action_title": action["title"],
                    "payload": payload,
                },
            ),
        )
        if dedupe_decision.duplicate_type == "hard":
            continue
        db.add(
            RecommendedAction(
                user_id=state["user_id"],
                action_candidate_id=candidate.id,
                profile_id=state["profile_id"],
                company_id=company_id,
                action_type=action["action_type"],
                title=action["title"],
                body=action.get("body"),
                payload=payload,
                dedupe_key=dedupe_decision.dedupe_key,
                duplicate_reason=dedupe_decision.reason,
                duplicate_matches_json=dedupe_decision.matches,
                priority=action.get("priority", 50),
            )
        )

    run.report_id = report.id
    run.status = final_report.get("status", "published")
    run.completed_at = datetime.now(timezone.utc)
    await index_record(db, report)
    await record_radar_report_artifact(db, report=report, run=run)
    await db.flush()

    return {
        "report_id": str(report.id),
        "final_report": {
            **final_report,
            "id": str(report.id),
        },
    }
