"""DB-backed Gmail classifier dry-run artifact generation.

This module reads stored ``EmailEvent`` rows and reruns the hybrid Gmail
classifier without model calls. It is intended for local real-Gmail analysis:
the artifacts are redacted and should be written under ``audit/runs``.
"""

from __future__ import annotations

import json
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import EmailEvent
from backend.services.email_classifier import CLASSIFICATION_TO_EMAIL_TYPE
from backend.services.gmail_intelligence.orchestrator import analyze_email
from backend.services.gmail_intelligence.preflight import detect_prompt_leaks, evaluate_llm_preflight
from backend.services.gmail_intelligence.privacy import redact_email_for_llm
from backend.services.gmail_intelligence.types import EmailCandidate, HybridClassificationResult


@dataclass(frozen=True)
class GmailDbDryRunOptions:
    user_id: uuid.UUID | None = None
    limit: int = 500
    include_hidden: bool = False
    ai_consent: bool = True
    include_redacted_body_preview: bool = True
    manual_review_limit: int = 300


def _hash_value(value: object, *, prefix: str = "") -> str | None:
    if value is None:
        return None
    raw = str(value).strip().lower()
    if not raw:
        return None
    digest = sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}{digest}" if prefix else digest


def _route_for_classification(classification: str | None) -> str:
    email_type = CLASSIFICATION_TO_EMAIL_TYPE.get(classification or "")
    if email_type == "conversation":
        return "conversation"
    if email_type == "decision":
        return "inbox"
    return "ignore"


def _classification_dict(result: HybridClassificationResult) -> dict[str, Any]:
    return {
        "classification": result.classification,
        "job_related": result.job_related,
        "confidence": round(float(result.confidence or 0), 4),
        "confidence_band": result.confidence_band,
        "decision_path": result.decision_path,
        "model_used": result.model_used,
        "action_needed": result.action_needed,
        "is_automated": result.is_automated,
        "sender_role": result.sender_role,
        "matched_features": result.matched_features,
        "ambiguity_reasons": result.ambiguity_reasons,
        "fallback_reason": result.fallback_reason,
    }


def _candidate_from_event(event: EmailEvent) -> EmailCandidate:
    raw_urls = tuple(url for url in [event.action_url] if url)
    return EmailCandidate(
        subject=event.subject or "",
        body=event.body or event.snippet or "",
        sender=event.sender or "",
        sender_email=event.sender_email or "",
        received_at=event.received_at,
        raw_candidate_urls=raw_urls,
    )


async def load_email_events_for_dry_run(
    db: AsyncSession,
    options: GmailDbDryRunOptions,
) -> list[EmailEvent]:
    stmt = select(EmailEvent).order_by(EmailEvent.received_at.desc().nullslast(), EmailEvent.id.desc()).limit(options.limit)
    if options.user_id:
        stmt = stmt.where(EmailEvent.user_id == options.user_id)
    if not options.include_hidden:
        stmt = stmt.where(EmailEvent.hidden.is_(False))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def analyze_email_event_for_dry_run(
    event: EmailEvent,
    *,
    ai_consent: bool = True,
    include_redacted_body_preview: bool = True,
) -> dict[str, Any]:
    candidate = _candidate_from_event(event)
    analysis = await analyze_email(candidate, ai_enabled=False, ai_consent=ai_consent)
    preflight = evaluate_llm_preflight(candidate, ai_consent=ai_consent, thresholds=analysis.thresholds)
    redacted = redact_email_for_llm(analysis.normalized)
    redacted_preview = None
    if include_redacted_body_preview:
        redacted_preview = {
            "sender": redacted.sender,
            "sender_email": redacted.sender_email,
            "subject": redacted.subject,
            "body_preview": redacted.body[:1000],
        }

    existing_route = _route_for_classification(event.classification)
    hybrid_route = _route_for_classification(analysis.result.classification)
    needs_manual_review = bool(
        preflight.should_call_llm
        or preflight.blocked
        or existing_route != hybrid_route
        or (event.classification and event.classification != analysis.result.classification)
        or analysis.result.confidence_band != "high"
    )
    prompt_preview = preflight.redacted_prompt[:1600] if preflight.redacted_prompt else None
    prompt_leaks = detect_prompt_leaks(prompt_preview)

    return {
        "event_ref": _hash_value(event.id, prefix="email_"),
        "user_ref": _hash_value(event.user_id, prefix="user_"),
        "gmail_message_ref": _hash_value(event.gmail_message_id, prefix="gmail_"),
        "thread_ref": _hash_value(event.thread_id, prefix="thread_"),
        "received_at": event.received_at.isoformat() if isinstance(event.received_at, datetime) else None,
        "sender_domain": event.sender_domain,
        "sender_ref": _hash_value(event.sender_email, prefix="sender_"),
        "existing": {
            "classification": event.classification,
            "route": existing_route,
            "email_type": event.email_type,
            "confidence": event.confidence,
            "action_needed": event.action_needed,
            "is_human": event.is_human,
        },
        "hybrid": {
            **_classification_dict(analysis.result),
            "route": hybrid_route,
            "scores": {
                "job_signal_score": analysis.scores.job_signal_score,
                "noise_score": analysis.scores.noise_score,
                "top_category": analysis.scores.top_category,
                "top_score": analysis.scores.top_score,
                "second_score": analysis.scores.second_score,
                "margin": analysis.scores.margin,
                "category_scores": analysis.scores.category_scores,
            },
        },
        "preflight": {
            "would_call_llm": preflight.should_call_llm,
            "blocked": preflight.blocked,
            "block_reason": preflight.block_reason,
            "prompt_injection_score": preflight.prompt_injection_score,
            "prompt_injection_reasons": preflight.prompt_injection_reasons,
            "redaction_counts": preflight.redaction_counts,
            "redaction_reasons": preflight.redaction_reasons,
            "leak_findings": sorted(set(preflight.leak_findings + prompt_leaks)),
            "prompt_preview": prompt_preview,
        },
        "redacted_email_preview": redacted_preview,
        "needs_manual_review": needs_manual_review,
        "review_reasons": _review_reasons(event, analysis.result, preflight, existing_route, hybrid_route),
    }


