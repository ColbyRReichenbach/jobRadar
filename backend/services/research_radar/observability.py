from __future__ import annotations

import importlib
import logging
import os
from datetime import datetime, timezone
from typing import Any


logger = logging.getLogger(__name__)

_LANGSMITH_IMPORT_FAILED = False
_LANGSMITH_CLIENT = None


def _isoformat(value: Any) -> str | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value) if value else None


def _unique_strings(values: list[str] | None, *, limit: int = 8) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        stripped = str(value).strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(stripped)
        if len(cleaned) >= limit:
            break
    return cleaned


def sanitize_tracker_snapshot(tracker: dict[str, Any] | None) -> dict[str, Any]:
    tracker = tracker or {}
    return {
        "id": tracker.get("id"),
        "name": tracker.get("name"),
        "objective": tracker.get("objective"),
        "mode": tracker.get("mode"),
        "frequency": tracker.get("frequency"),
        "depth": tracker.get("depth"),
        "minimum_score": tracker.get("minimum_score"),
        "selected_domains": _unique_strings(tracker.get("selected_domains")),
        "selected_roles": _unique_strings(tracker.get("selected_roles")),
        "selected_companies": _unique_strings(tracker.get("selected_companies"), limit=10),
        "keywords": _unique_strings(tracker.get("keywords")),
        "excluded_keywords": _unique_strings(tracker.get("excluded_keywords")),
        "source_types": _unique_strings(tracker.get("source_types")),
        "target_locations": _unique_strings(tracker.get("target_locations")),
        "remote_types": _unique_strings(tracker.get("remote_types")),
        "seniority_levels": _unique_strings(tracker.get("seniority_levels")),
        "research_source_scopes": _unique_strings(tracker.get("research_source_scopes")),
        "use_profile_context": bool(tracker.get("use_profile_context", False)),
        "include_public_web_research": bool(tracker.get("include_public_web_research", False)),
        "max_search_queries": tracker.get("max_search_queries"),
        "max_sources_per_run": tracker.get("max_sources_per_run"),
        "report_prompt_notes": tracker.get("report_prompt_notes"),
    }


def sanitize_user_context(user_context: dict[str, Any] | None) -> dict[str, Any]:
    user_context = user_context or {}
    previous_report = user_context.get("previous_report") or {}
    return {
        "name": user_context.get("name"),
        "email": user_context.get("email"),
        "preferred_locations": _unique_strings(user_context.get("preferred_locations")),
        "preferred_remote_type": user_context.get("preferred_remote_type"),
        "target_salary_min": user_context.get("target_salary_min"),
        "target_salary_max": user_context.get("target_salary_max"),
        "skills": _unique_strings(user_context.get("skills"), limit=10),
        "tools": _unique_strings(user_context.get("tools"), limit=10),
        "certifications": _unique_strings(user_context.get("certifications"), limit=6),
        "experience_years": user_context.get("experience_years"),
        "role_interest_labels": _unique_strings(user_context.get("role_interest_labels"), limit=8),
        "recent_applications": [
            {
                "company": item.get("company"),
                "role_title": item.get("role_title"),
                "status": item.get("status"),
                "applied_at": item.get("applied_at"),
            }
            for item in (user_context.get("recent_applications") or [])[:5]
        ],
        "company_visits": [
            {
                "domain": item.get("domain"),
                "url": item.get("url"),
                "visit_count": item.get("visit_count"),
                "last_visited_at": item.get("last_visited_at"),
            }
            for item in (user_context.get("company_visits") or [])[:5]
        ],
        "previous_report": {
            "id": previous_report.get("id"),
            "title": previous_report.get("title"),
            "report_date": previous_report.get("report_date"),
        }
        if previous_report
        else None,
    }


def summarize_search_tasks(tasks: list[dict[str, Any]] | None, *, include_candidates: bool) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for task in (tasks or [])[:10]:
        entry = {
            "task_id": task.get("task_id"),
            "task_type": task.get("task_type"),
            "query": task.get("query"),
            "company_hint": task.get("company_hint"),
            "role_hint": task.get("role_hint"),
            "expected_signal_type": task.get("expected_signal_type"),
            "priority": task.get("priority"),
            "max_results": task.get("max_results"),
        }
        candidates = task.get("candidates") or []
        entry["candidate_count"] = len(candidates)
        if include_candidates:
            entry["candidates"] = [
                {
                    "url": candidate.get("url"),
                    "title": candidate.get("title"),
                    "source_type": candidate.get("source_type"),
                    "domain": candidate.get("domain"),
                    "published_at": candidate.get("published_at"),
                    "why_selected": candidate.get("why_selected"),
                }
                for candidate in candidates[:5]
            ]
        summaries.append(entry)
    return summaries


