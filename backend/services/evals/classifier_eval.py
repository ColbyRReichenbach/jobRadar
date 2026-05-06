"""Offline email classifier evaluation."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from backend.services import ai_orchestrator, ai_safety, email_classifier
from backend.services.ai_pricing import estimate_cost_cents
from backend.services.gmail_intelligence.orchestrator import analyze_email
from backend.services.gmail_intelligence.types import EmailCandidate, HybridThresholds

STAGE_BY_CLASSIFICATION = {
    "job_update": "applied",
    "interview_request": "interview",
    "action_item": "assessment",
    "offer": "offer",
    "rejection": "rejection",
    "conversation": "follow_up",
    "not_relevant": "unknown",
}


@dataclass(frozen=True)
class ClassifierExample:
    id: str
    sender: str
    sender_email: str
    subject: str
    body: str
    expected_job_related: bool
    expected_classification: str
    expected_stage: str


@dataclass(frozen=True)
class Prediction:
    example_id: str
    classification: str
    stage: str
    job_related: bool
    latency_ms: float
    cost_estimate_cents: float
    confidence: float | None = None
    model_used: bool = False
    fallback_reason: str | None = None
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    retry_count: int = 0
    safety_status: str | None = None
    decision_path: str | None = None
    matched_features: list[str] | None = None
    ambiguity_reasons: list[str] | None = None
    redaction_applied: bool = False
    redaction_counts: dict[str, int] | None = None


def load_examples(path: Path | str) -> list[ClassifierExample]:
    examples: list[ClassifierExample] = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        try:
            examples.append(ClassifierExample(**payload))
        except TypeError as exc:
            raise ValueError(f"Invalid classifier eval example on line {line_number}") from exc
    return examples


def stage_from_classification(classification: str) -> str:
    return STAGE_BY_CLASSIFICATION.get(classification, "unknown")


async def fallback_rules_predict(example: ClassifierExample) -> Prediction:
    started = time.perf_counter()
    result = await email_classifier.classify_email(
        subject=example.subject,
        body=example.body,
        sender=example.sender,
        sender_email=example.sender_email,
        ai_enabled=False,
    )
    classification = str(result.get("classification") or "not_relevant")
    return Prediction(
        example_id=example.id,
        classification=classification,
        stage=stage_from_classification(classification),
        job_related=classification != "not_relevant",
        latency_ms=round((time.perf_counter() - started) * 1000, 3),
        cost_estimate_cents=0,
        model_used=False,
    )


async def subject_only_baseline_predict(example: ClassifierExample) -> Prediction:
    started = time.perf_counter()
    subject = example.subject.lower()
    if any(token in subject for token in {"interview", "schedule", "onsite"}):
        classification = "interview_request"
    elif any(token in subject for token in {"offer"}):
        classification = "offer"
    elif any(token in subject for token in {"reject", "unfortunately", "not selected"}):
        classification = "rejection"
    elif any(token in subject for token in {"assessment", "complete", "action"}):
        classification = "action_item"
    elif any(token in subject for token in {"application", "status", "applying"}):
        classification = "job_update"
    else:
        classification = "not_relevant"
    return Prediction(
        example_id=example.id,
        classification=classification,
        stage=stage_from_classification(classification),
        job_related=classification != "not_relevant",
        latency_ms=round((time.perf_counter() - started) * 1000, 3),
        cost_estimate_cents=0,
        model_used=False,
    )


def _email_classifier_prompt(example: ClassifierExample) -> str:
    truncated_body = example.body[:4000] if example.body else ""
    return f"""From: {example.sender} <{example.sender_email}>
Subject: {example.subject}

