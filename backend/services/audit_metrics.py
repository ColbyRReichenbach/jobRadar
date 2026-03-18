"""Audit metrics computation for classifier evaluation.

Computes accuracy, precision, recall, F1, and confusion matrices
from reviewed audit CSV data. Biased toward recall — missing a real
job email is worse than letting noise through.
"""

import csv
import io
from collections import Counter

VALID_CLASSIFICATIONS = {
    "interview_request", "rejection", "offer",
    "action_item", "job_update", "conversation", "not_relevant",
}

VALID_DECISIONS = {"inbox", "filter"}


def parse_audit_csv(file_bytes: bytes) -> list[dict]:
    """Parse uploaded CSV bytes into list of row dicts."""
    text = file_bytes.decode("utf-8-sig")  # handle BOM
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def _binary_metrics(y_true: list[str], y_pred: list[str], positive: str) -> dict:
    """Compute binary classification metrics for a given positive class."""
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == positive and p == positive)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t != positive and p == positive)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == positive and p != positive)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t != positive and p != positive)

    accuracy = (tp + tn) / max(tp + tn + fp + fn, 1)
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-9)

    return {
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }


def _confusion_matrix(y_true: list[str], y_pred: list[str], labels: list[str]) -> list[list[int]]:
    """Build a confusion matrix as 2D list. Rows = true, cols = predicted."""
    label_idx = {l: i for i, l in enumerate(labels)}
    n = len(labels)
    matrix = [[0] * n for _ in range(n)]
    for t, p in zip(y_true, y_pred):
        ti = label_idx.get(t)
        pi = label_idx.get(p)
        if ti is not None and pi is not None:
            matrix[ti][pi] += 1
    return matrix


def _per_class_metrics(y_true: list[str], y_pred: list[str], labels: list[str]) -> dict:
    """Compute per-class precision/recall/F1."""
    result = {}
    for label in labels:
        m = _binary_metrics(y_true, y_pred, positive=label)
        support = sum(1 for t in y_true if t == label)
        result[label] = {
            "precision": m["precision"],
            "recall": m["recall"],
            "f1": m["f1"],
            "support": support,
        }
    return result


