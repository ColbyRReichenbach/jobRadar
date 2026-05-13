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
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support
    from sklearn.model_selection import GroupShuffleSplit, StratifiedShuffleSplit
    from sklearn.pipeline import Pipeline
except Exception as exc:  # pragma: no cover - exercised only when local env lacks sklearn
    raise SystemExit(
        "scikit-learn is required for Gmail LR shadow eval. Install sklearn locally or rerun in an env "
        f"with sklearn available. Import error: {type(exc).__name__}: {exc}"
    ) from exc


PRIOR_LABEL_FILE = Path(
    "audit/runs/gmail_combined_real_baseline_3acct_2026-05-07T00-22-23Z/labels/label_queue_priority.csv"
)
NEW_LABEL_FILE = Path(
    "audit/runs/gmail_labeling_sample/2026-05-12T20-40-container/label_queue_priority_policy_corrected.csv"
)
DEFAULT_OUTPUT_ROOT = Path("audit/runs/gmail_lr_shadow_eval")
RANDOM_SEED = 42
N_SPLITS = 5

OUTPUT_COLUMNS = [
    "row_id",
    "source_dataset",
    "source_file",
    "source_row_number",
    "case_id",
    "account_label",
    "account_role",
    "source_account_group",
    "received_at",
    "sender_domain",
    "redacted_sender",
    "redacted_subject",
    "redacted_snippet",
    "redacted_body_preview",
    "predicted_route",
    "predicted_subtype",
    "expected_route",
    "expected_subtype",
    "is_correct",
    "error_bucket",
]

PREDICTION_COLUMNS = [
    "split_family",
    "split_id",
    "strategy",
    "row_id",
    "source_dataset",
    "case_id",
    "source_account_group",
    "sender_domain",
    "expected_route",
    "predicted_route",
    "correct",
]


@dataclass(frozen=True)
class SourceSpec:
    path: Path
    dataset: str


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
    if route == "inbox":
        return "application_inbox"
    return route


def _domain_token(value: str) -> str:
    cleaned = _normalize_label(value.replace(".", "_"))
    return f"sender_domain_{cleaned}" if cleaned else "sender_domain_unknown"


def _account_group(row: dict[str, str]) -> str:
    account_label = _clean_cell(row.get("account_label"))
    account_role = _clean_cell(row.get("account_role"))
    return account_label or account_role or "unknown_account"


def _text_for_lr(row: dict[str, str], *, include_domain: bool) -> str:
    parts = [
        row.get("redacted_subject", ""),
        row.get("redacted_snippet", ""),
        row.get("redacted_body_preview", ""),
    ]
    if include_domain:
        parts.append(_domain_token(row.get("sender_domain", "")))
    return " ".join(_clean_cell(part) for part in parts if _clean_cell(part))