{truncated_body}"""


def _cost_from_tokens(model: str, prompt_tokens: int | None, output_tokens: int | None) -> float:
    _, breakdown = estimate_cost_cents(
        model=model,
        provider="openai",
        prompt_tokens=prompt_tokens,
        output_tokens=output_tokens,
    )
    return round(
        float(breakdown.get("input_cost_cents") or 0)
        + float(breakdown.get("cached_input_cost_cents") or 0)
        + float(breakdown.get("output_cost_cents") or 0)
        + float(breakdown.get("reasoning_cost_cents") or 0),
        6,
    )


async def live_llm_predict(example: ClassifierExample) -> Prediction:
    started = time.perf_counter()
    user_prompt = _email_classifier_prompt(example)
    try:
        result = await ai_safety.run_json_task_with_safety(
            email_classifier.CLASSIFIER_TASK,
            user_prompt,
            metadata={
                "surface": "email_classifier_eval",
                "case_id": example.id,
                "dataset_source": "synthetic_or_redacted_eval",
            },
            data_classes=[
                ai_safety.DATA_CLASS_UNTRUSTED_INBOUND,
                ai_safety.DATA_CLASS_CAREER_PRIVATE,
            ],
            allow_identity=True,
            untrusted_input=True,
        )
        normalized = email_classifier._normalize_model_result(  # noqa: SLF001
            result.payload,
            example.subject,
            example.sender_email,
            example.sender,
        )
        if normalized is None:
            fallback = email_classifier._fallback_classify(  # noqa: SLF001
                example.subject,
                example.body,
                example.sender_email,
                sender=example.sender,
            )
            classification = str(fallback.get("classification") or "not_relevant")
            return Prediction(
                example_id=example.id,
                classification=classification,
                stage=stage_from_classification(classification),
                job_related=classification != "not_relevant",
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                cost_estimate_cents=_cost_from_tokens(result.model, result.tokens_in, result.tokens_out),
                model_used=True,
                fallback_reason="invalid_model_payload",
                prompt_tokens=result.tokens_in,
                output_tokens=result.tokens_out,
                retry_count=result.retries,
            )

        classification = str(normalized.get("classification") or "not_relevant")
        return Prediction(
            example_id=example.id,
            classification=classification,
            stage=stage_from_classification(classification),
            job_related=classification != "not_relevant",
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            cost_estimate_cents=_cost_from_tokens(result.model, result.tokens_in, result.tokens_out),
            model_used=True,
            prompt_tokens=result.tokens_in,
            output_tokens=result.tokens_out,
            retry_count=result.retries,
        )
    except ai_safety.AiSafetyQuarantinedError:
        return Prediction(
            example_id=example.id,
            classification="not_relevant",
            stage=stage_from_classification("not_relevant"),
            job_related=False,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            cost_estimate_cents=0,
            model_used=False,
            fallback_reason="safety_quarantine",
            safety_status="quarantined",
        )
    except Exception:
        fallback = email_classifier._fallback_classify(  # noqa: SLF001
            example.subject,
            example.body,
            example.sender_email,
            sender=example.sender,
        )
        classification = str(fallback.get("classification") or "not_relevant")
        return Prediction(
            example_id=example.id,
            classification=classification,
            stage=stage_from_classification(classification),
            job_related=classification != "not_relevant",
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            cost_estimate_cents=0,
            model_used=False,
            fallback_reason="model_task_failure",
        )


async def hybrid_rules_nlp_llm_predict(example: ClassifierExample) -> Prediction:
    started = time.perf_counter()
    candidate = EmailCandidate(
        subject=example.subject,
        body=example.body,
        sender=example.sender,
        sender_email=example.sender_email,
    )
    analysis = await analyze_email(
        candidate,
        thresholds=HybridThresholds(),
        ai_enabled=ai_orchestrator.has_configured_api_key(),
    )
    result = analysis.result
    return Prediction(
        example_id=example.id,
        classification=result.classification,
        stage=stage_from_classification(result.classification),
        job_related=result.job_related,
        latency_ms=round((time.perf_counter() - started) * 1000, 3),
        cost_estimate_cents=result.cost_estimate_cents,
        confidence=result.confidence,
        model_used=result.model_used,
        fallback_reason=result.fallback_reason,
        prompt_tokens=result.prompt_tokens,
        output_tokens=result.output_tokens,
        retry_count=result.retry_count,
        decision_path=result.decision_path,
        matched_features=result.matched_features,
        ambiguity_reasons=result.ambiguity_reasons,
        redaction_applied=result.redaction_applied,
        redaction_counts=result.redaction_counts,
    )


def binary_metrics(y_true: list[bool], y_pred: list[bool]) -> dict[str, float | int]:
    tp = sum(1 for truth, pred in zip(y_true, y_pred) if truth and pred)
    fp = sum(1 for truth, pred in zip(y_true, y_pred) if not truth and pred)
    fn = sum(1 for truth, pred in zip(y_true, y_pred) if truth and not pred)
    tn = sum(1 for truth, pred in zip(y_true, y_pred) if not truth and not pred)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = (tp + tn) / len(y_true) if y_true else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round(accuracy, 4),
    }


def confusion_matrix(examples: list[ClassifierExample], predictions: list[Prediction]) -> dict[str, dict[str, int]]:
    by_id = {prediction.example_id: prediction for prediction in predictions}
    labels = sorted({example.expected_classification for example in examples} | {prediction.classification for prediction in predictions})
    matrix = {label: {inner: 0 for inner in labels} for label in labels}
    for example in examples:
        matrix[example.expected_classification][by_id[example.id].classification] += 1
    return matrix


def score_predictions(examples: list[ClassifierExample], predictions: list[Prediction]) -> dict:
    by_id = {prediction.example_id: prediction for prediction in predictions}
    job_truth = [example.expected_job_related for example in examples]
    job_pred = [by_id[example.id].job_related for example in examples]
    stage_examples = [example for example in examples if example.expected_job_related]
    stage_correct = sum(1 for example in stage_examples if by_id[example.id].stage == example.expected_stage)
    category_correct = sum(1 for example in examples if by_id[example.id].classification == example.expected_classification)
    latencies = sorted(prediction.latency_ms for prediction in predictions)
    p50 = latencies[len(latencies) // 2] if latencies else 0
    p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else 0
    model_call_count = sum(1 for prediction in predictions if prediction.model_used)
    fallback_count = sum(1 for prediction in predictions if prediction.fallback_reason)
    prompt_tokens = sum(prediction.prompt_tokens or 0 for prediction in predictions)
    output_tokens = sum(prediction.output_tokens or 0 for prediction in predictions)
    total_cost = sum(float(prediction.cost_estimate_cents or 0) for prediction in predictions)
    return {
        "example_count": len(examples),
        "job_related": binary_metrics(job_truth, job_pred),
        "category_accuracy": round(category_correct / len(examples), 4) if examples else 0.0,
        "stage_accuracy": round(stage_correct / len(stage_examples), 4) if stage_examples else 0.0,
        "confusion_matrix": confusion_matrix(examples, predictions),
        "model_call_count": model_call_count,
        "model_call_rate": round(model_call_count / len(predictions), 4) if predictions else 0.0,
        "fallback_count": fallback_count,
        "fallback_rate": round(fallback_count / len(predictions), 4) if predictions else 0.0,
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "total_tokens": prompt_tokens + output_tokens,
        "latency": {
            "p50_ms": round(p50, 3),
            "p95_ms": round(p95, 3),
            "avg_ms": round(sum(latencies) / len(latencies), 3) if latencies else 0,
        },
        "cost": {
            "total_cost_cents": round(total_cost, 6),
            "cost_per_1000_emails_cents": round(total_cost * 1000 / len(predictions), 6) if predictions else 0,
        },
    }


async def evaluate_variant(
    examples: list[ClassifierExample],
    predict: Callable[[ClassifierExample], Awaitable[Prediction]],
) -> tuple[list[Prediction], dict]:
    predictions = [await predict(example) for example in examples]
    return predictions, score_predictions(examples, predictions)


async def run_classifier_eval(
    dataset_path: Path | str,
    *,
    include_live_llm: bool = False,
    include_hybrid: bool = False,
) -> dict:
    examples = load_examples(dataset_path)
    fallback_predictions, fallback_metrics = await evaluate_variant(examples, fallback_rules_predict)
    baseline_predictions, baseline_metrics = await evaluate_variant(examples, subject_only_baseline_predict)
    variants = {
        "fallback_rules_v1": {
            "description": "Current deterministic fallback used when model calls are disabled or invalid.",
            "predictions": [asdict(prediction) for prediction in fallback_predictions],
            "metrics": fallback_metrics,
            "model": "fallback-rules",
            "prompt_version": "rules-v1",
        },
        "subject_only_baseline_v1": {
            "description": "Cheap alternate baseline using only subject-line keywords.",
            "predictions": [asdict(prediction) for prediction in baseline_predictions],
            "metrics": baseline_metrics,
            "model": "subject-only-rules",
            "prompt_version": "subject-rules-v1",
        },
    }
    if include_live_llm:
        if not ai_orchestrator.has_configured_api_key():
            raise RuntimeError("OPENAI_API_KEY is required for include_live_llm=True")
        live_predictions, live_metrics = await evaluate_variant(examples, live_llm_predict)
        variants["live_llm_v1"] = {
            "description": "Current production LLM-first Gmail classifier path with safety preflight and rule fallback on invalid/error cases.",
            "predictions": [asdict(prediction) for prediction in live_predictions],
            "metrics": live_metrics,
            "model": email_classifier.CLASSIFIER_MODEL,
            "prompt_version": email_classifier.CLASSIFIER_TASK.prompt_version,
        }
    if include_hybrid:
        hybrid_predictions, hybrid_metrics = await evaluate_variant(examples, hybrid_rules_nlp_llm_predict)
        variants["hybrid_rules_nlp_llm_v1"] = {
            "description": "Hybrid Gmail classifier lane with local NLP/rules scoring, confidence gates, and redacted LLM adjudication only for ambiguous cases.",
            "predictions": [asdict(prediction) for prediction in hybrid_predictions],
            "metrics": hybrid_metrics,
            "model": "hybrid-rules-nlp-llm",
            "prompt_version": HybridThresholds().version,
        }
    return {
        "dataset_path": str(dataset_path),
        "dataset_version": Path(dataset_path).stem,
        "variants": variants,
        "decision_note": "Recall is weighted above precision because a missed job email is higher risk than extra review noise.",
    }


def run_classifier_eval_sync(
    dataset_path: Path | str,
    *,
    include_live_llm: bool = False,
    include_hybrid: bool = False,
) -> dict:
    return asyncio.run(run_classifier_eval(dataset_path, include_live_llm=include_live_llm, include_hybrid=include_hybrid))


def current_git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def build_report_payload(eval_result: dict, *, generated_at: str | None = None, git_sha: str | None = None) -> dict:
    primary = eval_result["variants"]["fallback_rules_v1"]["metrics"]
    baseline = eval_result["variants"]["subject_only_baseline_v1"]["metrics"]
    job_metrics = primary["job_related"]
    return {
        "metadata": {
            "report_type": "email_classifier_eval",
            "title": "Email Classifier Eval",
            "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
            "git_sha": git_sha or current_git_sha(),
            "release_version": "ai-classifier-evals",
            "dataset_version": eval_result["dataset_version"],
            "model": email_classifier.CLASSIFIER_MODEL,
            "prompt_version": email_classifier.CLASSIFIER_TASK.prompt_version,
            "recommendation": "keep_recall_weighted_threshold",
            "decision": "approved_for_demo_artifact",
        },
        "metrics": {
            "example_count": primary["example_count"],
            "precision": job_metrics["precision"],
            "recall": job_metrics["recall"],
            "f1": job_metrics["f1"],
            "category_accuracy": primary["category_accuracy"],
            "stage_accuracy": primary["stage_accuracy"],
            "baseline_subject_only_recall": baseline["job_related"]["recall"],
            "baseline_subject_only_f1": baseline["job_related"]["f1"],
            "false_negatives": job_metrics["fn"],
            "false_positives": job_metrics["fp"],
            "confusion_matrix": primary["confusion_matrix"],
        },
        "token_breakdown": {
            "prompt_tokens": "estimated_per_email",
            "output_tokens": "estimated_per_email",
            "live_model_calls": 0,
        },
        "cost_breakdown": primary["cost"],
        "latency_metrics": primary["latency"],
        "supporting_artifacts": [
            {"label": "Classifier eval dataset", "path": eval_result["dataset_path"]},
            {"label": "Labeling guidelines", "path": "evals/labeling-guidelines.md"},
            {"label": "Dataset governance", "path": "evals/dataset-governance.md"},
        ],
        "notes": [
            eval_result["decision_note"],
            "CI uses deterministic classifier paths and does not call a live model provider.",
            "The subject-only baseline is included to show the value of richer fallback rules before live prompt/model comparisons.",
        ],
    }
