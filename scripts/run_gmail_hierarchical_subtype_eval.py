from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, f1_score
    from sklearn.model_selection import GroupShuffleSplit, StratifiedShuffleSplit
    from sklearn.pipeline import Pipeline
except Exception as exc:  # pragma: no cover - local tooling dependency
    raise SystemExit(
        "scikit-learn is required for Gmail hierarchical subtype eval. "
        f"Import error: {type(exc).__name__}: {exc}"
    ) from exc


REAL_LABEL_FILE = Path(
    "audit/runs/gmail_labeling_sample/2026-05-12T20-40-container/label_queue_priority_policy_corrected.csv"
)
KAGGLE_FILE = Path(
    "audit/runs/external_datasets/kaggle_job_application_email/job_app_confirmation_emails_anonymized.csv"
)
DEFAULT_OUTPUT_ROOT = Path("audit/runs/gmail_hierarchical_subtype_eval")
RANDOM_SEED = 42
N_SPLITS = 5

ROUTES = ["action_review", "application_inbox", "conversation", "filter", "opportunity_discovery"]
APPLICATION_SUBTYPES = {
    "application_received",
    "application_status_update",
    "assessment_or_task",
    "document_request",
    "interview_request",
    "offer",
    "rejection",
}

PREDICTION_COLUMNS = [
    "split_family",
    "split_id",
    "strategy",
    "row_id",
    "case_id",
    "sender_domain",
    "source_account_group",
    "expected_route",
    "expected_subtype",
    "predicted_route",
    "predicted_subtype",
    "route_correct",
    "subtype_correct",
    "full_correct",
]


@dataclass(frozen=True)
class ConstantModel:
    label: str

    def predict(self, values: list[str]) -> list[str]:
        return [self.label for _ in values]


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _clean_cell(value: Any) -> str:
    return " ".join(str(value or "").split())


def _normalize_label(value: Any) -> str:
    cleaned = _clean_cell(value).lower()
    cleaned = re.sub(r"[\s-]+", "_", cleaned)
    cleaned = re.sub(r"[^a-z0-9_]+", "", cleaned)
    return re.sub(r"_+", "_", cleaned).strip("_")


def _normalize_route_label(value: Any) -> str:
    route = _normalize_label(value)
    if route in {"inbox", "application"}:
        return "application_inbox"
    return route


def _domain_token(value: str) -> str:
    cleaned = _normalize_label(value.replace(".", "_"))
    return f"sender_domain_{cleaned}" if cleaned else "sender_domain_unknown"


def _account_group(row: dict[str, str]) -> str:
    return _clean_cell(row.get("account_label")) or _clean_cell(row.get("account_role")) or "unknown_account"


def _text_for_lr(row: dict[str, str], *, include_domain: bool = True) -> str:
    fields = [
        row.get("redacted_subject", ""),
        row.get("redacted_snippet", ""),
        row.get("redacted_body_preview", ""),
    ]
    if include_domain:
        fields.append(_domain_token(row.get("sender_domain", "")))
    return " ".join(_clean_cell(field) for field in fields if _clean_cell(field))


def _kaggle_text_for_lr(row: dict[str, str], *, include_domain: bool = True) -> str:
    fields = [row.get("subject", ""), row.get("email_body", "")]
    if include_domain:
        fields.append(_domain_token(_clean_cell(row.get("sender")).split("@")[-1]))
    return " ".join(_clean_cell(field) for field in fields if _clean_cell(field))


def _pipeline(*, min_df: int = 1) -> Pipeline:
    return Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    lowercase=True,
                    strip_accents="unicode",
                    ngram_range=(1, 2),
                    min_df=min_df,
                    max_df=0.95,
                    sublinear_tf=True,
                ),
            ),
            (
                "lr",
                LogisticRegression(
                    max_iter=2000,
                    class_weight="balanced",
                    solver="liblinear",
                    random_state=RANDOM_SEED,
                ),
            ),
        ]
    )


def _fit_classifier(texts: list[str], labels: list[str]) -> Pipeline | ConstantModel | None:
    label_counts = Counter(labels)
    if not labels:
        return None
    if len(label_counts) == 1:
        return ConstantModel(next(iter(label_counts)))
    model = _pipeline(min_df=1)
    model.fit(texts, labels)
    return model