def load_labeled_rows(sources: list[SourceSpec]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    rows: list[dict[str, str]] = []
    skipped: list[dict[str, Any]] = []
    input_summaries: list[dict[str, Any]] = []
    for spec in sources:
        with spec.path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            source_rows = list(reader)
        labeled_count = 0
        for index, raw in enumerate(source_rows, start=1):
            expected_route = _normalize_route_label(raw.get("expected_route"))
            expected_subtype = _normalize_label(raw.get("expected_subtype"))
            if not expected_route or not expected_subtype:
                skipped.append(
                    {
                        "source_file": str(spec.path),
                        "source_dataset": spec.dataset,
                        "source_row_number": index,
                        "reason": "missing_expected_route_or_subtype",
                    }
                )
                continue
            labeled_count += 1
            account_group = _account_group(raw)
            case_id = _clean_cell(raw.get("case_id")) or f"row_{index}"
            row = {
                "row_id": f"{spec.dataset}:{index}:{case_id}",
                "source_dataset": spec.dataset,
                "source_file": str(spec.path),
                "source_row_number": str(index),
                "case_id": case_id,
                "account_label": _clean_cell(raw.get("account_label")),
                "account_role": _clean_cell(raw.get("account_role")),
                "source_account_group": f"{spec.dataset}:{account_group}",
                "received_at": _clean_cell(raw.get("received_at")),
                "sender_domain": _clean_cell(raw.get("sender_domain")).lower(),
                "redacted_sender": _clean_cell(raw.get("redacted_sender")),
                "redacted_subject": _clean_cell(raw.get("redacted_subject")),
                "redacted_snippet": _clean_cell(raw.get("redacted_snippet")),
                "redacted_body_preview": _clean_cell(raw.get("redacted_body_preview")),
                "predicted_route": _normalize_route_label(raw.get("predicted_route")),
                "predicted_subtype": _normalize_label(raw.get("predicted_subtype")),
                "expected_route": expected_route,
                "expected_subtype": expected_subtype,
                "is_correct": _clean_cell(raw.get("is_correct")),
                "error_bucket": _normalize_label(raw.get("error_bucket")),
            }
            rows.append(row)
        input_summaries.append(
            {
                "source_file": str(spec.path),
                "source_dataset": spec.dataset,
                "rows_total": len(source_rows),
                "rows_labeled": labeled_count,
                "rows_skipped": len(source_rows) - labeled_count,
            }
        )
    return rows, {"inputs": input_summaries, "skipped_rows": skipped}


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _safe_div(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def route_metrics(y_true: list[str], y_pred: list[str], *, labels: list[str]) -> dict[str, Any]:
    if not y_true:
        return {}
    confusion_labels = sorted(set(labels) | set(y_pred))
    accuracy = accuracy_score(y_true, y_pred)
    macro_f1 = f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=labels,
        zero_division=0,
    )
    cm = confusion_matrix(y_true, y_pred, labels=confusion_labels)
    per_route = {
        label: {
            "precision": round(float(precision[index]), 6),
            "recall": round(float(recall[index]), 6),
            "f1": round(float(f1[index]), 6),
            "support": int(support[index]),
        }
        for index, label in enumerate(labels)
    }
    expected_filter = sum(1 for label in y_true if label == "filter")
    filter_to_non_filter = sum(1 for truth, pred in zip(y_true, y_pred) if truth == "filter" and pred != "filter")
    expected_non_filter = sum(1 for label in y_true if label != "filter")
    non_filter_to_filter = sum(1 for truth, pred in zip(y_true, y_pred) if truth != "filter" and pred == "filter")
    return {
        "n": len(y_true),
        "route_accuracy": round(float(accuracy), 6),
        "macro_f1": round(float(macro_f1), 6),
        "per_route": per_route,
        "confusion_matrix": {
            "labels": confusion_labels,
            "matrix": [[int(value) for value in row] for row in cm.tolist()],
        },
        "filter_to_non_filter_rate": _safe_div(filter_to_non_filter, expected_filter),
        "filter_to_non_filter_count": filter_to_non_filter,
        "non_filter_to_filter_rate": _safe_div(non_filter_to_filter, expected_non_filter),
        "non_filter_to_filter_count": non_filter_to_filter,
        "application_inbox_recall": per_route.get("application_inbox", {}).get("recall"),
        "conversation_recall": per_route.get("conversation", {}).get("recall"),
    }


def _lr_pipeline() -> Pipeline:
    return Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    lowercase=True,
                    strip_accents="unicode",
                    ngram_range=(1, 2),
                    min_df=2,
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


def _fit_predict(
    rows: list[dict[str, str]],
    train_indices: list[int],
    test_indices: list[int],
    *,
    include_domain: bool,
) -> tuple[list[str], dict[str, Any]]:
    train_labels = [rows[index]["expected_route"] for index in train_indices]
    if len(set(train_labels)) < 2:
        return [], {"skipped": True, "reason": "train_split_has_fewer_than_two_classes"}
    model = _lr_pipeline()
    model.fit([_text_for_lr(rows[index], include_domain=include_domain) for index in train_indices], train_labels)
    predictions = model.predict([_text_for_lr(rows[index], include_domain=include_domain) for index in test_indices])
    vectorizer = model.named_steps["tfidf"]
    return list(predictions), {
        "skipped": False,
        "vocabulary_size": len(vectorizer.vocabulary_),
        "classes": list(model.named_steps["lr"].classes_),
    }


def random_splits(rows: list[dict[str, str]]) -> list[tuple[str, list[int], list[int], dict[str, Any]]]:
    y = [row["expected_route"] for row in rows]
    splitter = StratifiedShuffleSplit(n_splits=N_SPLITS, test_size=0.25, random_state=RANDOM_SEED)
    return [
        (
            f"random_stratified_{split_index}",
            list(train_idx),
            list(test_idx),
            {"group_overlap_count": None},
        )
        for split_index, (train_idx, test_idx) in enumerate(splitter.split(range(len(rows)), y), start=1)
    ]


def grouped_splits(rows: list[dict[str, str]], *, group_key: str, family: str) -> list[tuple[str, list[int], list[int], dict[str, Any]]]:
    groups = [row[group_key] or "unknown" for row in rows]
    unique_groups = sorted(set(groups))
    if len(unique_groups) < 2:
        return []
    test_size = 0.25 if len(unique_groups) >= 10 else 0.34
    splitter = GroupShuffleSplit(n_splits=N_SPLITS, test_size=test_size, random_state=RANDOM_SEED)
    split_rows = []
    for split_index, (train_idx, test_idx) in enumerate(splitter.split(range(len(rows)), groups=groups), start=1):
        train_groups = {groups[index] for index in train_idx}
        test_groups = {groups[index] for index in test_idx}
        split_rows.append(
            (
                f"{family}_{split_index}",
                list(train_idx),
                list(test_idx),
                {
                    "group_key": group_key,
                    "unique_group_count": len(unique_groups),
                    "train_group_count": len(train_groups),
                    "test_group_count": len(test_groups),
                    "group_overlap_count": len(train_groups & test_groups),
                },
            )
        )
    return split_rows


def summarize_folds(folds: list[dict[str, Any]]) -> dict[str, Any]:
    strategies = sorted({strategy for fold in folds for strategy in fold.get("metrics", {})})
    summary: dict[str, Any] = {}
    keys = [
        "route_accuracy",
        "macro_f1",
        "filter_to_non_filter_rate",
        "non_filter_to_filter_rate",
        "application_inbox_recall",
        "conversation_recall",
    ]
    for strategy in strategies:
        summary[strategy] = {}
        for key in keys:
            values = [
                fold["metrics"][strategy].get(key)
                for fold in folds
                if strategy in fold.get("metrics", {}) and fold["metrics"][strategy].get(key) is not None
            ]
            if not values:
                summary[strategy][key] = None
                continue
            summary[strategy][key] = {
                "mean": round(float(mean(values)), 6),
                "std": round(float(pstdev(values)), 6) if len(values) > 1 else 0.0,
                "min": round(float(min(values)), 6),
                "max": round(float(max(values)), 6),
            }
    return summary


def pooled_predictions_metrics(prediction_rows: list[dict[str, Any]], *, labels: list[str]) -> dict[str, Any]:
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in prediction_rows:
        by_key[(row["split_family"], row["strategy"])].append(row)
    output: dict[str, Any] = {}
    for (split_family, strategy), rows in sorted(by_key.items()):
        output.setdefault(split_family, {})[strategy] = route_metrics(
            [row["expected_route"] for row in rows],
            [row["predicted_route"] for row in rows],
            labels=labels,
        )
    return output


def run_eval(rows: list[dict[str, str]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    labels = sorted(set(row["expected_route"] for row in rows))
    y_true_full = [row["expected_route"] for row in rows]
    baseline_full = route_metrics(y_true_full, [row["predicted_route"] for row in rows], labels=labels)

    split_plan = {
        "random_stratified": random_splits(rows),
        "sender_domain_grouped": grouped_splits(rows, group_key="sender_domain", family="sender_domain_grouped"),
        "source_account_grouped": grouped_splits(rows, group_key="source_account_group", family="source_account_grouped"),
    }

    all_predictions: list[dict[str, Any]] = []
    split_results: dict[str, Any] = {}
    for family, splits in split_plan.items():
        folds: list[dict[str, Any]] = []
        for split_name, train_idx, test_idx, split_meta in splits:
            y_test = [rows[index]["expected_route"] for index in test_idx]
            fold_metrics = {
                "heuristic": route_metrics(y_test, [rows[index]["predicted_route"] for index in test_idx], labels=labels),
            }
            for index in test_idx:
                all_predictions.append(
                    {
                        "split_family": family,
                        "split_id": split_name,
                        "strategy": "heuristic",
                        "row_id": rows[index]["row_id"],
                        "source_dataset": rows[index]["source_dataset"],
                        "case_id": rows[index]["case_id"],
                        "source_account_group": rows[index]["source_account_group"],
                        "sender_domain": rows[index]["sender_domain"],
                        "expected_route": rows[index]["expected_route"],
                        "predicted_route": rows[index]["predicted_route"],
                        "correct": str(rows[index]["expected_route"] == rows[index]["predicted_route"]).lower(),
                    }
                )
            for strategy, include_domain in [
                ("tfidf_lr_text", False),
                ("tfidf_lr_text_plus_domain", True),
            ]:
                predictions, model_meta = _fit_predict(rows, train_idx, test_idx, include_domain=include_domain)
                if model_meta.get("skipped"):
                    fold_metrics[strategy] = {"skipped": True, "reason": model_meta["reason"]}
                    continue
                fold_metrics[strategy] = {
                    **route_metrics(y_test, predictions, labels=labels),
                    "model": model_meta,
                }
                for index, prediction in zip(test_idx, predictions):
                    all_predictions.append(
                        {
                            "split_family": family,
                            "split_id": split_name,
                            "strategy": strategy,
                            "row_id": rows[index]["row_id"],
                            "source_dataset": rows[index]["source_dataset"],
                            "case_id": rows[index]["case_id"],
                            "source_account_group": rows[index]["source_account_group"],
                            "sender_domain": rows[index]["sender_domain"],
                            "expected_route": rows[index]["expected_route"],
                            "predicted_route": prediction,
                            "correct": str(rows[index]["expected_route"] == prediction).lower(),
                        }
                    )
            folds.append(
                {
                    "split_id": split_name,
                    "train_n": len(train_idx),
                    "test_n": len(test_idx),
                    "train_route_counts": dict(Counter(rows[index]["expected_route"] for index in train_idx)),
                    "test_route_counts": dict(Counter(y_test)),
                    **split_meta,
                    "metrics": fold_metrics,
                }
            )
        split_results[family] = {
            "folds": folds,
            "aggregate": summarize_folds(folds),
        }
    return (
        {
            "route_labels": labels,
            "baseline_full": baseline_full,
            "splits": split_results,
            "pooled_test_metrics": pooled_predictions_metrics(all_predictions, labels=labels),
        },
        all_predictions,
    )


def _small_counts(counter: Counter[str], *, threshold: int) -> dict[str, int]:
    return dict(sorted((label, count) for label, count in counter.items() if count < threshold))


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _metric_line(metrics: dict[str, Any]) -> str:
    return (
        f"{_fmt_pct(metrics.get('route_accuracy'))} | {_fmt_pct(metrics.get('macro_f1'))} | "
        f"{_fmt_pct(metrics.get('filter_to_non_filter_rate'))} | "
        f"{_fmt_pct(metrics.get('non_filter_to_filter_rate'))} | "
        f"{_fmt_pct(metrics.get('application_inbox_recall'))} | {_fmt_pct(metrics.get('conversation_recall'))}"
    )


def _aggregate_value(metrics: dict[str, Any], key: str) -> str:
    value = metrics.get(key)
    if not isinstance(value, dict):
        return "n/a"
    return f"{value['mean'] * 100:.1f}% +/- {value['std'] * 100:.1f}"


def render_confusion_matrix(metrics: dict[str, Any]) -> str:
    labels = metrics["confusion_matrix"]["labels"]
    matrix = metrics["confusion_matrix"]["matrix"]
    lines = ["| actual \\ predicted | " + " | ".join(labels) + " |", "|" + " --- |" * (len(labels) + 1)]
    for label, row in zip(labels, matrix):
        lines.append(f"| {label} | " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


def render_report(metrics: dict[str, Any]) -> str:
    dataset = metrics["dataset"]
    baseline = metrics["eval"]["baseline_full"]
    splits = metrics["eval"]["splits"]
    pooled = metrics["eval"]["pooled_test_metrics"]
    lines = [
        "# Gmail TF-IDF/LR Shadow Eval",
        "",
        "This report uses locally stored, human-labeled Gmail rows only. No production routing changes are made.",
        "",
        "## Dataset",
        "",
        f"- Total source rows: `{dataset['rows_total']}`",
        f"- Labeled eval rows: `{dataset['rows_labeled']}`",
        f"- Skipped unlabeled rows: `{dataset['rows_skipped']}`",
        f"- Unique sender domains: `{dataset['unique_sender_domains']}`",
        f"- Source/account groups: `{dataset['unique_source_account_groups']}`",
        "",
        "### Route Labels",
        "",
        "| expected_route | count |",
        "| --- | ---: |",
    ]
    for route, count in dataset["expected_route_counts"].items():
        lines.append(f"| {route} | {count} |")
    lines.extend(
        [
            "",
            "### Underrepresented Labels",
            "",
            f"- Routes below 20 examples: `{dataset['underrepresented_routes_lt20']}`",
            f"- Subtypes below 10 examples: `{dataset['underrepresented_subtypes_lt10']}`",
            "",
            "## Full Heuristic Baseline",
            "",
            "| route accuracy | macro F1 | filter -> non-filter | non-filter -> filter | application_inbox recall | conversation recall |",
            "| ---: | ---: | ---: | ---: | ---: | ---: |",
            f"| {_metric_line(baseline)} |",
            "",
            "### Full Heuristic Confusion Matrix",
            "",
            render_confusion_matrix(baseline),
            "",
            "## Split Comparison",
            "",
            "Values are mean +/- population std across five folds. LR is evaluated only on held-out rows.",
            "",
            "| split | strategy | route accuracy | macro F1 | filter -> non-filter | non-filter -> filter | application_inbox recall | conversation recall |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for split_name, split_data in splits.items():
        for strategy in ["heuristic", "tfidf_lr_text", "tfidf_lr_text_plus_domain"]:
            aggregate = split_data["aggregate"].get(strategy, {})
            lines.append(
                f"| {split_name} | {strategy} | "
                f"{_aggregate_value(aggregate, 'route_accuracy')} | "
                f"{_aggregate_value(aggregate, 'macro_f1')} | "
                f"{_aggregate_value(aggregate, 'filter_to_non_filter_rate')} | "
                f"{_aggregate_value(aggregate, 'non_filter_to_filter_rate')} | "
                f"{_aggregate_value(aggregate, 'application_inbox_recall')} | "
                f"{_aggregate_value(aggregate, 'conversation_recall')} |"
            )
    lines.extend(["", "## Pooled Held-Out Confusion Matrices", ""])
    for split_name in ["random_stratified", "sender_domain_grouped", "source_account_grouped"]:
        split_metrics = pooled.get(split_name, {})
        for strategy in ["heuristic", "tfidf_lr_text", "tfidf_lr_text_plus_domain"]:
            if strategy not in split_metrics:
                continue
            lines.extend([f"### {split_name}: {strategy}", "", render_confusion_matrix(split_metrics[strategy]), ""])

    findings = metrics["findings"]
    lines.extend(
        [
            "## Interpretation",
            "",
            f"- Generalization assessment: {findings['generalization_assessment']}",
            f"- Promotion recommendation: `{findings['promotion_recommendation']}`",
            f"- Optional policy cleanup: {findings['policy_cleanup']}",
            "- Simple ensemble: not run; LR was not clearly separated enough from the current heuristic baseline.",
            "",
            "## Limitations",
            "",
            "- The combined set is still a priority/high-yield labeled sample, not a population-random Gmail sample.",
            "- Grouped splits are small and should be treated as directional.",
            "- TF-IDF/LR is route-only here; subtype and action prediction were not promoted or trained.",
            "- Redacted text remains private audit data and is intentionally not copied into this report.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_findings(eval_metrics: dict[str, Any]) -> dict[str, str]:
    splits = eval_metrics["splits"]
    random_lr = splits["random_stratified"]["aggregate"]["tfidf_lr_text"]["route_accuracy"]["mean"]
    domain_lr = splits["sender_domain_grouped"]["aggregate"]["tfidf_lr_text"]["route_accuracy"]["mean"]
    random_domain_lr = splits["random_stratified"]["aggregate"]["tfidf_lr_text_plus_domain"]["route_accuracy"]["mean"]
    grouped_domain_lr = splits["sender_domain_grouped"]["aggregate"]["tfidf_lr_text_plus_domain"]["route_accuracy"]["mean"]
    heuristic_domain = splits["sender_domain_grouped"]["aggregate"]["heuristic"]["route_accuracy"]["mean"]

    if random_lr - domain_lr > 0.15 or random_domain_lr - grouped_domain_lr > 0.15:
        generalization = (
            "Random split performance is materially higher than sender-domain grouped performance, so LR is likely "
            "learning sender/template regularities. Treat it as a shadow candidate only."
        )
    elif domain_lr > heuristic_domain + 0.05:
        generalization = (
            "LR stays ahead of heuristics on sender-domain grouped splits, which suggests some cross-domain signal. "
            "It still needs a fresh holdout before rollout."
        )
    else:
        generalization = (
            "LR does not clearly beat heuristics under grouped splits. Evidence is insufficient for a guarded rollout."
        )

    return {
        "generalization_assessment": generalization,
        "promotion_recommendation": "do_not_promote_collect_fresh_holdout_and_continue_shadow_eval",
        "policy_cleanup": (
            "One small heuristic pass is reasonable: review filter/conversation/application boundary rules for "
            "high-volume notification or job-board style senders, without tuning to individual labeled rows."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Gmail TF-IDF/LR route shadow eval.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--timestamp", default=_timestamp())
    parser.add_argument(
        "--dataset",
        choices=["new-only", "prior-only", "cumulative"],
        default="cumulative",
        help="Which labeled CSV source set to evaluate.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_root) / args.timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.dataset == "new-only":
        sources = [SourceSpec(NEW_LABEL_FILE, "new_2026_05_12_policy_corrected")]
    elif args.dataset == "prior-only":
        sources = [SourceSpec(PRIOR_LABEL_FILE, "prior_2026_05_07_priority")]
    else:
        sources = [
            SourceSpec(PRIOR_LABEL_FILE, "prior_2026_05_07_priority"),
            SourceSpec(NEW_LABEL_FILE, "new_2026_05_12_policy_corrected"),
        ]
    rows, input_summary = load_labeled_rows(sources)
    write_csv(output_dir / "cumulative_labeled_dataset.csv", rows, OUTPUT_COLUMNS)

    eval_metrics, predictions = run_eval(rows)
    write_csv(output_dir / "predictions.csv", predictions, PREDICTION_COLUMNS)

    route_counts = Counter(row["expected_route"] for row in rows)
    subtype_counts = Counter(row["expected_subtype"] for row in rows)
    dataset_metrics = {
        "rows_total": sum(item["rows_total"] for item in input_summary["inputs"]),
        "rows_labeled": len(rows),
        "rows_skipped": len(input_summary["skipped_rows"]),
        "expected_route_counts": dict(sorted(route_counts.items())),
        "expected_subtype_counts": dict(sorted(subtype_counts.items())),
        "predicted_route_counts": dict(sorted(Counter(row["predicted_route"] for row in rows).items())),
        "unique_sender_domains": len({row["sender_domain"] for row in rows if row["sender_domain"]}),
        "unique_source_account_groups": len({row["source_account_group"] for row in rows}),
        "underrepresented_routes_lt20": _small_counts(route_counts, threshold=20),
        "underrepresented_subtypes_lt10": _small_counts(subtype_counts, threshold=10),
    }
    metrics = {
        "artifact": "gmail_lr_shadow_eval",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(output_dir),
        "inputs": input_summary,
        "dataset": dataset_metrics,
        "eval": eval_metrics,
        "findings": build_findings(eval_metrics),
    }
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "report.md").write_text(render_report(metrics), encoding="utf-8")

    print(json.dumps({
        "output_dir": str(output_dir),
        "rows_labeled": len(rows),
        "rows_skipped": len(input_summary["skipped_rows"]),
        "baseline_route_accuracy": metrics["eval"]["baseline_full"]["route_accuracy"],
        "baseline_macro_f1": metrics["eval"]["baseline_full"]["macro_f1"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
