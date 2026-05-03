from __future__ import annotations

from backend.services.research_radar.schemas import ReportActionDraft


async def derive_report_actions(state):
    actions: list[dict] = []
    for item in state.get("evidence_items", [])[:5]:
        action_type = "research_company"
        title = f"Review {item.get('company_name') or 'company'} signal"
        body = item.get("claim")
        if item.get("evidence_type") == "role_opening":
            action_type = "review_role"
            title = f"Review role: {item.get('role_title') or item.get('title') or 'New opportunity'}"
        elif item.get("company_name"):
            title = f"Research {item['company_name']}"

        draft = ReportActionDraft(
            action_type=action_type,
            title=title,
            body=body,
            priority=80 if item.get("relevance_score", 0.0) >= 0.7 else 60,
            payload={
                "report_id": state.get("report_id"),
                "source_evidence_ids": [item.get("source_item_id")] if item.get("source_item_id") else [],
                "source_url": item.get("url"),
            },
        )
        actions.append(draft.model_dump())
    return {"report_actions": actions}
