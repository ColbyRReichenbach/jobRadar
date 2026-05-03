from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services import ai_orchestrator, ai_safety
from backend.services.research_radar.config import DEPTH_TASK_LIMITS, DEFAULT_MAX_RESULTS_PER_TASK
from backend.services.research_radar.prompts import (
    build_brief_normalization_prompt,
    build_evidence_extraction_prompt,
    build_report_prompt,
    build_research_plan_prompt,
    build_verification_prompt,
)
from backend.services.research_radar.schemas import (
    ExtractedEvidence,
    FinalReportDraft,
    NormalizedResearchBrief,
    ReportSectionDraft,
    ResearchSearchTask,
    VerificationResult,
)

logger = logging.getLogger(__name__)


class ResearchModelUnavailableError(RuntimeError):
    """Raised when Radar research cannot produce governed OpenAI-backed output."""


def deterministic_fallbacks_allowed() -> bool:
    if os.getenv("TESTING") == "1":
        return True
    return os.getenv("RESEARCH_RADAR_ALLOW_DETERMINISTIC_FALLBACKS", "false").lower() == "true"


def _require_openai(task: str) -> None:
    if not ai_orchestrator.has_configured_api_key():
        raise ResearchModelUnavailableError(f"OPENAI_API_KEY is not configured for {task}")


def _task_call_metric(result: ai_orchestrator.AiTaskRunResult) -> dict[str, Any]:
    return {
        "task": result.task,
        "model": result.model,
        "prompt_version": result.prompt_version,
        "duration_ms": result.duration_ms,
        "retries": result.retries,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "cost_estimate_cents": result.cost_estimate_cents,
    }


def _record_llm_fallback(
    task: str,
    reason: str,
    metadata: dict[str, Any],
    exc: Exception,
) -> None:
    ai_orchestrator.record_fallback(task, reason, metadata)
    logger.warning(
        "research_radar_llm_fallback task=%s reason=%s metadata=%s error=%s",
        task,
        reason,
        metadata,
        repr(exc),
    )


def _record_llm_failure(
    task: str,
    metadata: dict[str, Any],
    exc: Exception,
) -> None:
    logger.warning(
        "research_radar_llm_failure task=%s metadata=%s error=%s",
        task,
        metadata,
        repr(exc),
    )


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return None


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if not isinstance(value, list):
        return []

    cleaned_values: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _clean_string(item)
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned_values.append(text)
    return cleaned_values


def _coerce_constraints(value: Any) -> list[str]:
    if isinstance(value, dict):
        constraints: list[str] = []
        for key, item in value.items():
            if item in (None, "", [], {}):
                continue
            if isinstance(item, list):
                item_text = ", ".join(_coerce_string_list(item))
            else:
                item_text = _clean_string(item) or ""
            if item_text:
                constraints.append(f"{key}: {item_text}")
        return constraints
    return _coerce_string_list(value)


