"""Synthetic eval for Gmail classifier LLM preflight safety."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.services.gmail_intelligence.preflight import evaluate_llm_preflight
from backend.services.gmail_intelligence.types import EmailCandidate


@dataclass(frozen=True)
class GmailPreflightExample:
    id: str
    sender: str
    sender_email: str
    subject: str
    body: str
    expected_should_call_llm: bool
    expected_blocked: bool
    expected_block_reason: str | None = None
    ai_consent: bool = True
    forbidden_prompt_terms: tuple[str, ...] = ()
    expected_redaction_keys: tuple[str, ...] = ()
    risk_tags: tuple[str, ...] = ()


def load_preflight_examples(path: Path | str) -> list[GmailPreflightExample]:
    examples: list[GmailPreflightExample] = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        try:
            examples.append(
                GmailPreflightExample(
                    id=payload["id"],
                    sender=payload["sender"],
                    sender_email=payload["sender_email"],
                    subject=payload["subject"],
                    body=payload["body"],
                    expected_should_call_llm=bool(payload["expected_should_call_llm"]),
                    expected_blocked=bool(payload["expected_blocked"]),
                    expected_block_reason=payload.get("expected_block_reason"),
                    ai_consent=bool(payload.get("ai_consent", True)),
                    forbidden_prompt_terms=tuple(payload.get("forbidden_prompt_terms") or ()),
                    expected_redaction_keys=tuple(payload.get("expected_redaction_keys") or ()),
                    risk_tags=tuple(payload.get("risk_tags") or ()),
                )
            )
        except KeyError as exc:
            raise ValueError(f"Invalid Gmail preflight example on line {line_number}: missing {exc}") from exc
    return examples


def _safe_prompt_preview(prompt: str | None) -> str | None:
    if prompt is None:
        return None
    return prompt[:1200]


def render_redacted_prompt_review(case_results: list[dict[str, Any]]) -> str:
    lines = [
        "# Gmail Classifier LLM Preflight Redacted Prompt Review",
        "",
        "This file contains only minimized/redacted prompt previews for cases that would reach the Gmail classifier LLM gate, plus safety decisions for blocked cases. It is designed for human review before any real Gmail dry run.",
        "",
    ]
    for case in case_results:
        actual = case["actual"]
        expected = case["expected"]
        lines.extend(
            [
                f"## {case['case_id']}",
                "",
                f"- passed: {case['passed']}",
                f"- risk_tags: {', '.join(case.get('risk_tags') or ['none'])}",
                f"- should_call_llm: expected={expected['should_call_llm']} actual={actual['should_call_llm']}",
                f"- blocked: expected={expected['blocked']} actual={actual['blocked']}",
                f"- block_reason: {actual.get('block_reason') or 'none'}",
                f"- local_classification: {actual.get('local_classification')}",
                f"- prompt_injection_reasons: {', '.join(actual.get('prompt_injection_reasons') or ['none'])}",
                f"- redaction_counts: {json.dumps(actual.get('redaction_counts') or {}, sort_keys=True)}",
                f"- leak_findings: {', '.join(actual.get('leak_findings') or ['none'])}",
                "",
            ]
        )
        preview = case.get("redacted_prompt_preview")
        if preview:
            lines.extend(["```text", preview, "```", ""])
        else:
            lines.extend(["No prompt preview was generated for this case.", ""])
    return "\n".join(lines).rstrip() + "\n"


def run_preflight_eval(dataset_path: Path | str) -> dict[str, Any]:
    examples = load_preflight_examples(dataset_path)
    case_results: list[dict[str, Any]] = []
    for example in examples:
        candidate = EmailCandidate(
            subject=example.subject,
            body=example.body,
            sender=example.sender,
            sender_email=example.sender_email,
        )
        decision = evaluate_llm_preflight(
            candidate,
            ai_consent=example.ai_consent,
            forbidden_prompt_terms=list(example.forbidden_prompt_terms),
        )
        redaction_missing = [
            key for key in example.expected_redaction_keys if key not in decision.redaction_counts
        ]
        failures: list[str] = []
        if decision.should_call_llm != example.expected_should_call_llm:
            failures.append("wrong_llm_escalation_decision")
        if decision.blocked != example.expected_blocked:
            failures.append("wrong_block_decision")
        if example.expected_block_reason and decision.block_reason != example.expected_block_reason:
            failures.append("wrong_block_reason")
        if decision.leak_findings:
            failures.append("prompt_leak")
        if redaction_missing:
            failures.append("missing_expected_redaction")

        case_results.append(
            {
                "case_id": example.id,
                "expected": {
                    "should_call_llm": example.expected_should_call_llm,
                    "blocked": example.expected_blocked,
                    "block_reason": example.expected_block_reason,
                    "expected_redaction_keys": list(example.expected_redaction_keys),
                },
                "actual": {
                    "should_call_llm": decision.should_call_llm,
                    "blocked": decision.blocked,
                    "block_reason": decision.block_reason,
                    "local_classification": decision.local_classification,
                    "local_decision_path": decision.local_decision_path,
                    "prompt_injection_score": decision.prompt_injection_score,
                    "prompt_injection_reasons": decision.prompt_injection_reasons,
                    "redaction_counts": decision.redaction_counts,
                    "leak_findings": decision.leak_findings,
                    "ambiguity_reasons": decision.ambiguity_reasons,
                    "matched_features": decision.matched_features,
                },
                "risk_tags": list(example.risk_tags),
                "passed": not failures,
                "failure_types": failures,
                "redacted_prompt_preview": _safe_prompt_preview(decision.redacted_prompt),
            }
        )

    count = len(case_results)
    failed = [case for case in case_results if not case["passed"]]
    expected_escalations = sum(1 for case in case_results if case["expected"]["should_call_llm"])
    actual_escalations = sum(1 for case in case_results if case["actual"]["should_call_llm"])
    expected_blocks = sum(1 for case in case_results if case["expected"]["blocked"])
    actual_blocks = sum(1 for case in case_results if case["actual"]["blocked"])
    leak_cases = sum(1 for case in case_results if case["actual"]["leak_findings"])
    redaction_expected = sum(1 for case in case_results if case["expected"]["expected_redaction_keys"])
    redaction_passed = sum(
        1
        for case in case_results
        if case["expected"]["expected_redaction_keys"]
        and not any(failure == "missing_expected_redaction" for failure in case["failure_types"])
    )
    prompt_injection_cases = [
        case for case in case_results if case["actual"]["prompt_injection_reasons"] or case["expected"]["block_reason"] == "prompt_injection_risk"
    ]
    prompt_injection_blocked = sum(1 for case in prompt_injection_cases if case["actual"]["block_reason"] == "prompt_injection_risk")

    failure_counts: dict[str, int] = {}
    for case in failed:
        for failure in case["failure_types"]:
            failure_counts[failure] = failure_counts.get(failure, 0) + 1

    return {
        "dataset_path": str(dataset_path),
        "dataset_version": Path(dataset_path).stem,
        "case_results": case_results,
        "redacted_prompt_review_markdown": render_redacted_prompt_review(case_results),
        "metrics": {
            "case_count": count,
            "pass_rate": round((count - len(failed)) / count, 4) if count else 0,
            "failed_case_count": len(failed),
            "expected_llm_escalation_rate": round(expected_escalations / count, 4) if count else 0,
            "actual_llm_escalation_rate": round(actual_escalations / count, 4) if count else 0,
            "expected_block_rate": round(expected_blocks / count, 4) if count else 0,
            "actual_block_rate": round(actual_blocks / count, 4) if count else 0,
            "prompt_leak_rate": round(leak_cases / count, 4) if count else 0,
            "redaction_pass_rate": round(redaction_passed / redaction_expected, 4) if redaction_expected else 1.0,
            "prompt_injection_block_rate": round(prompt_injection_blocked / len(prompt_injection_cases), 4) if prompt_injection_cases else 1.0,
            "model_call_count": 0,
        },
        "failure_summary": {
            "case_count": count,
            "failed_case_count": len(failed),
            "failure_type_counts": dict(sorted(failure_counts.items())),
            "highest_risk_failure": "prompt_leak" if failure_counts.get("prompt_leak") else next(iter(sorted(failure_counts)), None),
        },
    }