def _predict(model: Pipeline | ConstantModel | None, texts: list[str], *, fallback: str) -> list[str]:
    if model is None:
        return [fallback for _ in texts]
    return list(model.predict(texts))


def load_real_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        source_rows = list(csv.DictReader(handle))

    rows: list[dict[str, str]] = []
    for index, raw in enumerate(source_rows, start=1):
        expected_route = _normalize_route_label(raw.get("expected_route"))
        expected_subtype = _normalize_label(raw.get("expected_subtype"))
        if not expected_route or not expected_subtype:
            continue
        case_id = _clean_cell(raw.get("case_id")) or f"row_{index}"
        account_group = _account_group(raw)
        rows.append(
            {
                "row_id": f"real:{index}:{case_id}",
                "source_row_number": str(index),
                "case_id": case_id,
                "sender_domain": _clean_cell(raw.get("sender_domain")).lower(),
                "source_account_group": account_group,
                "redacted_subject": _clean_cell(raw.get("redacted_subject")),
                "redacted_snippet": _clean_cell(raw.get("redacted_snippet")),
                "redacted_body_preview": _clean_cell(raw.get("redacted_body_preview")),
                "predicted_route": _normalize_route_label(raw.get("predicted_route")),
                "predicted_subtype": _normalize_label(raw.get("predicted_subtype")),
                "expected_route": expected_route,
                "expected_subtype": expected_subtype,
            }
        )
    return rows


def random_splits(rows: list[dict[str, str]]) -> list[tuple[str, list[int], list[int], dict[str, Any]]]:
    y = [row["expected_route"] for row in rows]
    splitter = StratifiedShuffleSplit(n_splits=N_SPLITS, test_size=0.25, random_state=RANDOM_SEED)
    return [
        (f"random_stratified_{index}", list(train), list(test), {})
        for index, (train, test) in enumerate(splitter.split(range(len(rows)), y), start=1)
    ]


def grouped_splits(
    rows: list[dict[str, str]], *, group_key: str, family: str
) -> list[tuple[str, list[int], list[int], dict[str, Any]]]:
    groups = [row[group_key] or "unknown" for row in rows]
    unique_groups = sorted(set(groups))
    if len(unique_groups) < 2:
        return []
    splitter = GroupShuffleSplit(
        n_splits=N_SPLITS,
        test_size=0.25 if len(unique_groups) >= 10 else 0.34,
        random_state=RANDOM_SEED,
    )
    output = []
    for index, (train, test) in enumerate(splitter.split(range(len(rows)), groups=groups), start=1):
        train_groups = {groups[item] for item in train}
        test_groups = {groups[item] for item in test}
        output.append(
            (
                f"{family}_{index}",
                list(train),
                list(test),
                {
                    "group_key": group_key,
                    "unique_group_count": len(unique_groups),
                    "train_group_count": len(train_groups),
                    "test_group_count": len(test_groups),
                    "group_overlap_count": len(train_groups & test_groups),
                },
            )
        )
    return output


def _combo(route: str, subtype: str) -> str:
    return f"{route}::{subtype}"


def _split_combo(value: str) -> tuple[str, str]:
    route, _, subtype = value.partition("::")
    return route, subtype


def _majority_subtype(rows: list[dict[str, str]], *, route: str | None = None) -> str:
    candidates = [row["expected_subtype"] for row in rows if route is None or row["expected_route"] == route]
    if not candidates:
        candidates = [row["expected_subtype"] for row in rows]
    return Counter(candidates).most_common(1)[0][0]


def _fit_route_subtype_models(
    rows: list[dict[str, str]], train_indices: list[int]
) -> tuple[Pipeline | ConstantModel | None, dict[str, Pipeline | ConstantModel | None], dict[str, str]]:
    train_rows = [rows[index] for index in train_indices]
    route_model = _fit_classifier(
        [_text_for_lr(row) for row in train_rows],
        [row["expected_route"] for row in train_rows],
    )
    subtype_models: dict[str, Pipeline | ConstantModel | None] = {}
    subtype_fallbacks: dict[str, str] = {}
    for route in sorted(set(row["expected_route"] for row in train_rows)):
        route_rows = [row for row in train_rows if row["expected_route"] == route]
        subtype_fallbacks[route] = _majority_subtype(train_rows, route=route)
        subtype_models[route] = _fit_classifier(
            [_text_for_lr(row) for row in route_rows],
            [row["expected_subtype"] for row in route_rows],
        )
    subtype_fallbacks["__global__"] = _majority_subtype(train_rows)
    return route_model, subtype_models, subtype_fallbacks


