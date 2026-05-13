from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_gmail_lr_shadow_eval import (
    NEW_LABEL_FILE,
    _lr_pipeline,
    _normalize_label,
    _normalize_route_label,
    grouped_splits,
    random_splits,
    route_metrics,
)

try:
    from sklearn.metrics import accuracy_score, f1_score
except Exception as exc:  # pragma: no cover - local dependency guard
    raise SystemExit(
        "scikit-learn is required for Gmail synthetic augmentation eval. "
        f"Import error: {type(exc).__name__}: {exc}"
    ) from exc


DEFAULT_SYNTHETIC_ROOT = Path("audit/runs/gmail_synthetic_scenarios")
DEFAULT_OUTPUT_ROOT = Path("audit/runs/gmail_synthetic_lr_augmentation_eval")
RANDOM_SEED = 42

PREDICTION_COLUMNS = [
    "split_family",
    "split_id",
    "strategy",
    "row_id",
    "source_dataset",
    "source_account_group",
    "sender_domain",
    "expected_route",
    "predicted_route",
    "expected_subtype",
    "predicted_subtype",
    "expected_action_required",
    "predicted_action_required",
]


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _clean_cell(value: Any) -> str:
    return " ".join(str(value or "").split())


def _bool_label(value: Any) -> str:
    cleaned = _normalize_label(value)
    if cleaned in {"yes", "true", "1", "y"}:
        return "true"
    if cleaned in {"no", "false", "0", "n"}:
        return "false"
    return ""