def _review_reasons(
    event: EmailEvent,
    result: HybridClassificationResult,
    preflight,
    existing_route: str,
    hybrid_route: str,
) -> list[str]:
    reasons: list[str] = []
    if preflight.should_call_llm:
        reasons.append("would_call_llm")
    if preflight.blocked:
        reasons.append(f"preflight_blocked:{preflight.block_reason}")
    if existing_route != hybrid_route:
        reasons.append("route_changed")
    if event.classification and event.classification != result.classification:
        reasons.append("classification_changed")
    if result.confidence_band != "high":
        reasons.append(f"confidence_band:{result.confidence_band}")
    return reasons


def summarize_dry_run(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(case_results)
    existing_counts = Counter(case["existing"]["classification"] or "unknown" for case in case_results)
    hybrid_counts = Counter(case["hybrid"]["classification"] for case in case_results)
    decision_paths = Counter(case["hybrid"]["decision_path"] for case in case_results)
    route_changes = sum(1 for case in case_results if case["existing"]["route"] != case["hybrid"]["route"])
    classification_changes = sum(
        1
        for case in case_results
        if case["existing"]["classification"] and case["existing"]["classification"] != case["hybrid"]["classification"]
    )
    would_call = sum(1 for case in case_results if case["preflight"]["would_call_llm"])
    blocked = sum(1 for case in case_results if case["preflight"]["blocked"])
    leaks = sum(1 for case in case_results if case["preflight"]["leak_findings"])
    manual_review = sum(1 for case in case_results if case["needs_manual_review"])

    redaction_counts: Counter[str] = Counter()
    review_reasons: Counter[str] = Counter()
    for case in case_results:
        redaction_counts.update(case["preflight"]["redaction_counts"])
        review_reasons.update(case["review_reasons"])

    return {
        "event_count": count,
        "existing_classification_counts": dict(sorted(existing_counts.items())),
        "hybrid_classification_counts": dict(sorted(hybrid_counts.items())),
        "hybrid_decision_path_counts": dict(sorted(decision_paths.items())),
        "route_change_count": route_changes,
        "route_change_rate": round(route_changes / count, 4) if count else 0,
        "classification_change_count": classification_changes,
        "classification_change_rate": round(classification_changes / count, 4) if count else 0,
        "would_call_llm_count": would_call,
        "would_call_llm_rate": round(would_call / count, 4) if count else 0,
        "preflight_blocked_count": blocked,
        "preflight_blocked_rate": round(blocked / count, 4) if count else 0,
        "prompt_leak_count": leaks,
        "prompt_leak_rate": round(leaks / count, 4) if count else 0,
        "manual_review_count": manual_review,
        "manual_review_rate": round(manual_review / count, 4) if count else 0,
        "aggregate_redaction_counts": dict(sorted(redaction_counts.items())),
        "review_reason_counts": dict(sorted(review_reasons.items())),
        "model_call_count": 0,
    }


async def run_db_gmail_dry_run(
    db: AsyncSession,
    options: GmailDbDryRunOptions,
) -> dict[str, Any]:
    events = await load_email_events_for_dry_run(db, options)
    case_results = [
        await analyze_email_event_for_dry_run(
            event,
            ai_consent=options.ai_consent,
            include_redacted_body_preview=options.include_redacted_body_preview,
        )
        for event in events
    ]
    manual_queue = [case for case in case_results if case["needs_manual_review"]][: options.manual_review_limit]
    return {
        "case_results": case_results,
        "manual_label_queue": manual_queue,
        "summary": summarize_dry_run(case_results),
        "options": {
            "user_id": str(options.user_id) if options.user_id else None,
            "limit": options.limit,
            "include_hidden": options.include_hidden,
            "ai_consent": options.ai_consent,
            "include_redacted_body_preview": options.include_redacted_body_preview,
            "manual_review_limit": options.manual_review_limit,
        },
    }


def render_db_dry_run_review(result: dict[str, Any]) -> str:
    summary = result["summary"]
    lines = [
        "# Gmail Classifier DB Dry Run Review",
        "",
        "This artifact is generated from local stored `email_events` rows. It does not call an LLM and does not include raw email bodies.",
        "",
        "## Summary",
        "",
        "```json",
        json.dumps(summary, indent=2, sort_keys=True, default=str),
        "```",
        "",
        "## Manual Review Queue",
        "",
    ]
    for case in result["manual_label_queue"]:
        lines.extend(
            [
                f"### {case['event_ref']}",
                "",
                f"- sender_domain: {case.get('sender_domain') or 'unknown'}",
                f"- existing: {case['existing']['classification']} -> {case['existing']['route']}",
                f"- hybrid: {case['hybrid']['classification']} -> {case['hybrid']['route']}",
                f"- confidence: {case['hybrid']['confidence']} ({case['hybrid']['confidence_band']})",
                f"- decision_path: {case['hybrid']['decision_path']}",
                f"- review_reasons: {', '.join(case['review_reasons']) or 'none'}",
                f"- would_call_llm: {case['preflight']['would_call_llm']}",
                f"- preflight_blocked: {case['preflight']['blocked']}",
                f"- block_reason: {case['preflight']['block_reason'] or 'none'}",
                f"- redaction_counts: {json.dumps(case['preflight']['redaction_counts'], sort_keys=True)}",
                f"- leak_findings: {', '.join(case['preflight']['leak_findings']) or 'none'}",
                "",
            ]
        )
        preview = case.get("redacted_email_preview")
        if preview:
            lines.extend(
                [
                    "Redacted email preview:",
                    "",
                    "```text",
                    f"From: {preview['sender']} <{preview['sender_email']}>",
                    f"Subject: {preview['subject']}",
                    "",
                    preview["body_preview"],
                    "```",
                    "",
                ]
            )
        prompt = case["preflight"].get("prompt_preview")
        if prompt:
            lines.extend(["Would-be LLM prompt preview:", "", "```text", prompt, "```", ""])
    return "\n".join(lines).rstrip() + "\n"


def write_db_dry_run_artifacts(result: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(result["summary"], indent=2, sort_keys=True, default=str), encoding="utf-8")
    (output_dir / "options.json").write_text(json.dumps(result["options"], indent=2, sort_keys=True, default=str), encoding="utf-8")
    (output_dir / "trace.jsonl").write_text(
        "".join(json.dumps(case, sort_keys=True, default=str) + "\n" for case in result["case_results"]),
        encoding="utf-8",
    )
    (output_dir / "manual_label_queue.jsonl").write_text(
        "".join(json.dumps(case, sort_keys=True, default=str) + "\n" for case in result["manual_label_queue"]),
        encoding="utf-8",
    )
    (output_dir / "review.md").write_text(render_db_dry_run_review(result), encoding="utf-8")
    (output_dir / "README.md").write_text(
        "# Gmail Classifier DB Dry Run\n\n"
        "Generated from local `email_events` rows. No LLM calls are made. "
        "Artifacts are redacted, but they are still derived from private email data and should stay under `audit/runs`.\n",
        encoding="utf-8",
    )
    return output_dir