def _heuristic_predictions(rows: list[dict[str, str]], test_indices: list[int]) -> list[tuple[str, str]]:
    return [(rows[index]["predicted_route"], rows[index]["predicted_subtype"]) for index in test_indices]


def _global_combo_predictions(
    rows: list[dict[str, str]], train_indices: list[int], test_indices: list[int]
) -> list[tuple[str, str]]:
    train_rows = [rows[index] for index in train_indices]
    model = _fit_classifier(
        [_text_for_lr(row) for row in train_rows],
        [_combo(row["expected_route"], row["expected_subtype"]) for row in train_rows],
    )
    fallback = _combo(
        Counter(row["expected_route"] for row in train_rows).most_common(1)[0][0],
        _majority_subtype(train_rows),
    )
    combo_predictions = _predict(model, [_text_for_lr(rows[index]) for index in test_indices], fallback=fallback)
    return [_split_combo(value) for value in combo_predictions]


def _global_route_global_subtype_predictions(
    rows: list[dict[str, str]], train_indices: list[int], test_indices: list[int]
) -> list[tuple[str, str]]:
    train_rows = [rows[index] for index in train_indices]
    route_model = _fit_classifier(
        [_text_for_lr(row) for row in train_rows],
        [row["expected_route"] for row in train_rows],
    )
    subtype_model = _fit_classifier(
        [_text_for_lr(row) for row in train_rows],
        [row["expected_subtype"] for row in train_rows],
    )
    route_fallback = Counter(row["expected_route"] for row in train_rows).most_common(1)[0][0]
    subtype_fallback = _majority_subtype(train_rows)
    texts = [_text_for_lr(rows[index]) for index in test_indices]
    return list(
        zip(
            _predict(route_model, texts, fallback=route_fallback),
            _predict(subtype_model, texts, fallback=subtype_fallback),
        )
    )


def _hierarchical_predictions(
    rows: list[dict[str, str]],
    train_indices: list[int],
    test_indices: list[int],
    *,
    oracle_route: bool,
) -> list[tuple[str, str]]:
    train_rows = [rows[index] for index in train_indices]
    route_model, subtype_models, subtype_fallbacks = _fit_route_subtype_models(rows, train_indices)
    route_fallback = Counter(row["expected_route"] for row in train_rows).most_common(1)[0][0]
    texts = [_text_for_lr(rows[index]) for index in test_indices]
    predicted_routes = (
        [rows[index]["expected_route"] for index in test_indices]
        if oracle_route
        else _predict(route_model, texts, fallback=route_fallback)
    )
    predictions: list[tuple[str, str]] = []
    for text, route in zip(texts, predicted_routes):
        model = subtype_models.get(route)
        subtype = _predict(model, [text], fallback=subtype_fallbacks.get(route, subtype_fallbacks["__global__"]))[0]
        predictions.append((route, subtype))
    return predictions


def _metrics(rows: list[dict[str, str]], test_indices: list[int], predictions: list[tuple[str, str]]) -> dict[str, Any]:
    true_routes = [rows[index]["expected_route"] for index in test_indices]
    true_subtypes = [rows[index]["expected_subtype"] for index in test_indices]
    pred_routes = [route for route, _ in predictions]
    pred_subtypes = [subtype for _, subtype in predictions]
    full_correct = [
        true_route == pred_route and true_subtype == pred_subtype
        for true_route, true_subtype, pred_route, pred_subtype in zip(
            true_routes, true_subtypes, pred_routes, pred_subtypes
        )
    ]
    by_route: dict[str, dict[str, Any]] = {}
    for route in sorted(set(true_routes)):
        indices = [idx for idx, true_route in enumerate(true_routes) if true_route == route]
        by_route[route] = {
            "n": len(indices),
            "subtype_accuracy": round(
                accuracy_score([true_subtypes[idx] for idx in indices], [pred_subtypes[idx] for idx in indices]), 6
            ),
            "full_accuracy": round(mean(1.0 if full_correct[idx] else 0.0 for idx in indices), 6),
        }
    return {
        "n": len(test_indices),
        "route_accuracy": round(float(accuracy_score(true_routes, pred_routes)), 6),
        "route_macro_f1": round(float(f1_score(true_routes, pred_routes, labels=ROUTES, average="macro", zero_division=0)), 6),
        "subtype_accuracy": round(float(accuracy_score(true_subtypes, pred_subtypes)), 6),
        "subtype_macro_f1": round(
            float(f1_score(true_subtypes, pred_subtypes, average="macro", zero_division=0)), 6
        ),
        "full_route_subtype_accuracy": round(mean(1.0 if item else 0.0 for item in full_correct), 6),
        "by_expected_route": by_route,
    }