def _coerce_float(value: Any, default: float, *, minimum: float = 0.0, maximum: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _coerce_int(value: Any, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        number = default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def _slugify(value: str | None, fallback: str) -> str:
    base = (value or fallback).strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", base).strip("_")
    return slug or fallback


def _normalize_brief_payload(
    payload: dict[str, Any],
    *,
    tracker: dict[str, Any],
    user_context: dict[str, Any],
) -> NormalizedResearchBrief:
    fallback = deterministic_normalized_brief(tracker, user_context)
    search_constraints_raw = _first_present(payload, "search_constraints", "constraints", "filters")
    search_constraints = _coerce_constraints(search_constraints_raw)
    constraints_dict = search_constraints_raw if isinstance(search_constraints_raw, dict) else {}

    search_objective = (
        _clean_string(_first_present(payload, "search_objective", "research_objective", "objective", "summary"))
        or fallback.search_objective
    )
    fit_summary = (
        _clean_string(_first_present(payload, "fit_summary", "candidate_fit", "profile_fit", "user_fit_summary"))
        or fallback.fit_summary
    )

    normalized = {
        "search_objective": search_objective,
        "ideal_role_titles": _coerce_string_list(_first_present(payload, "ideal_role_titles", "target_roles", "role_titles", "roles")) or fallback.ideal_role_titles,
        "target_domains": _coerce_string_list(_first_present(payload, "target_domains", "domains", "industries")) or fallback.target_domains,
        "target_companies": _coerce_string_list(_first_present(payload, "target_companies", "companies", "company_targets")) or fallback.target_companies,
        "target_locations": _coerce_string_list(_first_present(payload, "target_locations", "locations")) or _coerce_string_list(constraints_dict.get("target_locations")) or fallback.target_locations,
        "remote_preferences": _coerce_string_list(_first_present(payload, "remote_preferences", "remote_types")) or _coerce_string_list(constraints_dict.get("remote_preferences")) or fallback.remote_preferences,
        "seniority": _coerce_string_list(_first_present(payload, "seniority", "seniority_levels")) or fallback.seniority,
        "must_have_signals": _coerce_string_list(_first_present(payload, "must_have_signals", "must_haves", "included_keywords", "keywords")) or _coerce_string_list(constraints_dict.get("included_keywords")) or fallback.must_have_signals,
        "avoid_signals": _coerce_string_list(_first_present(payload, "avoid_signals", "avoid", "excluded_keywords")) or _coerce_string_list(constraints_dict.get("excluded_keywords")) or fallback.avoid_signals,
        "fit_summary": fit_summary,
        "search_constraints": search_constraints or fallback.search_constraints,
    }
    return NormalizedResearchBrief.model_validate(normalized)


def _infer_task_type(raw_type: Any, query: str | None) -> str:
    raw_text = (_clean_string(raw_type) or "").lower()
    query_text = (query or "").lower()
    text = f"{raw_text} {query_text}"
    if any(token in raw_text for token in ("role", "opening", "job", "career")):
        return "role_openings"
    if any(token in raw_text for token in ("tech", "stack", "infrastructure")):
        return "tech_stack_signal"
    if any(token in raw_text for token in ("team", "growth", "expansion", "headcount")):
        return "team_growth_signal"
    if any(token in raw_text for token in ("strategy", "roadmap", "funding", "market")):
        return "company_strategy_signal"
    if any(token in raw_text for token in ("hiring", "recruiting")):
        return "company_hiring_signal"
    if any(token in query_text for token in ("career", "job", "role", "opening")):
        return "role_openings"
    if any(token in text for token in ("hiring", "recruiting", "growth")):
        return "company_hiring_signal"
    if any(token in text for token in ("tech", "stack", "infrastructure")):
        return "tech_stack_signal"
    return "role_openings"


def _normalize_task_payload(payload: dict[str, Any], index: int, max_queries: int) -> ResearchSearchTask:
    query = _clean_string(_first_present(payload, "query", "search_query", "search", "keyword_query"))
    company_hint = _clean_string(_first_present(payload, "company_hint", "company", "target_company"))
    role_hint = _clean_string(_first_present(payload, "role_hint", "role", "target_role"))
    if not query:
        query_parts = [company_hint, role_hint, _clean_string(_first_present(payload, "objective", "description"))]
        query = " ".join(part for part in query_parts if part) or "AI engineering roles"

    return ResearchSearchTask(
        task_id=_clean_string(_first_present(payload, "task_id", "id", "key")) or f"task_{index + 1}",
        task_type=_infer_task_type(_first_present(payload, "task_type", "type", "category", "expected_signal_type"), query),
        query=query,
        company_hint=company_hint,
        role_hint=role_hint,
        expected_signal_type=_clean_string(_first_present(payload, "expected_signal_type", "signal_type", "expected_signal")),
        max_results=_coerce_int(_first_present(payload, "max_results", "limit"), min(DEFAULT_MAX_RESULTS_PER_TASK, max_queries), minimum=1, maximum=10),
        priority=_coerce_int(_first_present(payload, "priority", "rank"), max(50, 100 - index * 10), minimum=1, maximum=100),
        candidates=payload.get("candidates") if isinstance(payload.get("candidates"), list) else [],
    )


def _normalize_evidence_payload(payload: dict[str, Any], source_document: dict[str, Any]) -> ExtractedEvidence:
    title = _clean_string(_first_present(payload, "title", "headline", "source_title")) or source_document.get("title")
    snippet = _clean_string(_first_present(payload, "snippet", "quote", "source_excerpt", "excerpt"))
    claim = _clean_string(_first_present(payload, "claim", "finding", "summary", "evidence", "key_finding")) or snippet
    if not claim:
        claim = (source_document.get("raw_text") or source_document.get("excerpt") or title or "Research finding")[:280]
    source_item_id = _clean_string(_first_present(payload, "source_item_id", "source_id", "id")) or (
        str(source_document["source_item_id"]) if source_document.get("source_item_id") else None
    )

    citation_ids = _coerce_string_list(_first_present(payload, "citation_ids", "citations"))
    if not citation_ids and source_item_id:
        citation_ids = [source_item_id]

    return ExtractedEvidence(
        source_item_id=source_item_id,
        evidence_type=_infer_task_type(_first_present(payload, "evidence_type", "type", "signal_type", "category"), claim).replace("role_openings", "role_opening"),
        title=title,
        claim=claim,
        snippet=snippet,
        url=_clean_string(_first_present(payload, "url", "source_url")) or source_document.get("source_url"),
        domain=_clean_string(payload.get("domain")) or source_document.get("domain"),
        company_name=_clean_string(_first_present(payload, "company_name", "company")) or source_document.get("company_name"),
        role_title=_clean_string(_first_present(payload, "role_title", "role")) or source_document.get("role_title"),
        published_at=_clean_string(_first_present(payload, "published_at", "date")),
        confidence=_coerce_float(payload.get("confidence"), 0.7),
        relevance_score=_coerce_float(_first_present(payload, "relevance_score", "relevance"), 0.7),
        novelty_score=_coerce_float(_first_present(payload, "novelty_score", "novelty"), 0.6),
        supports_objective=bool(payload.get("supports_objective", True)),
        citation_ids=citation_ids,
    )


def _normalize_report_section(payload: dict[str, Any], index: int) -> ReportSectionDraft:
    title = _clean_string(_first_present(payload, "title", "heading", "name")) or f"Section {index + 1}"
    structured_json = payload.get("structured_json") if isinstance(payload.get("structured_json"), dict) else {}
    citation_ids = _coerce_string_list(_first_present(payload, "citation_ids", "citations", "sources"))
    if citation_ids:
        structured_json = {**structured_json, "citation_ids": citation_ids}

    return ReportSectionDraft(
        section_key=_clean_string(_first_present(payload, "section_key", "key", "id")) or _slugify(title, f"section_{index + 1}"),
        title=title,
        display_order=_coerce_int(_first_present(payload, "display_order", "order", "index"), index + 1, minimum=1),
        markdown=_clean_string(_first_present(payload, "markdown", "content", "body", "text", "summary")) or "",
        structured_json=structured_json,
    )


def _normalize_verification_payload(payload: dict[str, Any], fallback: VerificationResult) -> VerificationResult:
    citation_coverage_raw = payload.get("citation_coverage")
    if isinstance(citation_coverage_raw, dict):
        citation_coverage = _coerce_float(
            _first_present(citation_coverage_raw, "overall", "score", "value"),
            fallback.citation_coverage,
        )
    else:
        citation_coverage = _coerce_float(citation_coverage_raw, fallback.citation_coverage)

    hallucination_raw = payload.get("hallucination_risk")
    if isinstance(hallucination_raw, dict):
        hallucination_risk = _clean_string(_first_present(hallucination_raw, "overall_risk", "risk", "level")) or fallback.hallucination_risk
    else:
        hallucination_risk = _clean_string(hallucination_raw) or fallback.hallucination_risk
    if hallucination_risk not in {"low", "medium", "high"}:
        hallucination_risk = fallback.hallucination_risk

    status = _clean_string(_first_present(payload, "status", "readiness", "final_status")) or fallback.status
    if status not in {"ready", "needs_review"}:
        status = "ready" if payload.get("ready") is True else fallback.status

    unsupported_claims = payload.get("unsupported_claims")
    default_unsupported_count = len(unsupported_claims) if isinstance(unsupported_claims, list) else fallback.unsupported_claim_count

    return VerificationResult(
        unsupported_claim_count=_coerce_int(_first_present(payload, "unsupported_claim_count", "unsupported_count"), default_unsupported_count, minimum=0),
        section_completeness=_coerce_float(_first_present(payload, "section_completeness", "completeness"), fallback.section_completeness),
        tracker_fit_score=_coerce_float(_first_present(payload, "tracker_fit_score", "tracker_fit", "fit_score"), fallback.tracker_fit_score),
        citation_coverage=citation_coverage,
        hallucination_risk=hallucination_risk,
        status=status,
        notes=_coerce_string_list(_first_present(payload, "notes", "issues", "recommendations")) or fallback.notes,
    )


def _unique_clean(values: list[str] | None) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values or []:
        stripped = value.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(stripped)
    return cleaned


def deterministic_normalized_brief(tracker: dict[str, Any], user_context: dict[str, Any]) -> NormalizedResearchBrief:
    role_titles = _unique_clean(tracker.get("selected_roles") or user_context.get("role_interest_labels"))
    domains = _unique_clean(tracker.get("selected_domains"))
    companies = _unique_clean(tracker.get("selected_companies"))
    locations = _unique_clean(tracker.get("target_locations") or user_context.get("preferred_locations"))
    remote_preferences = _unique_clean(tracker.get("remote_types") or ([user_context["preferred_remote_type"]] if user_context.get("preferred_remote_type") else []))
    seniority = _unique_clean(tracker.get("seniority_levels"))
    must_have = _unique_clean((tracker.get("keywords") or [])[:8])
    avoid = _unique_clean((tracker.get("excluded_keywords") or [])[:8])

    objective = tracker.get("objective") or "Identify public hiring signals that match the user's target job search."
    if role_titles:
        objective += f" Prioritize roles similar to: {', '.join(role_titles[:4])}."
    if companies:
        objective += f" Focus companies include: {', '.join(companies[:4])}."

    fit_summary_parts = []
    if user_context.get("experience_years") is not None:
        fit_summary_parts.append(f"{user_context['experience_years']} years of experience")
    if user_context.get("skills"):
        fit_summary_parts.append(f"skills in {', '.join(user_context['skills'][:6])}")
    if user_context.get("tools"):
        fit_summary_parts.append(f"tools including {', '.join(user_context['tools'][:6])}")
    fit_summary = ", ".join(fit_summary_parts) if fit_summary_parts else "Use the saved AppTrail profile context when ranking fit."

    constraints = []
    if locations:
        constraints.append(f"Target locations: {', '.join(locations[:5])}")
    if remote_preferences:
        constraints.append(f"Remote preferences: {', '.join(remote_preferences[:5])}")
    if tracker.get("report_prompt_notes"):
        constraints.append(tracker["report_prompt_notes"])

    return NormalizedResearchBrief(
        search_objective=objective,
        ideal_role_titles=role_titles[:8],
        target_domains=domains[:8],
        target_companies=companies[:10],
        target_locations=locations[:8],
        remote_preferences=remote_preferences[:5],
        seniority=seniority[:5],
        must_have_signals=must_have,
        avoid_signals=avoid,
        fit_summary=fit_summary,
        search_constraints=constraints,
    )


async def normalize_brief_with_metrics(
    tracker: dict[str, Any],
    user_context: dict[str, Any],
    *,
    db_session: AsyncSession | None = None,
    user_id: str | None = None,
) -> tuple[NormalizedResearchBrief, dict[str, Any] | None]:
    fallback = deterministic_normalized_brief(tracker, user_context)
    if not ai_orchestrator.has_configured_api_key():
        if deterministic_fallbacks_allowed():
            return fallback, None
        _require_openai("research_brief_normalizer")

    metadata = {"surface": "research_radar", "profile_name": tracker.get("name")}
    try:
        result = await ai_safety.run_json_task_with_safety(
            "research_brief_normalizer",
            build_brief_normalization_prompt(tracker=tracker, user_context=user_context),
            metadata=metadata,
            data_classes=[ai_safety.DATA_CLASS_CAREER_PRIVATE, ai_safety.DATA_CLASS_UNTRUSTED_INBOUND],
            allow_identity=False,
            untrusted_input=True,
            db_session=db_session,
            user_id=user_id,
        )
        return _normalize_brief_payload(result.payload, tracker=tracker, user_context=user_context), _task_call_metric(result)
    except Exception as exc:  # noqa: BLE001
        if deterministic_fallbacks_allowed():
            _record_llm_fallback("research_brief_normalizer", "task_failure_or_invalid_payload", metadata, exc)
            return fallback, None
        _record_llm_failure("research_brief_normalizer", metadata, exc)
        raise ResearchModelUnavailableError("Radar brief normalization failed") from exc


async def normalize_brief(tracker: dict[str, Any], user_context: dict[str, Any]) -> NormalizedResearchBrief:
    normalized, _ = await normalize_brief_with_metrics(tracker, user_context)
    return normalized


def deterministic_research_plan(normalized_brief: dict[str, Any], depth: str, max_queries: int) -> list[ResearchSearchTask]:
    max_tasks = min(max_queries, DEPTH_TASK_LIMITS.get(depth, DEPTH_TASK_LIMITS["standard"]))
    companies = _unique_clean(normalized_brief.get("target_companies"))[:4]
    roles = _unique_clean(normalized_brief.get("ideal_role_titles"))[:4]
    domains = _unique_clean(normalized_brief.get("target_domains"))[:4]

    tasks: list[ResearchSearchTask] = []
    seed_roles = roles or ["software engineer"]
    seed_companies = companies or domains or ["AI company"]
    task_counter = 0

    for company in seed_companies:
        if len(tasks) >= max_tasks:
            break
        role_hint = seed_roles[task_counter % len(seed_roles)]
        tasks.append(
            ResearchSearchTask(
                task_id=f"task_{task_counter + 1}",
                task_type="role_openings",
                query=f"{company} careers {role_hint}",
                company_hint=company,
                role_hint=role_hint,
                expected_signal_type="role_opening",
                max_results=min(DEFAULT_MAX_RESULTS_PER_TASK, max_queries),
                priority=max(40, 100 - (task_counter * 5)),
            )
        )
        task_counter += 1

    for company in seed_companies:
        if len(tasks) >= max_tasks:
            break
        tasks.append(
            ResearchSearchTask(
                task_id=f"task_{task_counter + 1}",
                task_type="company_hiring_signal",
                query=f"{company} hiring blog engineering team growth",
                company_hint=company,
                expected_signal_type="company_signal",
                max_results=min(DEFAULT_MAX_RESULTS_PER_TASK, max_queries),
                priority=max(35, 95 - (task_counter * 5)),
            )
        )
        task_counter += 1

    if not tasks:
        tasks.append(
            ResearchSearchTask(
                task_id="task_1",
                task_type="role_openings",
                query=normalized_brief.get("search_objective", "AI engineering roles"),
                max_results=min(DEFAULT_MAX_RESULTS_PER_TASK, max_queries),
                priority=80,
            )
        )

    return tasks[:max_tasks]


async def plan_research_tasks_with_metrics(
    normalized_brief: dict[str, Any],
    depth: str,
    max_queries: int,
    *,
    db_session: AsyncSession | None = None,
    user_id: str | None = None,
) -> tuple[list[ResearchSearchTask], dict[str, Any] | None]:
    fallback = deterministic_research_plan(normalized_brief, depth, max_queries)
    if not ai_orchestrator.has_configured_api_key():
        if deterministic_fallbacks_allowed():
            return fallback, None
        _require_openai("research_planner")

    metadata = {"surface": "research_radar", "depth": depth}
    try:
        result = await ai_safety.run_json_task_with_safety(
            "research_planner",
            build_research_plan_prompt(
                normalized_brief=normalized_brief,
                depth=depth,
                max_tasks=min(max_queries, DEPTH_TASK_LIMITS.get(depth, DEPTH_TASK_LIMITS["standard"])),
            ),
            metadata=metadata,
            data_classes=[ai_safety.DATA_CLASS_CAREER_PRIVATE],
            allow_identity=False,
            untrusted_input=True,
            db_session=db_session,
            user_id=user_id,
        )
        tasks_payload = result.payload.get("tasks", result.payload)
        if not isinstance(tasks_payload, list):
            raise ValueError("research_planner returned a non-list tasks payload")
        tasks = [_normalize_task_payload(task, index, max_queries) for index, task in enumerate(tasks_payload) if isinstance(task, dict)]
        if not tasks:
            raise ValueError("research_planner returned no tasks")
        return tasks, _task_call_metric(result)
    except Exception as exc:  # noqa: BLE001
        if deterministic_fallbacks_allowed():
            _record_llm_fallback("research_planner", "task_failure_or_invalid_payload", metadata, exc)
            return fallback, None
        _record_llm_failure("research_planner", metadata, exc)
        raise ResearchModelUnavailableError("Radar research planning failed") from exc


async def plan_research_tasks(normalized_brief: dict[str, Any], depth: str, max_queries: int) -> list[ResearchSearchTask]:
    tasks, _ = await plan_research_tasks_with_metrics(normalized_brief, depth, max_queries)
    return tasks


def deterministic_extract_evidence(normalized_brief: dict[str, Any], source_document: dict[str, Any]) -> list[ExtractedEvidence]:
    title = source_document.get("title") or source_document.get("source_url") or "Research finding"
    raw_text = (source_document.get("raw_text") or "").strip()
    snippet = raw_text[:280] if raw_text else source_document.get("excerpt") or ""
    company_name = source_document.get("company_name")
    role_title = source_document.get("role_title")
    lowered_text = f"{title} {raw_text}".lower()
    if role_title or "job" in lowered_text or "career" in lowered_text or "/jobs/" in (source_document.get("source_url") or ""):
        evidence_type = "role_opening"
    elif "hiring" in lowered_text or "team" in lowered_text or "expanding" in lowered_text:
        evidence_type = "company_hiring_signal"
    elif "platform" in lowered_text or "stack" in lowered_text or "infra" in lowered_text:
        evidence_type = "tech_stack_signal"
    else:
        evidence_type = "company_strategy_signal"

    claim = snippet or f"{title} appears relevant to the search objective."
    supports_objective = True
    objective = normalized_brief.get("search_objective", "").lower()
    if company_name and company_name.lower() in objective:
        supports_objective = True

    return [
        ExtractedEvidence(
            source_item_id=str(source_document["source_item_id"]) if source_document.get("source_item_id") else None,
            evidence_type=evidence_type,
            title=title,
            claim=claim,
            snippet=snippet or None,
            url=source_document.get("source_url"),
            domain=source_document.get("domain"),
            company_name=company_name,
            role_title=role_title,
            published_at=source_document.get("published_at"),
            confidence=0.7,
            relevance_score=0.7,
            novelty_score=0.6,
            supports_objective=supports_objective,
            citation_ids=[str(source_document["source_item_id"])] if source_document.get("source_item_id") else [],
        )
    ]


async def extract_evidence_with_metrics(
    normalized_brief: dict[str, Any],
    source_document: dict[str, Any],
    *,
    db_session: AsyncSession | None = None,
    user_id: str | None = None,
) -> tuple[list[ExtractedEvidence], dict[str, Any] | None]:
    fallback = deterministic_extract_evidence(normalized_brief, source_document)
    if not ai_orchestrator.has_configured_api_key():
        if deterministic_fallbacks_allowed():
            return fallback, None
        _require_openai("research_evidence_extractor")

    metadata = {"surface": "research_radar", "source_url": source_document.get("source_url")}
    try:
        result = await ai_safety.run_json_task_with_safety(
            "research_evidence_extractor",
            build_evidence_extraction_prompt(normalized_brief=normalized_brief, source_document=source_document),
            metadata=metadata,
            max_tokens=1800,
            data_classes=[ai_safety.DATA_CLASS_PUBLIC_RESEARCH, ai_safety.DATA_CLASS_UNTRUSTED_INBOUND],
            allow_identity=False,
            untrusted_input=True,
            db_session=db_session,
            user_id=user_id,
        )
        evidence_payload = result.payload.get("evidence_items", result.payload)
        if not isinstance(evidence_payload, list):
            raise ValueError("research_evidence_extractor returned a non-list evidence payload")
        return [_normalize_evidence_payload(item, source_document) for item in evidence_payload if isinstance(item, dict)], _task_call_metric(result)
    except Exception as exc:  # noqa: BLE001
        if deterministic_fallbacks_allowed():
            _record_llm_fallback("research_evidence_extractor", "task_failure_or_invalid_payload", metadata, exc)
            return fallback, None
        _record_llm_failure("research_evidence_extractor", metadata, exc)
        raise ResearchModelUnavailableError("Radar evidence extraction failed") from exc


async def extract_evidence(normalized_brief: dict[str, Any], source_document: dict[str, Any]) -> list[ExtractedEvidence]:
    evidence_items, _ = await extract_evidence_with_metrics(normalized_brief, source_document)
    return evidence_items


def deterministic_report(normalized_brief: dict[str, Any], diff_summary: dict[str, Any], evidence_items: list[dict[str, Any]]) -> tuple[FinalReportDraft, list[ReportSectionDraft]]:
    objective = normalized_brief.get("search_objective", "Radar research report")
    top_evidence = evidence_items[:5]
    date_str = datetime.now(timezone.utc).date().isoformat()
    summary_lines = [f"- {item.get('claim')}" for item in top_evidence] or ["- No public findings were captured for this run."]
    sections = [
        ReportSectionDraft(
            section_key="executive_summary",
            title="Executive Summary",
            display_order=1,
            markdown=f"{objective}\n\n" + "\n".join(summary_lines[:3]),
            structured_json={"citation_ids": [item.get("source_item_id") for item in top_evidence if item.get("source_item_id")]},
        ),
        ReportSectionDraft(
            section_key="what_changed",
            title="What Changed Since The Last Run",
            display_order=2,
            markdown=diff_summary.get("diff_summary") or "This is the first saved report for this tracker.",
            structured_json={"new_findings": diff_summary.get("new_findings", [])},
        ),
        ReportSectionDraft(
            section_key="best_fit_opportunities",
            title="Best-Fit Opportunities",
            display_order=3,
            markdown="\n".join(summary_lines) or "No clear best-fit opportunities were identified.",
            structured_json={"citation_ids": [item.get("source_item_id") for item in top_evidence if item.get("source_item_id")]},
        ),
        ReportSectionDraft(
            section_key="recommended_actions",
            title="Recommended Actions",
            display_order=4,
            markdown="Review the strongest hiring signals, compare fit against your saved profile, and decide where to apply or reach out next.",
            structured_json={"citation_ids": [item.get("source_item_id") for item in top_evidence[:3] if item.get("source_item_id")]},
        ),
    ]
    report = FinalReportDraft(
        title=f"Research report: {normalized_brief.get('search_objective', 'Radar tracker')[:80]}",
        summary_markdown="\n".join(summary_lines[:4]),
        structured_json={
            "evidence_keys": diff_summary.get("all_keys", []),
            "generated_from": "deterministic_fallback",
        },
        diff_summary=diff_summary.get("diff_summary"),
        status="draft",
        overall_confidence=0.72 if evidence_items else 0.45,
        finding_count=len(evidence_items),
        source_count=len({item.get("source_item_id") for item in evidence_items if item.get("source_item_id")}),
        new_findings_count=len(diff_summary.get("new_findings", [])),
        changed_findings_count=len(diff_summary.get("changed_findings", [])),
    )
    return report, sections


async def write_report_with_metrics(
    normalized_brief: dict[str, Any],
    diff_summary: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    *,
    db_session: AsyncSession | None = None,
    user_id: str | None = None,
) -> tuple[FinalReportDraft, list[ReportSectionDraft], dict[str, Any] | None]:
    fallback_report, fallback_sections = deterministic_report(normalized_brief, diff_summary, evidence_items)
    if not ai_orchestrator.has_configured_api_key():
        if deterministic_fallbacks_allowed():
            return fallback_report, fallback_sections, None
        _require_openai("research_report_writer")

    metadata = {"surface": "research_radar", "evidence_count": len(evidence_items)}
    try:
        result = await ai_safety.run_json_task_with_safety(
            "research_report_writer",
            build_report_prompt(
                normalized_brief=normalized_brief,
                diff_summary=diff_summary,
                evidence_items=evidence_items,
            ),
            metadata=metadata,
            max_tokens=3000,
            data_classes=[ai_safety.DATA_CLASS_PUBLIC_RESEARCH, ai_safety.DATA_CLASS_GENERATED_OUTPUT],
            allow_identity=False,
            untrusted_input=False,
            db_session=db_session,
            user_id=user_id,
        )
        payload = result.payload
        title = payload.get("title")
        summary_markdown = payload.get("summary_markdown")
        sections_payload = payload.get("sections")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("research_report_writer returned no title")
        if not isinstance(summary_markdown, str) or not summary_markdown.strip():
            raise ValueError("research_report_writer returned no summary_markdown")
        if not isinstance(sections_payload, list):
            raise ValueError("research_report_writer returned a non-list sections payload")
        sections = [_normalize_report_section(section, index) for index, section in enumerate(sections_payload) if isinstance(section, dict)]
        if not sections:
            raise ValueError("research_report_writer returned no sections")
        report = FinalReportDraft(
            title=title.strip(),
            summary_markdown=summary_markdown.strip(),
            structured_json=payload.get("structured_json", {}),
            diff_summary=diff_summary.get("diff_summary"),
            status="draft",
            overall_confidence=payload.get("overall_confidence", 0.8),
            finding_count=len(evidence_items),
            source_count=len({item.get("source_item_id") for item in evidence_items if item.get("source_item_id")}),
            new_findings_count=len(diff_summary.get("new_findings", [])),
            changed_findings_count=len(diff_summary.get("changed_findings", [])),
        )
        return report, sections, _task_call_metric(result)
    except Exception as exc:  # noqa: BLE001
        if deterministic_fallbacks_allowed():
            _record_llm_fallback("research_report_writer", "task_failure_or_invalid_payload", metadata, exc)
            return fallback_report, fallback_sections, None
        _record_llm_failure("research_report_writer", metadata, exc)
        raise ResearchModelUnavailableError("Radar report writing failed") from exc


async def write_report(normalized_brief: dict[str, Any], diff_summary: dict[str, Any], evidence_items: list[dict[str, Any]]) -> tuple[FinalReportDraft, list[ReportSectionDraft]]:
    report, sections, _ = await write_report_with_metrics(normalized_brief, diff_summary, evidence_items)
    return report, sections


def deterministic_verification(report_sections: list[dict[str, Any]], evidence_items: list[dict[str, Any]]) -> VerificationResult:
    total_sections = len(report_sections)
    completed_sections = sum(1 for section in report_sections if section.get("markdown"))
    sections_with_citations = 0
    unsupported_claim_count = 0
    for section in report_sections:
        citation_ids = section.get("structured_json", {}).get("citation_ids", [])
        if citation_ids:
            sections_with_citations += 1
        elif section.get("section_key") in {"executive_summary", "recommended_actions"} and evidence_items:
            unsupported_claim_count += 1

    completeness = completed_sections / total_sections if total_sections else 0.0
    citation_coverage = sections_with_citations / total_sections if total_sections else 0.0
    status = "needs_review" if unsupported_claim_count > 0 else "ready"
    return VerificationResult(
        unsupported_claim_count=unsupported_claim_count,
        section_completeness=round(completeness, 2),
        tracker_fit_score=0.85 if evidence_items else 0.4,
        citation_coverage=round(citation_coverage, 2),
        hallucination_risk="medium" if unsupported_claim_count else "low",
        status=status,
        notes=[] if status == "ready" else ["Executive summary or recommended actions lack direct citations."],
    )


async def verify_report_with_metrics(
    normalized_brief: dict[str, Any],
    report_sections: list[dict[str, Any]],
    evidence_items: list[dict[str, Any]],
    *,
    db_session: AsyncSession | None = None,
    user_id: str | None = None,
) -> tuple[VerificationResult, dict[str, Any] | None]:
    fallback = deterministic_verification(report_sections, evidence_items)
    if not ai_orchestrator.has_configured_api_key():
        if deterministic_fallbacks_allowed():
            return fallback, None
        _require_openai("research_report_verifier")

    metadata = {"surface": "research_radar", "section_count": len(report_sections)}
    try:
        result = await ai_safety.run_json_task_with_safety(
            "research_report_verifier",
            build_verification_prompt(
                normalized_brief=normalized_brief,
                report_sections=report_sections,
                evidence_items=evidence_items,
            ),
            metadata=metadata,
            max_tokens=1200,
            data_classes=[ai_safety.DATA_CLASS_PUBLIC_RESEARCH, ai_safety.DATA_CLASS_GENERATED_OUTPUT],
            allow_identity=False,
            untrusted_input=False,
            db_session=db_session,
            user_id=user_id,
        )
        return _normalize_verification_payload(result.payload, fallback), _task_call_metric(result)
    except Exception as exc:  # noqa: BLE001
        if deterministic_fallbacks_allowed():
            _record_llm_fallback("research_report_verifier", "task_failure_or_invalid_payload", metadata, exc)
            return fallback, None
        _record_llm_failure("research_report_verifier", metadata, exc)
        raise ResearchModelUnavailableError("Radar report verification failed") from exc


async def verify_report(normalized_brief: dict[str, Any], report_sections: list[dict[str, Any]], evidence_items: list[dict[str, Any]]) -> VerificationResult:
    verification_result, _ = await verify_report_with_metrics(normalized_brief, report_sections, evidence_items)
    return verification_result
