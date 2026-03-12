#!/usr/bin/env python3
"""Suggest classifier rule updates from a reviewed email audit CSV."""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path


STOPWORDS = {
    "the", "and", "for", "with", "your", "from", "that", "this", "have", "has",
    "you", "our", "are", "was", "were", "will", "not", "but", "into", "they",
    "them", "their", "about", "just", "more", "here", "than", "what", "when",
    "where", "which", "while", "would", "could", "should", "please", "thanks",
    "thank", "hello", "hi", "team", "role", "position", "application", "job",
}


def _normalize(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _tokens(text: str) -> list[str]:
    return [
        token for token in re.findall(r"[a-z0-9][a-z0-9.+_-]*", _normalize(text))
        if len(token) > 2 and token not in STOPWORDS and not token.isdigit()
    ]


def _ngrams(tokens: list[str], n: int) -> list[str]:
    return [" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def _read_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _reviewed_incorrect(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    incorrect = []
    for row in rows:
        if (row.get("review_correct") or "").strip().lower() != "no":
            continue
        incorrect.append(row)
    return incorrect


def _expected_decision(row: dict[str, str]) -> str:
    return _normalize(row.get("review_expected_decision", ""))


def _predicted_decision(row: dict[str, str]) -> str:
    return _normalize(row.get("predicted_decision", ""))


def _expected_classification(row: dict[str, str]) -> str:
    return _normalize(row.get("review_expected_classification", ""))


def _predicted_classification(row: dict[str, str]) -> str:
    return _normalize(row.get("predicted_classification", ""))


def suggest(csv_path: Path, min_hits: int) -> None:
    rows = _read_rows(csv_path)
    incorrect = _reviewed_incorrect(rows)
    if not incorrect:
        raise SystemExit("No reviewed incorrect rows found. Fill `review_correct=no` rows first.")

    denylist_domains = Counter()
    denylist_senders = Counter()
    allowlist_senders = Counter()
    allowlist_domains = Counter()
    subject_phrases = Counter()
    body_phrases = Counter()
    reclassify_phrases: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)

    for row in incorrect:
        sender_domain = _normalize(row.get("sender_domain", ""))
        sender_email = _normalize(row.get("sender_email", ""))
        subject = row.get("subject", "") or ""
        body = row.get("body_excerpt", "") or ""
        expected_decision = _expected_decision(row)
        predicted_decision = _predicted_decision(row)
        expected_class = _expected_classification(row)
        predicted_class = _predicted_classification(row)

        if expected_decision == "filter" and predicted_decision != "filter":
            if sender_domain:
                denylist_domains[sender_domain] += 1
            if sender_email:
                denylist_senders[sender_email] += 1
            tokens = _tokens(subject)
            subject_phrases.update(_ngrams(tokens, 2))
            subject_phrases.update(_ngrams(tokens, 3))
            body_tokens = _tokens(body)
            body_phrases.update(_ngrams(body_tokens, 2))
            body_phrases.update(_ngrams(body_tokens, 3))

        if expected_decision in {"inbox", "conversation"} and predicted_decision == "filter":
            if sender_email:
                allowlist_senders[sender_email] += 1
            if sender_domain:
                allowlist_domains[sender_domain] += 1

        if expected_class and predicted_class and expected_class != predicted_class:
            tokens = _tokens(subject)
            if not tokens:
                tokens = _tokens(body)
            for phrase in _ngrams(tokens, 2) + _ngrams(tokens, 3):
                reclassify_phrases[(predicted_class, expected_class)][phrase] += 1

    print(f"Analyzed {len(incorrect)} incorrect reviewed rows from {csv_path}")

    print("\nCandidate denylist domains")
    for domain, count in denylist_domains.most_common():
        if count < min_hits:
            continue
        print(f"  {domain}  ({count})")

    print("\nCandidate denylist sender emails")
    for sender, count in denylist_senders.most_common():
        if count < min_hits:
            continue
        print(f"  {sender}  ({count})")

    print("\nCandidate allowlist sender emails")
    for sender, count in allowlist_senders.most_common():
        if count < min_hits:
            continue
        print(f"  {sender}  ({count})")

    print("\nCandidate allowlist domains")
    for domain, count in allowlist_domains.most_common():
        if count < min_hits:
            continue
        print(f"  {domain}  ({count})")

    print("\nHigh-signal subject phrases for filter rules")
    shown = 0
    for phrase, count in subject_phrases.most_common():
        if count < min_hits or phrase.strip() == "":
            continue
        print(f"  {phrase}  ({count})")
        shown += 1
        if shown >= 15:
            break

    print("\nHigh-signal body phrases for filter rules")
    shown = 0
    for phrase, count in body_phrases.most_common():
        if count < min_hits or phrase.strip() == "":
            continue
        print(f"  {phrase}  ({count})")
        shown += 1
        if shown >= 15:
            break

    print("\nClassification phrase suggestions")
    for (predicted, expected), phrase_counter in sorted(
        reclassify_phrases.items(),
        key=lambda item: sum(item[1].values()),
        reverse=True,
    ):
        top = [(phrase, count) for phrase, count in phrase_counter.most_common() if count >= min_hits][:8]
        if not top:
            continue
        print(f"  predicted={predicted} -> expected={expected}")
        for phrase, count in top:
            print(f"    {phrase}  ({count})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Suggest classifier rule changes from a reviewed email audit CSV.")
    parser.add_argument("csv_path", help="Path to the reviewed audit CSV.")
    parser.add_argument("--min-hits", type=int, default=2, help="Minimum repeated mistakes before suggesting a rule.")
    args = parser.parse_args()
    suggest(Path(args.csv_path), min_hits=args.min_hits)


if __name__ == "__main__":
    main()