def _append_predictions(
    prediction_rows: list[dict[str, Any]],
    rows: list[dict[str, str]],
    test_indices: list[int],
    predictions: list[tuple[str, str]],
    *,
    split_family: str,
    split_id: str,
    strategy: str,
) -> None:
    for index, (pred_route, pred_subtype) in zip(test_indices, predictions):
        row = rows[index]
        prediction_rows.append(
            {
                "split_family": split_family,
                "split_id": split_id,
                "strategy": strategy,
                "row_id": row["row_id"],
                "case_id": row["case_id"],
                "sender_domain": row["sender_domain"],
                "source_account_group": row["source_account_group"],
                "expected_route": row["expected_route"],
                "expected_subtype": row["expected_subtype"],
                "predicted_route": pred_route,
                "predicted_subtype": pred_subtype,
                "route_correct": str(row["expected_route"] == pred_route).lower(),
                "subtype_correct": str(row["expected_subtype"] == pred_subtype).lower(),
                "full_correct": str(row["expected_route"] == pred_route and row["expected_subtype"] == pred_subtype).lower(),
            }
        )


def _summarize_folds(folds: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    keys = [
        "route_accuracy",
        "route_macro_f1",
        "subtype_accuracy",
        "subtype_macro_f1",
        "full_route_subtype_accuracy",
    ]
    route_keys = ["application_inbox", "conversation", "filter", "action_review"]
    strategies = sorted({strategy for fold in folds for strategy in fold["metrics"]})
    summary: dict[str, dict[str, Any]] = {}
    for strategy in strategies:
        summary[strategy] = {}
        for key in keys:
            values = [fold["metrics"][strategy][key] for fold in folds if strategy in fold["metrics"]]
            summary[strategy][key] = {
                "mean": round(float(mean(values)), 6),
                "std": round(float(pstdev(values)), 6) if len(values) > 1 else 0.0,
                "min": round(float(min(values)), 6),
                "max": round(float(max(values)), 6),
            }
        for route in route_keys:
            values = [
                fold["metrics"][strategy]["by_expected_route"][route]["subtype_accuracy"]
                for fold in folds
                if strategy in fold["metrics"] and route in fold["metrics"][strategy]["by_expected_route"]
            ]
            summary[strategy][f"{route}_subtype_accuracy"] = (
                {
                    "mean": round(float(mean(values)), 6),
                    "std": round(float(pstdev(values)), 6) if len(values) > 1 else 0.0,
                    "min": round(float(min(values)), 6),
                    "max": round(float(max(values)), 6),
                }
                if values
                else None
            )
    return summary


def run_real_eval(rows: list[dict[str, str]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    split_plan = {
        "random_stratified": random_splits(rows),
        "sender_domain_grouped": grouped_splits(rows, group_key="sender_domain", family="sender_domain_grouped"),
        "source_account_grouped": grouped_splits(
            rows, group_key="source_account_group", family="source_account_grouped"
        ),
    }
    prediction_rows: list[dict[str, Any]] = []
    output: dict[str, Any] = {}
    for family, splits in split_plan.items():
        folds = []
        for split_id, train_indices, test_indices, split_meta in splits:
            strategies = {
                "heuristic_current": _heuristic_predictions(rows, test_indices),
                "global_combo_lr": _global_combo_predictions(rows, train_indices, test_indices),
                "global_route_global_subtype_lr": _global_route_global_subtype_predictions(
                    rows, train_indices, test_indices
                ),
                "hierarchical_predicted_route_lr": _hierarchical_predictions(
                    rows, train_indices, test_indices, oracle_route=False
                ),
                "hierarchical_oracle_route_subtype_lr": _hierarchical_predictions(
                    rows, train_indices, test_indices, oracle_route=True
                ),
            }
            fold_metrics = {}
            for strategy, predictions in strategies.items():
                fold_metrics[strategy] = _metrics(rows, test_indices, predictions)
                _append_predictions(
                    prediction_rows,
                    rows,
                    test_indices,
                    predictions,
                    split_family=family,
                    split_id=split_id,
                    strategy=strategy,
                )
            folds.append(
                {
                    "split_id": split_id,
                    "train_n": len(train_indices),
                    "test_n": len(test_indices),
                    "train_route_counts": dict(Counter(rows[index]["expected_route"] for index in train_indices)),
                    "test_route_counts": dict(Counter(rows[index]["expected_route"] for index in test_indices)),
                    "test_combo_counts": dict(
                        Counter(_combo(rows[index]["expected_route"], rows[index]["expected_subtype"]) for index in test_indices)
                    ),
                    **split_meta,
                    "metrics": fold_metrics,
                }
            )
        output[family] = {"folds": folds, "aggregate": _summarize_folds(folds)}
    return output, prediction_rows


def _weak_kaggle_subtype(row: dict[str, str]) -> tuple[str, str]:
    subject = _clean_cell(row.get("subject"))
    body = _clean_cell(row.get("email_body"))
    text = f"{subject} {body}".lower()
    if re.search(r"\b(unfortunately|not moving forward|not selected|other candidates|decided to pursue|decline)\b", text):
        return "rejection", "rejection_phrase"
    if re.search(r"\b(interview|schedule a call|phone screen|calendly|availability|meet with|zoom|teams)\b", text):
        return "interview_request", "interview_or_scheduler_phrase"
    if re.search(r"\b(assessment|coding challenge|take[- ]?home|hackerrank|technical screen|complete the test)\b", text):
        return "assessment_or_task", "assessment_phrase"
    if re.search(r"\b(transcript|document|work authorization|portfolio|references|background check)\b", text):
        return "document_request", "document_phrase"
    if re.search(r"\b(status|under review|reviewing your application|next step|next steps|update)\b", text):
        return "application_status_update", "status_phrase"
    if re.search(r"\b(thank you for applying|thanks for applying|received your application|application.*received|successfully submitted|we got your application)\b", text):
        return "application_received", "received_phrase"
    return "unknown_other", "no_weak_pattern"


def load_kaggle_weak_rows(path: Path) -> tuple[list[dict[str, str]], dict[str, Any]]:
    if not path.exists():
        return [], {"available": False, "path": str(path)}
    with path.open(newline="", encoding="utf-8") as handle:
        source_rows = list(csv.DictReader(handle))
    rows: list[dict[str, str]] = []
    for index, raw in enumerate(source_rows, start=1):
        subtype, reason = _weak_kaggle_subtype(raw)
        sender = _clean_cell(raw.get("sender"))
        rows.append(
            {
                "row_id": f"kaggle:{index}",
                "subject": _clean_cell(raw.get("subject")),
                "body": _clean_cell(raw.get("email_body")),
                "sender_domain": sender.split("@")[-1].lower() if "@" in sender else sender.lower(),
                "expected_route": "application_inbox",
                "expected_subtype": subtype,
                "weak_label_reason": reason,
                "text": _kaggle_text_for_lr(raw),
            }
        )
    return rows, {
        "available": True,
        "path": str(path),
        "rows_total": len(rows),
        "weak_subtype_counts": dict(sorted(Counter(row["expected_subtype"] for row in rows).items())),
        "weak_label_reason_counts": dict(sorted(Counter(row["weak_label_reason"] for row in rows).items())),
    }


def run_kaggle_application_subtype_probe(
    kaggle_rows: list[dict[str, str]], real_rows: list[dict[str, str]]
) -> dict[str, Any]:
    known_kaggle = [row for row in kaggle_rows if row["expected_subtype"] in APPLICATION_SUBTYPES]
    real_application = [row for row in real_rows if row["expected_route"] == "application_inbox"]
    if len(known_kaggle) < 2 or len(set(row["expected_subtype"] for row in known_kaggle)) < 2 or not real_application:
        return {"available": False, "reason": "insufficient_kaggle_or_real_application_rows"}

    model = _fit_classifier([row["text"] for row in known_kaggle], [row["expected_subtype"] for row in known_kaggle])
    fallback = Counter(row["expected_subtype"] for row in known_kaggle).most_common(1)[0][0]
    predictions = _predict(model, [_text_for_lr(row) for row in real_application], fallback=fallback)
    expected = [row["expected_subtype"] for row in real_application]
    return {
        "available": True,
        "training_rows": len(known_kaggle),
        "training_subtype_counts": dict(sorted(Counter(row["expected_subtype"] for row in known_kaggle).items())),
        "real_eval_rows": len(real_application),
        "real_eval_subtype_counts": dict(sorted(Counter(expected).items())),
        "accuracy_on_real_application_inbox_rows": round(float(accuracy_score(expected, predictions)), 6),
        "macro_f1_on_real_application_inbox_rows": round(float(f1_score(expected, predictions, average="macro", zero_division=0)), 6),
        "prediction_counts": dict(sorted(Counter(predictions).items())),
        "confusion": [
            {"expected_subtype": truth, "predicted_subtype": pred, "count": count}
            for (truth, pred), count in Counter(zip(expected, predictions)).most_common()
        ],
        "license_warning": "Kaggle dataset is CC-BY-NC-SA-4.0; treat this as research-only, not production training evidence.",
    }


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _agg_pct(aggregate: dict[str, Any], key: str) -> str:
    value = aggregate.get(key)
    if not isinstance(value, dict):
        return "n/a"
    return f"{value['mean'] * 100:.1f}% +/- {value['std'] * 100:.1f}"


def render_report(metrics: dict[str, Any]) -> str:
    dataset = metrics["dataset"]
    real_eval = metrics["real_eval"]
    lines = [
        "# Gmail Hierarchical Subtype Research Eval",
        "",
        "This is an offline architecture experiment. It does not change production routing.",
        "",
        "## Dataset",
        "",
        f"- Human-labeled real rows: `{dataset['real_rows']}`",
        f"- Sender domains: `{dataset['unique_sender_domains']}`",
        f"- Source/account groups: `{dataset['unique_source_account_groups']}`",
        "",
        "### Route Counts",
        "",
        "| expected_route | count |",
        "| --- | ---: |",
    ]
    for route, count in dataset["expected_route_counts"].items():
        lines.append(f"| {route} | {count} |")
    lines.extend(["", "### Route/Subtype Counts", "", "| expected_route | expected_subtype | count |", "| --- | --- | ---: |"])
    for combo_key, count in dataset["expected_route_subtype_counts"].items():
        route, subtype = _split_combo(combo_key)
        lines.append(f"| {route} | {subtype} | {count} |")

    lines.extend(
        [
            "",
            "## Strategies",
            "",
            "- `heuristic_current`: current heuristic route/subtype output in the labeled CSV.",
            "- `global_combo_lr`: one TF-IDF/LR model predicts a combined `route::subtype` label.",
            "- `global_route_global_subtype_lr`: one global route model plus one global subtype model.",
            "- `hierarchical_predicted_route_lr`: route model first, then route-specific subtype model.",
            "- `hierarchical_oracle_route_subtype_lr`: diagnostic upper bound that uses the true route, then the route-specific subtype model.",
            "",
            "## Split Results",
            "",
            "Values are mean +/- population std across five folds.",
            "",
            "| split | strategy | route acc | route macro F1 | subtype acc | subtype macro F1 | full route+subtype acc | application_inbox subtype acc | conversation subtype acc | filter subtype acc |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    strategy_order = [
        "heuristic_current",
        "global_combo_lr",
        "global_route_global_subtype_lr",
        "hierarchical_predicted_route_lr",
        "hierarchical_oracle_route_subtype_lr",
    ]
    for split_name, split_data in real_eval.items():
        for strategy in strategy_order:
            aggregate = split_data["aggregate"].get(strategy, {})
            lines.append(
                f"| {split_name} | {strategy} | "
                f"{_agg_pct(aggregate, 'route_accuracy')} | "
                f"{_agg_pct(aggregate, 'route_macro_f1')} | "
                f"{_agg_pct(aggregate, 'subtype_accuracy')} | "
                f"{_agg_pct(aggregate, 'subtype_macro_f1')} | "
                f"{_agg_pct(aggregate, 'full_route_subtype_accuracy')} | "
                f"{_agg_pct(aggregate, 'application_inbox_subtype_accuracy')} | "
                f"{_agg_pct(aggregate, 'conversation_subtype_accuracy')} | "
                f"{_agg_pct(aggregate, 'filter_subtype_accuracy')} |"
            )

    kaggle = metrics["kaggle"]
    lines.extend(["", "## Kaggle Application-Inbox Subtype Probe", ""])
    if kaggle["metadata"].get("available"):
        lines.extend(
            [
                f"- External rows: `{kaggle['metadata']['rows_total']}`",
                f"- Weak subtype counts: `{kaggle['metadata']['weak_subtype_counts']}`",
                "- License note: CC-BY-NC-SA-4.0, so this is research-only evidence.",
            ]
        )
        probe = kaggle["application_subtype_probe"]
        if probe.get("available"):
            lines.extend(
                [
                    f"- Weak-labeled application subtype training rows: `{probe['training_rows']}`",
                    f"- Real application_inbox eval rows: `{probe['real_eval_rows']}`",
                    f"- Accuracy on real application_inbox rows: `{_fmt_pct(probe['accuracy_on_real_application_inbox_rows'])}`",
                    f"- Macro F1 on real application_inbox rows: `{_fmt_pct(probe['macro_f1_on_real_application_inbox_rows'])}`",
                    f"- Prediction counts: `{probe['prediction_counts']}`",
                ]
            )
        else:
            lines.append(f"- Probe not available: `{probe.get('reason')}`")
    else:
        lines.append(f"- Kaggle file unavailable at `{kaggle['metadata']['path']}`.")

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- The hierarchical architecture is the right long-term shape, but this labeled set is too small and imbalanced for production submodels.",
            "- The oracle-route row is the important diagnostic: if it improves while predicted-route hierarchy does not, route errors are the bottleneck.",
            "- The Kaggle probe can demonstrate expected application subtype behavior, but weak labels and license constraints prevent treating it as production training data.",
            "- Recommended production decision remains: heuristics in production, LR/subtype models in shadow or research eval until real holdout coverage improves.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-labels", type=Path, default=REAL_LABEL_FILE)
    parser.add_argument("--kaggle-file", type=Path, default=KAGGLE_FILE)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir or DEFAULT_OUTPUT_ROOT / _timestamp()
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = load_real_rows(args.real_labels)
    real_eval, prediction_rows = run_real_eval(rows)
    kaggle_rows, kaggle_metadata = load_kaggle_weak_rows(args.kaggle_file)
    kaggle_probe = run_kaggle_application_subtype_probe(kaggle_rows, rows)
    metrics = {
        "inputs": {
            "real_labels": str(args.real_labels),
            "kaggle_file": str(args.kaggle_file),
        },
        "dataset": {
            "real_rows": len(rows),
            "unique_sender_domains": len({row["sender_domain"] for row in rows}),
            "unique_source_account_groups": len({row["source_account_group"] for row in rows}),
            "expected_route_counts": dict(sorted(Counter(row["expected_route"] for row in rows).items())),
            "expected_subtype_counts": dict(sorted(Counter(row["expected_subtype"] for row in rows).items())),
            "expected_route_subtype_counts": dict(
                sorted(Counter(_combo(row["expected_route"], row["expected_subtype"]) for row in rows).items())
            ),
        },
        "real_eval": real_eval,
        "kaggle": {
            "metadata": kaggle_metadata,
            "application_subtype_probe": kaggle_probe,
        },
    }

    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_csv(output_dir / "predictions.csv", prediction_rows, PREDICTION_COLUMNS)
    (output_dir / "report.md").write_text(render_report(metrics), encoding="utf-8")
    print(f"Wrote Gmail hierarchical subtype eval to {output_dir}")


if __name__ == "__main__":
    main()