def summarize_source_items(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [
        {
            "source_item_id": str(item.get("source_item_id")) if item.get("source_item_id") else None,
            "source_url": item.get("source_url"),
            "title": item.get("title"),
            "source_type": item.get("source_type"),
            "domain": item.get("domain"),
            "published_at": item.get("published_at"),
            "company_name": item.get("company_name"),
            "role_title": item.get("role_title"),
            "fetch_error": item.get("fetch_error"),
        }
        for item in (items or [])[:10]
    ]


def summarize_evidence_items(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [
        {
            "source_item_id": item.get("source_item_id"),
            "evidence_type": item.get("evidence_type"),
            "title": item.get("title"),
            "claim": item.get("claim"),
            "url": item.get("url"),
            "domain": item.get("domain"),
            "company_name": item.get("company_name"),
            "role_title": item.get("role_title"),
            "confidence": item.get("confidence"),
            "relevance_score": item.get("relevance_score"),
            "novelty_score": item.get("novelty_score"),
            "supports_objective": item.get("supports_objective"),
        }
        for item in (items or [])[:10]
    ]


def summarize_report_sections(sections: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [
        {
            "section_key": section.get("section_key"),
            "title": section.get("title"),
            "display_order": section.get("display_order"),
            "citation_ids": (section.get("structured_json") or {}).get("citation_ids", [])[:10],
        }
        for section in (sections or [])[:10]
    ]


def summarize_report_actions(actions: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [
        {
            "action_type": action.get("action_type"),
            "title": action.get("title"),
            "priority": action.get("priority"),
            "source_url": (action.get("payload") or {}).get("source_url"),
        }
        for action in (actions or [])[:10]
    ]


def summarize_final_report(report: dict[str, Any] | None) -> dict[str, Any]:
    report = report or {}
    return {
        "id": report.get("id"),
        "title": report.get("title"),
        "status": report.get("status"),
        "overall_confidence": report.get("overall_confidence"),
        "finding_count": report.get("finding_count"),
        "source_count": report.get("source_count"),
        "new_findings_count": report.get("new_findings_count"),
        "changed_findings_count": report.get("changed_findings_count"),
        "diff_summary": report.get("diff_summary"),
    }


def extract_llm_calls(result: dict[str, Any]) -> list[dict[str, Any]]:
    llm_calls = result.pop("_llm_calls", [])
    if not isinstance(llm_calls, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for item in llm_calls:
        if not isinstance(item, dict):
            continue
        cleaned.append(
            {
                "task": item.get("task"),
                "model": item.get("model"),
                "prompt_version": item.get("prompt_version"),
                "duration_ms": item.get("duration_ms"),
                "retries": item.get("retries"),
                "tokens_in": item.get("tokens_in"),
                "tokens_out": item.get("tokens_out"),
                "cost_estimate_cents": item.get("cost_estimate_cents"),
            }
        )
    return cleaned


def build_step_input_snapshot(step_name: str, state: dict[str, Any]) -> dict[str, Any]:
    tracker = sanitize_tracker_snapshot(state.get("tracker"))
    user_context = sanitize_user_context(state.get("user_context"))
    if step_name == "load_tracker_context":
        return {
            "profile_id": str(state.get("profile_id")) if state.get("profile_id") else None,
            "user_id": str(state.get("user_id")) if state.get("user_id") else None,
            "mode": state.get("mode"),
            "trigger": state.get("trigger"),
        }
    if step_name == "normalize_research_brief":
        return {"tracker": tracker, "user_context": user_context}
    if step_name == "validate_brief":
        return {
            "tracker": tracker,
            "normalized_brief": state.get("normalized_brief") or {},
        }
    if step_name == "plan_research_tasks":
        return {
            "tracker": {"depth": tracker.get("depth"), "max_search_queries": tracker.get("max_search_queries")},
            "normalized_brief": state.get("normalized_brief") or {},
        }
    if step_name == "run_search_tasks":
        return {"search_tasks": summarize_search_tasks(state.get("search_tasks"), include_candidates=False)}
    if step_name == "fetch_documents":
        return {"search_tasks": summarize_search_tasks(state.get("search_tasks"), include_candidates=True)}
    if step_name == "extract_evidence":
        return {
            "normalized_brief": state.get("normalized_brief") or {},
            "source_items": summarize_source_items(state.get("source_items")),
        }
    if step_name == "dedupe_and_rank_evidence":
        return {"evidence_items": summarize_evidence_items(state.get("evidence_items"))}
    if step_name == "build_report_diff":
        return {
            "evidence_items": summarize_evidence_items(state.get("evidence_items")),
            "previous_report": user_context.get("previous_report"),
        }
    if step_name == "write_report":
        return {
            "normalized_brief": state.get("normalized_brief") or {},
            "diff_summary": state.get("diff_summary") or {},
            "evidence_items": summarize_evidence_items(state.get("evidence_items")),
        }
    if step_name == "derive_report_actions":
        return {"evidence_items": summarize_evidence_items(state.get("evidence_items"))}
    if step_name == "verify_report":
        return {
            "report_sections": summarize_report_sections(state.get("report_sections")),
            "evidence_items": summarize_evidence_items(state.get("evidence_items")),
        }
    if step_name == "persist_report":
        return {
            "final_report": summarize_final_report(state.get("final_report")),
            "report_sections": summarize_report_sections(state.get("report_sections")),
            "evidence_items": summarize_evidence_items(state.get("evidence_items")),
            "report_actions": summarize_report_actions(state.get("report_actions")),
        }
    if step_name == "emit_alerts":
        return {
            "profile_id": str(state.get("profile_id")) if state.get("profile_id") else None,
            "report_id": state.get("report_id"),
            "final_report": summarize_final_report(state.get("final_report")),
        }
    if step_name == "schedule_next_run":
        return {
            "frequency": tracker.get("frequency"),
            "mode": tracker.get("mode"),
        }
    return {
        "mode": state.get("mode"),
        "trigger": state.get("trigger"),
    }


def build_step_output_snapshot(
    step_name: str,
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    llm_calls: list[dict[str, Any]],
    duration_ms: float | None = None,
) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    if step_name == "load_tracker_context":
        snapshot = {
            "tracker": sanitize_tracker_snapshot(result.get("tracker")),
            "user_context": sanitize_user_context(result.get("user_context")),
        }
    elif step_name in {"normalize_research_brief", "validate_brief"}:
        snapshot = {"normalized_brief": result.get("normalized_brief") or state.get("normalized_brief") or {}}
    elif step_name == "plan_research_tasks":
        snapshot = {
            "research_plan": result.get("research_plan") or {},
            "search_tasks": summarize_search_tasks(result.get("search_tasks"), include_candidates=False),
        }
    elif step_name == "run_search_tasks":
        snapshot = {"search_tasks": summarize_search_tasks(result.get("search_tasks"), include_candidates=True)}
    elif step_name == "fetch_documents":
        snapshot = {"source_items": summarize_source_items(result.get("source_items"))}
    elif step_name in {"extract_evidence", "dedupe_and_rank_evidence"}:
        snapshot = {"evidence_items": summarize_evidence_items(result.get("evidence_items"))}
    elif step_name == "build_report_diff":
        snapshot = {"diff_summary": result.get("diff_summary") or {}}
    elif step_name == "write_report":
        snapshot = {
            "final_report": summarize_final_report(result.get("final_report")),
            "report_sections": summarize_report_sections(result.get("report_sections")),
        }
    elif step_name == "derive_report_actions":
        snapshot = {"report_actions": summarize_report_actions(result.get("report_actions"))}
    elif step_name == "verify_report":
        snapshot = {
            "verification_result": result.get("verification_result") or {},
            "final_report": summarize_final_report(result.get("final_report")),
        }
    elif step_name == "persist_report":
        snapshot = {
            "report_id": result.get("report_id"),
            "final_report": summarize_final_report(result.get("final_report")),
        }
    elif step_name == "emit_alerts":
        snapshot = {
            "report_id": state.get("report_id"),
            "alert_emitted": bool(state.get("report_id") and (state.get("final_report") or {}).get("status") == "published"),
        }
    elif step_name == "schedule_next_run":
        snapshot = {
            "next_run_at": (result.get("next_run_at") if isinstance(result, dict) else None),
            "frequency": sanitize_tracker_snapshot(state.get("tracker")).get("frequency"),
        }

    if llm_calls:
        snapshot["llm_calls"] = llm_calls
    if duration_ms is not None:
        snapshot["duration_ms"] = round(duration_ms, 2)
    return snapshot


def merge_step_metrics(
    existing_metrics: dict[str, Any] | None,
    *,
    step_name: str,
    status: str,
    duration_ms: float,
    llm_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    metrics = dict(existing_metrics or {})
    steps = dict(metrics.get("steps", {}))
    totals = dict(metrics.get("totals", {}))

    tokens_in = sum((item.get("tokens_in") or 0) for item in llm_calls)
    tokens_out = sum((item.get("tokens_out") or 0) for item in llm_calls)
    cost_estimate_cents = sum((item.get("cost_estimate_cents") or 0) for item in llm_calls)

    steps[step_name] = {
        "status": status,
        "duration_ms": round(duration_ms, 2),
        "llm_call_count": len(llm_calls),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_estimate_cents": cost_estimate_cents,
    }

    totals["duration_ms"] = round(float(totals.get("duration_ms", 0.0)) + duration_ms, 2)
    totals["llm_call_count"] = int(totals.get("llm_call_count", 0)) + len(llm_calls)
    totals["tokens_in"] = int(totals.get("tokens_in", 0)) + tokens_in
    totals["tokens_out"] = int(totals.get("tokens_out", 0)) + tokens_out
    totals["cost_estimate_cents"] = int(totals.get("cost_estimate_cents", 0)) + cost_estimate_cents

    metrics["steps"] = steps
    metrics["totals"] = totals
    return metrics


def _step_duration_seconds(step: Any) -> float | None:
    started_at = getattr(step, "started_at", None)
    completed_at = getattr(step, "completed_at", None)
    if not started_at or not completed_at:
        return None
    return max((completed_at - started_at).total_seconds(), 0.0)


def build_trace_payload(run: Any, steps: list[Any]) -> dict[str, Any]:
    tracker_snapshot = None
    normalized_brief = None
    research_plan = None
    search_tasks = None
    fetched_sources = None
    evidence_items = None
    diff_summary = None
    final_report = None
    verification_result = None
    report_actions = None

    failed_steps = [step.step_name for step in steps if getattr(step, "status", None) == "failed"]
    succeeded_steps = [step.step_name for step in steps if getattr(step, "status", None) == "succeeded"]
    llm_step_count = sum(1 for step in steps if getattr(step, "model_name", None))
    total_tokens_in = sum((getattr(step, "tokens_in", None) or 0) for step in steps)
    total_tokens_out = sum((getattr(step, "tokens_out", None) or 0) for step in steps)
    total_cost_estimate_cents = sum((getattr(step, "cost_estimate_cents", None) or 0) for step in steps)
    timeline = []

    for step in steps:
        output_json = getattr(step, "output_json", None) or {}
        if step.step_name == "load_tracker_context":
            tracker_snapshot = output_json.get("tracker") or tracker_snapshot
        elif step.step_name in {"normalize_research_brief", "validate_brief"}:
            normalized_brief = output_json.get("normalized_brief") or normalized_brief
        elif step.step_name == "plan_research_tasks":
            research_plan = output_json.get("research_plan") or research_plan
            search_tasks = output_json.get("search_tasks") or search_tasks
        elif step.step_name == "run_search_tasks":
            search_tasks = output_json.get("search_tasks") or search_tasks
        elif step.step_name == "fetch_documents":
            fetched_sources = output_json.get("source_items") or fetched_sources
        elif step.step_name in {"extract_evidence", "dedupe_and_rank_evidence"}:
            evidence_items = output_json.get("evidence_items") or evidence_items
        elif step.step_name == "build_report_diff":
            diff_summary = output_json.get("diff_summary") or diff_summary
        elif step.step_name == "write_report":
            final_report = output_json.get("final_report") or final_report
        elif step.step_name == "derive_report_actions":
            report_actions = output_json.get("report_actions") or report_actions
        elif step.step_name == "verify_report":
            verification_result = output_json.get("verification_result") or verification_result
            final_report = output_json.get("final_report") or final_report
        elif step.step_name == "persist_report":
            final_report = output_json.get("final_report") or final_report

        timeline.append(
            {
                "step_name": step.step_name,
                "status": step.status,
                "duration_seconds": _step_duration_seconds(step),
                "started_at": _isoformat(getattr(step, "started_at", None)),
                "completed_at": _isoformat(getattr(step, "completed_at", None)),
                "model_name": getattr(step, "model_name", None),
                "prompt_version": getattr(step, "prompt_version", None),
            }
        )

    run_duration_seconds = None
    if getattr(run, "started_at", None) and getattr(run, "completed_at", None):
        run_duration_seconds = max((run.completed_at - run.started_at).total_seconds(), 0.0)

    return {
        "summary": {
            "status": getattr(run, "status", None),
            "mode": getattr(run, "mode", None),
            "trigger_reason": getattr(run, "trigger_reason", None),
            "step_count": len(steps),
            "succeeded_steps": succeeded_steps,
            "failed_steps": failed_steps,
            "llm_step_count": llm_step_count,
            "total_tokens_in": total_tokens_in,
            "total_tokens_out": total_tokens_out,
            "total_cost_estimate_cents": total_cost_estimate_cents,
            "run_duration_seconds": run_duration_seconds,
        },
        "artifacts": {
            "tracker_snapshot": tracker_snapshot,
            "normalized_brief": normalized_brief,
            "research_plan": research_plan,
            "search_tasks": search_tasks,
            "fetched_sources": fetched_sources,
            "evidence_items": evidence_items,
            "diff_summary": diff_summary,
            "final_report": final_report,
            "verification_result": verification_result,
            "report_actions": report_actions,
        },
        "timeline": timeline,
    }


def _get_langsmith_client():
    global _LANGSMITH_IMPORT_FAILED, _LANGSMITH_CLIENT

    if _LANGSMITH_CLIENT is not None:
        return _LANGSMITH_CLIENT
    if _LANGSMITH_IMPORT_FAILED:
        return None
    if not os.getenv("LANGSMITH_API_KEY", "").strip():
        return None

    try:
        module = importlib.import_module("langsmith")
        client_cls = getattr(module, "Client", None)
        if client_cls is None:
            raise RuntimeError("langsmith.Client is not available")
        _LANGSMITH_CLIENT = client_cls(api_key=os.getenv("LANGSMITH_API_KEY"))
        return _LANGSMITH_CLIENT
    except Exception as exc:  # noqa: BLE001
        _LANGSMITH_IMPORT_FAILED = True
        logger.warning("Radar Research LangSmith tracing disabled: %s", exc)
        return None


def _trace_metadata(
    *,
    run_id: str,
    profile_id: str,
    user_id: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = {
        "run_id": run_id,
        "profile_id": profile_id,
        "user_id": user_id,
        "environment": os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")),
    }
    if extra:
        metadata.update(extra)
    return metadata


def emit_langsmith_step_trace(
    *,
    run_id: str,
    profile_id: str,
    user_id: str,
    step_name: str,
    input_payload: dict[str, Any],
    output_payload: dict[str, Any] | None,
    error_message: str | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    client = _get_langsmith_client()
    if client is None or not hasattr(client, "create_run"):
        return
    try:
        client.create_run(
            name=f"research_radar.{step_name}",
            run_type="chain",
            inputs=input_payload,
            outputs=output_payload or {},
            error=error_message,
            project_name=os.getenv("LANGSMITH_PROJECT", "apptrail-radar"),
            extra={"metadata": _trace_metadata(run_id=run_id, profile_id=profile_id, user_id=user_id, extra=metadata)},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Radar Research LangSmith step trace failed: %s", exc)


def emit_langsmith_run_trace(
    *,
    run_id: str,
    profile_id: str,
    user_id: str,
    input_payload: dict[str, Any],
    output_payload: dict[str, Any] | None,
    error_message: str | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    client = _get_langsmith_client()
    if client is None or not hasattr(client, "create_run"):
        return
    try:
        client.create_run(
            name="research_radar.run",
            run_type="chain",
            inputs=input_payload,
            outputs=output_payload or {},
            error=error_message,
            project_name=os.getenv("LANGSMITH_PROJECT", "apptrail-radar"),
            extra={"metadata": _trace_metadata(run_id=run_id, profile_id=profile_id, user_id=user_id, extra=metadata)},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Radar Research LangSmith run trace failed: %s", exc)
