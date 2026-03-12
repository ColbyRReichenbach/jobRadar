#!/usr/bin/env python3
"""Summarize a reviewed email audit CSV."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


def _normalize_review(value: str) -> str:
    return (value or "").strip().lower()


def _bucket_error_type(row: dict[str, str]) -> str:
    actual = row.get("review_expected_decision", "").strip().lower()
    predicted = row.get("predicted_decision", "").strip().lower()
    if not actual:
        return "unlabeled"
    if actual == "filter" and predicted != "filter":
        return "false_positive"
    if actual != "filter" and predicted == "filter":
        return "false_negative"
    return "misbucket"


def _print_counter(title: str, counter: Counter[str], limit: int = 10) -> None:
    print(f"\n{title}")
    if not counter:
        print("  none")
        return
    for key, count in counter.most_common(limit):
        print(f"  {count:>3}  {key}")


def analyze(csv_path: Path) -> None:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    if not rows:
        raise SystemExit("CSV is empty.")

    reviewed = [row for row in rows if _normalize_review(row.get("review_correct", "")) in {"yes", "no"}]
    correct_rows = [row for row in reviewed if _normalize_review(row.get("review_correct", "")) == "yes"]
    incorrect_rows = [row for row in reviewed if _normalize_review(row.get("review_correct", "")) == "no"]

    print(f"Rows: {len(rows)}")
    print(f"Reviewed: {len(reviewed)}")
    print(f"Correct: {len(correct_rows)}")
    print(f"Incorrect: {len(incorrect_rows)}")
    if reviewed:
        accuracy = len(correct_rows) / len(reviewed)
        print(f"Accuracy: {accuracy:.1%}")

    if not reviewed:
        print("\nNo reviewed rows yet. Fill `review_correct` with yes/no and rerun.")
        return

    decision_pairs = Counter(
        (
            row.get("predicted_decision", "").strip().lower(),
            row.get("review_expected_decision", "").strip().lower() or "(missing)",
        )
        for row in incorrect_rows
    )
    classification_pairs = Counter(
        (
            row.get("predicted_classification", "").strip().lower(),
            row.get("review_expected_classification", "").strip().lower() or "(missing)",
        )
        for row in incorrect_rows
    )

    incorrect_by_domain = Counter((row.get("sender_domain") or "(missing)").lower() for row in incorrect_rows)
    incorrect_by_sender = Counter((row.get("sender_email") or "(missing)").lower() for row in incorrect_rows)
    incorrect_by_reason = Counter((row.get("review_reason") or "(missing)").strip() for row in incorrect_rows)
    incorrect_by_error_type = Counter(_bucket_error_type(row) for row in incorrect_rows)

    print("\nDecision confusion")
    for (predicted, expected), count in decision_pairs.most_common(12):
        print(f"  {count:>3}  predicted={predicted or '(blank)'}  expected={expected or '(blank)'}")

    print("\nClassification confusion")
    for (predicted, expected), count in classification_pairs.most_common(12):
        print(f"  {count:>3}  predicted={predicted or '(blank)'}  expected={expected or '(blank)'}")

    _print_counter("Incorrect by error type", incorrect_by_error_type)
    _print_counter("Top incorrect sender domains", incorrect_by_domain)
    _print_counter("Top incorrect sender emails", incorrect_by_sender)
    _print_counter("Top review reasons", incorrect_by_reason)

    domain_reason_counter: dict[str, Counter[str]] = defaultdict(Counter)
    for row in incorrect_rows:
        domain = (row.get("sender_domain") or "(missing)").lower()
        reason = (row.get("review_reason") or "(missing)").strip()
        domain_reason_counter[domain][reason] += 1

    print("\nDomain -> top reasons")
    for domain, reason_counter in sorted(
        domain_reason_counter.items(),
        key=lambda item: sum(item[1].values()),
        reverse=True,
    )[:10]:
        top_reason, top_count = reason_counter.most_common(1)[0]
        print(f"  {domain}: {top_reason} ({top_count})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a reviewed email audit CSV.")
    parser.add_argument("csv_path", help="Path to the CSV produced by export_email_audit.py")
    args = parser.parse_args()
    analyze(Path(args.csv_path))


if __name__ == "__main__":
    main()