def compute_run_metrics(rows: list[dict]) -> dict:
    """Compute all metrics from reviewed audit CSV rows.

    Only rows where review_correct is non-empty are included.
    Returns metrics dict matching the run metadata schema.
    """
    reviewed = [r for r in rows if (r.get("review_correct") or "").strip()]

    if not reviewed:
        return {
            "decision": {"accuracy": 0, "precision": 0, "recall": 0, "f1": 0, "support": {}},
            "classification": {"accuracy": 0, "per_class": {}, "macro_recall": 0, "weighted_recall": 0},
            "network_contact": {"accuracy": 0, "precision": 0, "recall": 0, "f1": 0},
            "confusion_matrix": {"labels": [], "matrix": []},
            "classification_confusion": {"labels": [], "matrix": []},
            "status_change": {"accuracy": 0, "total": 0},
        }

    # --- Decision metrics (inbox/filter) ---
    # For rows marked correct, predicted == expected.
    # For rows marked incorrect, use review_expected_decision.
    decision_true = []
    decision_pred = []
    for r in reviewed:
        pred = (r.get("predicted_decision") or "").strip()
        if r.get("review_correct", "").strip().lower() == "yes":
            decision_true.append(pred)
        else:
            expected = (r.get("review_expected_decision") or "").strip()
            decision_true.append(expected if expected else pred)
        decision_pred.append(pred)

    decision_metrics = _binary_metrics(decision_true, decision_pred, positive="inbox")
    decision_support = dict(Counter(decision_true))

    # Decision confusion matrix
    decision_labels = ["inbox", "filter"]
    decision_cm = _confusion_matrix(decision_true, decision_pred, decision_labels)

    # --- Classification metrics (7 categories) ---
    cls_true = []
    cls_pred = []
    for r in reviewed:
        pred = (r.get("predicted_classification") or "").strip()
        if r.get("review_correct", "").strip().lower() == "yes":
            cls_true.append(pred)
        else:
            expected = (r.get("review_expected_classification") or "").strip()
            cls_true.append(expected if expected else pred)
        cls_pred.append(pred)

    # Only include labels that appear in either true or pred
    active_labels = sorted(set(cls_true) | set(cls_pred))
    per_class = _per_class_metrics(cls_true, cls_pred, active_labels)

    cls_accuracy = sum(1 for t, p in zip(cls_true, cls_pred) if t == p) / max(len(cls_true), 1)

    # Macro recall (unweighted average of per-class recall)
    recalls = [per_class[l]["recall"] for l in active_labels if per_class[l]["support"] > 0]
    macro_recall = sum(recalls) / max(len(recalls), 1)

    # Weighted recall (weighted by support)
    total_support = sum(per_class[l]["support"] for l in active_labels)
    weighted_recall = sum(
        per_class[l]["recall"] * per_class[l]["support"]
        for l in active_labels
    ) / max(total_support, 1)

    cls_cm = _confusion_matrix(cls_true, cls_pred, active_labels)

    # --- Network contact metrics ---
    net_true = []
    net_pred = []
    for r in reviewed:
        pred = (r.get("predicted_network_contact") or "").strip()
        if r.get("review_correct", "").strip().lower() == "yes":
            net_true.append(pred)
        else:
            expected = (r.get("review_expected_network_contact") or "").strip()
            net_true.append(expected if expected else pred)
        net_pred.append(pred)

    net_metrics = _binary_metrics(net_true, net_pred, positive="yes")

    # --- Status change accuracy ---
    status_rows = [r for r in reviewed if (r.get("review_expected_status_change") or "").strip()]
    status_correct = sum(
        1 for r in status_rows
        if r.get("predicted_status_change", "").strip() == r.get("review_expected_status_change", "").strip()
    )

    return {
        "decision": {
            "accuracy": decision_metrics["accuracy"],
            "precision": decision_metrics["precision"],
            "recall": decision_metrics["recall"],
            "f1": decision_metrics["f1"],
            "support": decision_support,
        },
        "classification": {
            "accuracy": round(cls_accuracy, 4),
            "per_class": per_class,
            "macro_recall": round(macro_recall, 4),
            "weighted_recall": round(weighted_recall, 4),
        },
        "network_contact": {
            "accuracy": net_metrics["accuracy"],
            "precision": net_metrics["precision"],
            "recall": net_metrics["recall"],
            "f1": net_metrics["f1"],
        },
        "confusion_matrix": {
            "labels": decision_labels,
            "matrix": decision_cm,
        },
        "classification_confusion": {
            "labels": active_labels,
            "matrix": cls_cm,
        },
        "status_change": {
            "accuracy": round(status_correct / max(len(status_rows), 1), 4),
            "total": len(status_rows),
        },
    }


def compare_runs(run_metas: list[dict]) -> list[dict]:
    """Extract time-series metrics from a list of run metadata dicts.

    Returns list sorted by created_at, each entry containing key metrics
    for charting.
    """
    series = []
    for meta in sorted(run_metas, key=lambda m: m.get("created_at", "")):
        metrics = meta.get("metrics", {})
        decision = metrics.get("decision", {})
        classification = metrics.get("classification", {})
        network = metrics.get("network_contact", {})

        series.append({
            "id": meta.get("id", ""),
            "name": meta.get("name", ""),
            "created_at": meta.get("created_at", ""),
            "classifier_engine": meta.get("classifier_engine", ""),
            "model": meta.get("model", ""),
            "prompt_version": meta.get("prompt_version", ""),
            "total_emails": meta.get("total_emails", 0),
            "reviewed_emails": meta.get("reviewed_emails", 0),
            "decision_recall": decision.get("recall", 0),
            "decision_precision": decision.get("precision", 0),
            "decision_f1": decision.get("f1", 0),
            "decision_accuracy": decision.get("accuracy", 0),
            "classification_macro_recall": classification.get("macro_recall", 0),
            "classification_weighted_recall": classification.get("weighted_recall", 0),
            "classification_accuracy": classification.get("accuracy", 0),
            "network_recall": network.get("recall", 0),
            "network_precision": network.get("precision", 0),
        })

    return series
