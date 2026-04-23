from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.services import ai_orchestrator
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
) -> tuple[NormalizedResearchBrief, dict[str, Any] | None]:
    if not ai_orchestrator.has_configured_api_key():
        return deterministic_normalized_brief(tracker, user_context), None

    result = await ai_orchestrator.run_json_task_with_metadata(
        "research_brief_normalizer",
        build_brief_normalization_prompt(tracker=tracker, user_context=user_context),
        metadata={"surface": "research_radar", "profile_name": tracker.get("name")},
    )
    return NormalizedResearchBrief.model_validate(result.payload), _task_call_metric(result)


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
) -> tuple[list[ResearchSearchTask], dict[str, Any] | None]:
    if not ai_orchestrator.has_configured_api_key():
        return deterministic_research_plan(normalized_brief, depth, max_queries), None

    result = await ai_orchestrator.run_json_task_with_metadata(
        "research_planner",
        build_research_plan_prompt(
            normalized_brief=normalized_brief,
            depth=depth,
            max_tasks=min(max_queries, DEPTH_TASK_LIMITS.get(depth, DEPTH_TASK_LIMITS["standard"])),
        ),
        metadata={"surface": "research_radar", "depth": depth},
    )
    tasks = result.payload.get("tasks", result.payload)
    return [ResearchSearchTask.model_validate(task) for task in tasks], _task_call_metric(result)


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
) -> tuple[list[ExtractedEvidence], dict[str, Any] | None]:
    if not ai_orchestrator.has_configured_api_key():
        return deterministic_extract_evidence(normalized_brief, source_document), None

    result = await ai_orchestrator.run_json_task_with_metadata(
        "research_evidence_extractor",
        build_evidence_extraction_prompt(normalized_brief=normalized_brief, source_document=source_document),
        metadata={"surface": "research_radar", "source_url": source_document.get("source_url")},
        max_tokens=1800,
    )
    evidence_items = result.payload.get("evidence_items", result.payload)
    return [ExtractedEvidence.model_validate(item) for item in evidence_items], _task_call_metric(result)


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
) -> tuple[FinalReportDraft, list[ReportSectionDraft], dict[str, Any] | None]:
    if not ai_orchestrator.has_configured_api_key():
        report, sections = deterministic_report(normalized_brief, diff_summary, evidence_items)
        return report, sections, None

    result = await ai_orchestrator.run_json_task_with_metadata(
        "research_report_writer",
        build_report_prompt(
            normalized_brief=normalized_brief,
            diff_summary=diff_summary,
            evidence_items=evidence_items,
        ),
        metadata={"surface": "research_radar", "evidence_count": len(evidence_items)},
        max_tokens=3000,
    )
    payload = result.payload
    sections = [ReportSectionDraft.model_validate(section) for section in payload.get("sections", [])]
    report = FinalReportDraft(
        title=payload["title"],
        summary_markdown=payload["summary_markdown"],
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
) -> tuple[VerificationResult, dict[str, Any] | None]:
    if not ai_orchestrator.has_configured_api_key():
        return deterministic_verification(report_sections, evidence_items), None

    result = await ai_orchestrator.run_json_task_with_metadata(
        "research_report_verifier",
        build_verification_prompt(
            normalized_brief=normalized_brief,
            report_sections=report_sections,
            evidence_items=evidence_items,
        ),
        metadata={"surface": "research_radar", "section_count": len(report_sections)},
        max_tokens=1200,
    )
    return VerificationResult.model_validate(result.payload), _task_call_metric(result)


async def verify_report(normalized_brief: dict[str, Any], report_sections: list[dict[str, Any]], evidence_items: list[dict[str, Any]]) -> VerificationResult:
    verification_result, _ = await verify_report_with_metrics(normalized_brief, report_sections, evidence_items)
    return verification_result