def _text_for_row(row: dict[str, Any], *, include_domain: bool = False) -> str:
    parts = [
        row.get("subject", ""),
        row.get("snippet", ""),
        row.get("body", ""),
    ]
    if include_domain:
        domain = _normalize_label(str(row.get("sender_domain", "")).replace(".", "_"))
        parts.append(f"sender_domain_{domain}" if domain else "sender_domain_unknown")
    return " ".join(_clean_cell(part) for part in parts if _clean_cell(part))


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _latest_dir(root: Path) -> Path | None:
    if not root.exists():
        return None
    candidates = [path for path in root.iterdir() if path.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def load_real_rows(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        raw_rows = list(csv.DictReader(handle))
    rows: list[dict[str, Any]] = []
    skipped = []
    for index, raw in enumerate(raw_rows, start=1):
        expected_route = _normalize_route_label(raw.get("expected_route"))
        expected_subtype = _normalize_label(raw.get("expected_subtype"))
        if not expected_route or not expected_subtype:
            skipped.append({"source_row_number": index, "reason": "missing_expected_route_or_subtype"})
            continue
        account_group = _clean_cell(raw.get("account_role")) or _clean_cell(raw.get("account_label")) or "unknown_account"
        rows.append(
            {
                "row_id": f"real:{index}:{_clean_cell(raw.get('case_id')) or index}",
                "source_type": "real_human",
                "source_dataset": "new_2026_05_12_policy_corrected",
                "source_file": str(path),
                "source_row_number": index,
                "source_account_group": f"real:{account_group}",
                "sender_domain": _clean_cell(raw.get("sender_domain")).lower(),
                "subject": _clean_cell(raw.get("redacted_subject")),
                "snippet": _clean_cell(raw.get("redacted_snippet")),
                "body": _clean_cell(raw.get("redacted_body_preview")),
                "expected_route": expected_route,
                "expected_subtype": expected_subtype,
                "expected_action_required": _bool_label(raw.get("action_expected")),
                "expected_action_type": _normalize_label(raw.get("expected_action_type")),
                "predicted_route": _normalize_route_label(raw.get("predicted_route")),
                "predicted_subtype": _normalize_label(raw.get("predicted_subtype")),
                "predicted_action_required": _bool_label(raw.get("action_needed")),
            }
        )
    return rows, {"rows_total": len(raw_rows), "rows_labeled": len(rows), "rows_skipped": len(skipped), "skipped_rows": skipped}


def load_synthetic_rows(path: Path | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if path is None:
        return [], {"synthetic_dir": None, "rows_total": 0, "training_eligible_count": 0, "reason": "no_synthetic_dir_found"}
    csv_path = path / "synthetic_scenarios.csv"
    if not csv_path.exists():
        return [], {"synthetic_dir": str(path), "rows_total": 0, "training_eligible_count": 0, "reason": "synthetic_scenarios.csv_missing"}
    with csv_path.open(newline="", encoding="utf-8") as handle:
        raw_rows = list(csv.DictReader(handle))
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_rows, start=1):
        training_eligible = _bool_label(raw.get("training_eligible")) == "true"
        row = {
            "row_id": f"synthetic:{index}:{_normalize_label(raw.get('scenario_family'))}",
            "source_type": _clean_cell(raw.get("source_type")),
            "source_dataset": _clean_cell(raw.get("source_dataset")) or "synthetic",
            "source_file": str(csv_path),
            "source_row_number": index,
            "source_account_group": "synthetic:generation",
            "sender_domain": _clean_cell(raw.get("sender_domain")).lower(),
            "subject": _clean_cell(raw.get("subject")),
            "snippet": "",
            "body": _clean_cell(raw.get("body")),
            "expected_route": _normalize_route_label(raw.get("expected_route")),
            "expected_subtype": _normalize_label(raw.get("expected_subtype")),
            "expected_action_required": _bool_label(raw.get("expected_action_required")),
            "expected_action_type": _normalize_label(raw.get("expected_action_type")),
            "predicted_route": "",
            "predicted_subtype": "",
            "predicted_action_required": "",
            "scenario_family": _clean_cell(raw.get("scenario_family")),
            "synthetic_family_id": _clean_cell(raw.get("synthetic_family_id")),
            "generation_prompt_version": _clean_cell(raw.get("generation_prompt_version")),
            "label_policy_version": _clean_cell(raw.get("label_policy_version")),
            "human_reviewed": _bool_label(raw.get("human_reviewed")),
            "training_eligible": str(training_eligible).lower(),
        }
        if training_eligible:
            rows.append(row)
    return rows, {
        "synthetic_dir": str(path),
        "rows_total": len(raw_rows),
        "training_eligible_count": len(rows),
        "route_counts": dict(sorted(Counter(row["expected_route"] for row in rows).items())),
        "subtype_counts": dict(sorted(Counter(row["expected_subtype"] for row in rows).items())),
    }


def _fit_predict_label(
    train_rows: list[dict[str, Any]],
    test_rows: list[dict[str, Any]],
    *,
    label_key: str,
    include_domain: bool,
) -> tuple[list[str], dict[str, Any]]:
    train_rows = [row for row in train_rows if row.get(label_key)]
    test_rows = [row for row in test_rows if row.get(label_key)]
    labels = [row[label_key] for row in train_rows]
    if len(set(labels)) < 2:
        return [], {"skipped": True, "reason": f"{label_key}_train_has_fewer_than_two_classes"}
    model = _lr_pipeline()
    model.fit([_text_for_row(row, include_domain=include_domain) for row in train_rows], labels)
    predictions = model.predict([_text_for_row(row, include_domain=include_domain) for row in test_rows])
    return list(predictions), {
        "skipped": False,
        "train_n": len(train_rows),
        "test_n": len(test_rows),
        "classes": list(model.named_steps["lr"].classes_),
        "vocabulary_size": len(model.named_steps["tfidf"].vocabulary_),
    }


def _classification_metrics(y_true: list[str], y_pred: list[str]) -> dict[str, Any]:
    if not y_true:
        return {"accuracy": None, "macro_f1": None, "n": 0}
    labels = sorted(set(y_true))
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 6),
        "macro_f1": round(float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)), 6),
        "n": len(y_true),
    }


def _heuristic_fold_metrics(test_rows: list[dict[str, Any]], route_labels: list[str]) -> dict[str, Any]:
    route = route_metrics(
        [row["expected_route"] for row in test_rows],
        [row["predicted_route"] for row in test_rows],
        labels=route_labels,
    )
    subtype_rows = [row for row in test_rows if row["expected_subtype"] and row["predicted_subtype"]]
    action_rows = [row for row in test_rows if row["expected_action_required"] and row["predicted_action_required"]]
    return {
        **route,
        "subtype_accuracy": _classification_metrics(
            [row["expected_subtype"] for row in subtype_rows],
            [row["predicted_subtype"] for row in subtype_rows],
        )["accuracy"],
        "action_required_accuracy": _classification_metrics(
            [row["expected_action_required"] for row in action_rows],
            [row["predicted_action_required"] for row in action_rows],
        )["accuracy"],
    }


