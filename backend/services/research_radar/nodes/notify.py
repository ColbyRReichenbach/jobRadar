from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from backend.services.action_candidates import build_action_dedupe_key, fingerprint_from_parts
from backend.services.alerts import create_user_alert


def _alert_action_url(path: str, **params: str | None) -> str:
    clean_params = {key: value for key, value in params.items() if value}
    query = urlencode(clean_params)
    return f"{path}?{query}" if query else path


async def emit_alerts(state):
    db = state["db"]
    final_report = state.get("final_report", {})
    report_id = state.get("report_id")
    if report_id and final_report.get("status") == "published":
        await create_user_alert(
            db,
            user_id=state["user_id"],
            alert_type="research_report_ready",
            title=f"Radar report ready: {state['tracker']['name']}",
            body=final_report.get("summary_markdown"),
            action_url=_alert_action_url("/radar", profile_id=str(state["profile_id"]), report_id=report_id),
            dedupe_key=build_action_dedupe_key(
                user_id=state["user_id"],
                action_type="notify:research_report_ready",
                target_entity_type="research_report",
                target_fingerprint=fingerprint_from_parts("research_report", report_id),
            ),
        )
    return {}


async def schedule_next_run(state):
    db = state["db"]
    from backend.models import ResearchProfile

    profile = await db.get(ResearchProfile, state["profile_id"])
    if not profile or profile.frequency == "manual":
        return {"next_run_at": None}

    now = datetime.now(timezone.utc)
    if profile.frequency == "daily":
        profile.next_run_at = now + timedelta(days=1)
    elif profile.frequency == "weekly":
        profile.next_run_at = now + timedelta(days=7)
    elif profile.frequency == "biweekly":
        profile.next_run_at = now + timedelta(days=14)
    elif profile.frequency == "monthly":
        profile.next_run_at = now + timedelta(days=30)
    return {"next_run_at": profile.next_run_at.isoformat() if profile.next_run_at else None}
