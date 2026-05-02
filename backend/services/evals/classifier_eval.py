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

from backend.services import email_classifier

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
    cost_estimate_cents: int


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
    return {
        "example_count": len(examples),
        "job_related": binary_metrics(job_truth, job_pred),
        "category_accuracy": round(category_correct / len(examples), 4) if examples else 0.0,
        "stage_accuracy": round(stage_correct / len(stage_examples), 4) if stage_examples else 0.0,
        "confusion_matrix": confusion_matrix(examples, predictions),
        "latency": {
            "p50_ms": round(p50, 3),
            "p95_ms": round(p95, 3),
            "avg_ms": round(sum(latencies) / len(latencies), 3) if latencies else 0,
        },
        "cost": {
            "total_cost_cents": sum(prediction.cost_estimate_cents for prediction in predictions),
            "cost_per_1000_emails_cents": round(sum(prediction.cost_estimate_cents for prediction in predictions) * 1000 / len(predictions), 2)
            if predictions
            else 0,
        },
    }


async def evaluate_variant(
    examples: list[ClassifierExample],
    predict: Callable[[ClassifierExample], Awaitable[Prediction]],
) -> tuple[list[Prediction], dict]:
    predictions = [await predict(example) for example in examples]
    return predictions, score_predictions(examples, predictions)


async def run_classifier_eval(dataset_path: Path | str) -> dict:
    examples = load_examples(dataset_path)
    fallback_predictions, fallback_metrics = await evaluate_variant(examples, fallback_rules_predict)
    baseline_predictions, baseline_metrics = await evaluate_variant(examples, subject_only_baseline_predict)
    return {
        "dataset_path": str(dataset_path),
        "dataset_version": Path(dataset_path).stem,
        "variants": {
            "fallback_rules_v1": {
                "description": "Current deterministic fallback used when model calls are disabled or invalid.",
                "predictions": [asdict(prediction) for prediction in fallback_predictions],
                "metrics": fallback_metrics,
            },
            "subject_only_baseline_v1": {
                "description": "Cheap alternate baseline using only subject-line keywords.",
                "predictions": [asdict(prediction) for prediction in baseline_predictions],
                "metrics": baseline_metrics,
            },
        },
        "decision_note": "Recall is weighted above precision because a missed job email is higher risk than extra review noise.",
    }


def run_classifier_eval_sync(dataset_path: Path | str) -> dict:
    return asyncio.run(run_classifier_eval(dataset_path))


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