def _lr_fold_metrics(
    train_rows: list[dict[str, Any]],
    test_rows: list[dict[str, Any]],
    *,
    route_labels: list[str],
    include_domain: bool = False,
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    route_pred, route_meta = _fit_predict_label(
        train_rows,
        test_rows,
        label_key="expected_route",
        include_domain=include_domain,
    )
    if route_meta.get("skipped"):
        return {"skipped": True, "reason": route_meta["reason"]}, {}
    route_true = [row["expected_route"] for row in test_rows]
    route = route_metrics(route_true, route_pred, labels=route_labels)

    subtype_rows = [row for row in test_rows if row["expected_subtype"]]
    subtype_pred, subtype_meta = _fit_predict_label(
        train_rows,
        subtype_rows,
        label_key="expected_subtype",
        include_domain=include_domain,
    )
    subtype_true = [row["expected_subtype"] for row in subtype_rows]
    subtype_metrics = (
        {"accuracy": None, "macro_f1": None, "n": len(subtype_rows), "skipped": True}
        if subtype_meta.get("skipped")
        else _classification_metrics(subtype_true, subtype_pred)
    )

    action_rows = [row for row in test_rows if row["expected_action_required"]]
    action_pred, action_meta = _fit_predict_label(
        train_rows,
        action_rows,
        label_key="expected_action_required",
        include_domain=include_domain,
    )
    action_true = [row["expected_action_required"] for row in action_rows]
    action_metrics = (
        {"accuracy": None, "macro_f1": None, "n": len(action_rows), "skipped": True}
        if action_meta.get("skipped")
        else _classification_metrics(action_true, action_pred)
    )

    subtype_by_row = {row["row_id"]: pred for row, pred in zip(subtype_rows, subtype_pred)}
    action_by_row = {row["row_id"]: pred for row, pred in zip(action_rows, action_pred)}
    return (
        {
            **route,
            "subtype_accuracy": subtype_metrics["accuracy"],
            "subtype_macro_f1": subtype_metrics["macro_f1"],
            "action_required_accuracy": action_metrics["accuracy"],
            "action_required_macro_f1": action_metrics["macro_f1"],
            "route_model": route_meta,
            "subtype_model": subtype_meta,
            "action_model": action_meta,
        },
        {
            "route": route_pred,
            "subtype": [subtype_by_row.get(row["row_id"], "") for row in test_rows],
            "action": [action_by_row.get(row["row_id"], "") for row in test_rows],
        },
    )


def _aggregate(folds: list[dict[str, Any]]) -> dict[str, Any]:
    strategies = sorted({key for fold in folds for key in fold["metrics"]})
    metric_keys = [
        "route_accuracy",
        "macro_f1",
        "subtype_accuracy",
        "action_required_accuracy",
        "filter_to_non_filter_rate",
        "non_filter_to_filter_rate",
        "application_inbox_recall",
        "conversation_recall",
        "action_review_recall",
    ]
    output: dict[str, Any] = {}
    for strategy in strategies:
        output[strategy] = {}
        for key in metric_keys:
            values = []
            for fold in folds:
                metrics = fold["metrics"].get(strategy, {})
                if key == "action_review_recall":
                    value = metrics.get("per_route", {}).get("action_review", {}).get("recall")
                else:
                    value = metrics.get(key)
                if value is not None:
                    values.append(value)
            if not values:
                output[strategy][key] = None
                continue
            output[strategy][key] = {
                "mean": round(float(mean(values)), 6),
                "std": round(float(pstdev(values)), 6) if len(values) > 1 else 0.0,
                "min": round(float(min(values)), 6),
                "max": round(float(max(values)), 6),
            }
    return output


def run_comparison(real_rows: list[dict[str, Any]], synthetic_rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    route_labels = sorted(set(row["expected_route"] for row in real_rows))
    splits = {
        "random_stratified": random_splits(real_rows),
        "sender_domain_grouped": grouped_splits(real_rows, group_key="sender_domain", family="sender_domain_grouped"),
        "source_account_grouped": grouped_splits(real_rows, group_key="source_account_group", family="source_account_grouped"),
    }
    prediction_rows: list[dict[str, Any]] = []
    split_results: dict[str, Any] = {}
    for split_family, split_items in splits.items():
        folds = []
        for split_id, train_idx, test_idx, split_meta in split_items:
            train_real = [real_rows[index] for index in train_idx]
            test_real = [real_rows[index] for index in test_idx]
            metrics = {
                "heuristic": _heuristic_fold_metrics(test_real, route_labels),
            }
            real_only_metrics, real_only_predictions = _lr_fold_metrics(train_real, test_real, route_labels=route_labels)
            metrics["lr_real_only"] = real_only_metrics
            if synthetic_rows:
                augmented_metrics, augmented_predictions = _lr_fold_metrics(
                    [*train_real, *synthetic_rows],
                    test_real,
                    route_labels=route_labels,
                )
                synthetic_only_metrics, synthetic_only_predictions = _lr_fold_metrics(
                    synthetic_rows,
                    test_real,
                    route_labels=route_labels,
                )
            else:
                augmented_predictions = {}
                synthetic_only_predictions = {}
                augmented_metrics = {
                    "skipped": True,
                    "reason": "no_training_eligible_synthetic_rows",
                }
                synthetic_only_metrics = {
                    "skipped": True,
                    "reason": "no_training_eligible_synthetic_rows",
                }
            metrics["lr_real_plus_synthetic"] = augmented_metrics
            metrics["lr_synthetic_only"] = synthetic_only_metrics

            prediction_sets = {
                "heuristic": {
                    "route": [row["predicted_route"] for row in test_real],
                    "subtype": [row["predicted_subtype"] for row in test_real],
                    "action": [row["predicted_action_required"] for row in test_real],
                },
                "lr_real_only": real_only_predictions,
                "lr_real_plus_synthetic": augmented_predictions,
                "lr_synthetic_only": synthetic_only_predictions,
            }
            for strategy, preds in prediction_sets.items():
                if not preds:
                    continue
                for row_index, row in enumerate(test_real):
                    prediction_rows.append(
                        {
                            "split_family": split_family,
                            "split_id": split_id,
                            "strategy": strategy,
                            "row_id": row["row_id"],
                            "source_dataset": row["source_dataset"],
                            "source_account_group": row["source_account_group"],
                            "sender_domain": row["sender_domain"],
                            "expected_route": row["expected_route"],
                            "predicted_route": preds.get("route", [""] * len(test_real))[row_index]
                            if row_index < len(preds.get("route", []))
                            else "",
                            "expected_subtype": row["expected_subtype"],
                            "predicted_subtype": preds.get("subtype", [""] * len(test_real))[row_index]
                            if row_index < len(preds.get("subtype", []))
                            else "",
                            "expected_action_required": row["expected_action_required"],
                            "predicted_action_required": preds.get("action", [""] * len(test_real))[row_index]
                            if row_index < len(preds.get("action", []))
                            else "",
                        }
                    )
            folds.append(
                {
                    "split_id": split_id,
                    "train_real_n": len(train_real),
                    "test_real_n": len(test_real),
                    "synthetic_training_n": len(synthetic_rows),
                    **split_meta,
                    "metrics": metrics,
                }
            )
        split_results[split_family] = {
            "folds": folds,
            "aggregate": _aggregate(folds),
        }
    return {"route_labels": route_labels, "splits": split_results}, prediction_rows


def _pct(value: Any) -> str:
    if not isinstance(value, dict):
        return "n/a"
    return f"{value['mean'] * 100:.1f}% +/- {value['std'] * 100:.1f}"


def render_report(metrics: dict[str, Any]) -> str:
    synthetic = metrics["synthetic"]
    lines = [
        "# Gmail Synthetic LR Augmentation Eval",
        "",
        "This report evaluates synthetic augmentation offline only. Production Gmail routing is unchanged.",
        "",
        "## Dataset",
        "",
        f"- Real labeled rows: `{metrics['real']['rows_labeled']}`",
        f"- Real skipped rows: `{metrics['real']['rows_skipped']}`",
        f"- Synthetic artifact: `{synthetic.get('synthetic_dir')}`",
        f"- Synthetic rows total: `{synthetic.get('rows_total', 0)}`",
        f"- Training-eligible synthetic rows: `{synthetic.get('training_eligible_count', 0)}`",
        "",
        "## Split Comparison",
        "",
        "| split | strategy | route accuracy | route macro F1 | subtype accuracy | action-required accuracy | filter -> non-filter | non-filter -> filter | application_inbox recall | conversation recall | action_review recall |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for split_name, split_data in metrics["eval"]["splits"].items():
        for strategy in ["heuristic", "lr_real_only", "lr_real_plus_synthetic", "lr_synthetic_only"]:
            aggregate = split_data["aggregate"].get(strategy, {})
            lines.append(
                f"| {split_name} | {strategy} | "
                f"{_pct(aggregate.get('route_accuracy'))} | "
                f"{_pct(aggregate.get('macro_f1'))} | "
                f"{_pct(aggregate.get('subtype_accuracy'))} | "
                f"{_pct(aggregate.get('action_required_accuracy'))} | "
                f"{_pct(aggregate.get('filter_to_non_filter_rate'))} | "
                f"{_pct(aggregate.get('non_filter_to_filter_rate'))} | "
                f"{_pct(aggregate.get('application_inbox_recall'))} | "
                f"{_pct(aggregate.get('conversation_recall'))} | "
                f"{_pct(aggregate.get('action_review_recall'))} |"
            )
    findings = metrics["findings"]
    lines.extend(
        [
            "",
            "## Finding",
            "",
            findings["summary"],
            "",
            "## Safety Boundary",
            "",
            "- Synthetic rows are never written to production DB tables.",
            "- Synthetic rows are never merged into the human-labeled CSV.",
            "- Real human-labeled rows remain the promotion gate.",
            "- Dry-run template examples are not training data.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_findings(metrics: dict[str, Any]) -> dict[str, str]:
    synthetic_count = metrics["synthetic"].get("training_eligible_count", 0)
    if synthetic_count == 0:
        return {
            "summary": (
                "Synthetic augmentation comparison ran, but no synthetic rows were training-eligible. "
                "The dry-run generator produced schema/provenance examples only, so augmentation impact is blocked "
                "until LLM-generated rows are produced and reviewed for training use."
            ),
            "decision": "augmentation_blocked_no_training_eligible_synthetic_rows",
        }
    random_split = metrics["eval"]["splits"]["random_stratified"]["aggregate"]
    real = random_split["lr_real_only"]["route_accuracy"]["mean"]
    augmented = random_split["lr_real_plus_synthetic"]["route_accuracy"]["mean"]
    if augmented > real + 0.02:
        decision = "synthetic_augmentation_promising_continue_shadow_eval"
        summary = "Synthetic augmentation improved random-split route accuracy. Check grouped splits and fresh real holdout before promotion."
    elif augmented < real - 0.02:
        decision = "synthetic_augmentation_regressed"
        summary = "Synthetic augmentation regressed random-split route accuracy. Improve generation quality before more experiments."
    else:
        decision = "synthetic_augmentation_insufficient_delta"
        summary = "Synthetic augmentation did not materially change random-split route accuracy. More targeted rows or better labels are needed."
    return {"summary": summary, "decision": decision}


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare real-only LR with synthetic-augmented Gmail LR.")
    parser.add_argument("--real-csv", default=str(NEW_LABEL_FILE))
    parser.add_argument("--synthetic-dir", default=None)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--timestamp", default=_timestamp())
    args = parser.parse_args()

    synthetic_dir = Path(args.synthetic_dir) if args.synthetic_dir else _latest_dir(DEFAULT_SYNTHETIC_ROOT)
    output_dir = Path(args.output_root) / args.timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    real_rows, real_summary = load_real_rows(Path(args.real_csv))
    synthetic_rows, synthetic_summary = load_synthetic_rows(synthetic_dir)
    eval_metrics, predictions = run_comparison(real_rows, synthetic_rows)
    _write_csv(output_dir / "predictions.csv", predictions, PREDICTION_COLUMNS)

    metrics = {
        "artifact": "gmail_synthetic_lr_augmentation_eval",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(output_dir),
        "real": {
            **real_summary,
            "route_counts": dict(sorted(Counter(row["expected_route"] for row in real_rows).items())),
            "subtype_counts": dict(sorted(Counter(row["expected_subtype"] for row in real_rows).items())),
            "action_required_counts": dict(sorted(Counter(row["expected_action_required"] for row in real_rows).items())),
        },
        "synthetic": synthetic_summary,
        "eval": eval_metrics,
    }
    metrics["findings"] = build_findings(metrics)
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "report.md").write_text(render_report(metrics), encoding="utf-8")
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "real_rows": len(real_rows),
                "synthetic_training_rows": len(synthetic_rows),
                "decision": metrics["findings"]["decision"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
