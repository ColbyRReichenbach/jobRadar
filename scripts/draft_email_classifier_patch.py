#!/usr/bin/env python3
"""Generate draft classifier constant updates from a reviewed audit CSV."""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path


STOPWORDS = {
    "the", "and", "for", "with", "your", "from", "that", "this", "have", "has",
    "you", "our", "are", "was", "were", "will", "would", "could", "should",
    "but", "into", "they", "them", "their", "about", "more", "just", "than",
    "what", "when", "where", "which", "while", "please", "thank", "thanks",
    "hello", "team", "role", "position", "application", "job", "email", "message",
}


def _normalize(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _tokens(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9][a-z0-9.+_-]*", _normalize(text))
        if len(token) > 2 and token not in STOPWORDS and not token.isdigit()
    ]


def _ngrams(tokens: list[str], n: int) -> list[str]:
    return [" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def _read_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _incorrect_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if _normalize(row.get("review_correct", "")) == "no"]


def _collect_patch_suggestions(rows: list[dict[str, str]], min_hits: int) -> dict[str, list[str]]:
    denylist_domains = Counter()
    denylist_senders = Counter()
    allowlist_domains = Counter()
    allowlist_senders = Counter()
    promotional_phrases = Counter()
    reclassify_phrases: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)

    for row in rows:
        sender_domain = _normalize(row.get("sender_domain", ""))
        sender_email = _normalize(row.get("sender_email", ""))
        subject = row.get("subject", "") or ""
        body = row.get("body_excerpt", "") or ""
        expected_decision = _normalize(row.get("review_expected_decision", ""))
        predicted_decision = _normalize(row.get("predicted_decision", ""))
        expected_classification = _normalize(row.get("review_expected_classification", ""))
        predicted_classification = _normalize(row.get("predicted_classification", ""))

        if expected_decision == "filter" and predicted_decision != "filter":
            if sender_domain:
                denylist_domains[sender_domain] += 1
            if sender_email:
                denylist_senders[sender_email] += 1
            tokens = _tokens(subject)
            promotional_phrases.update(_ngrams(tokens, 2))
            promotional_phrases.update(_ngrams(tokens, 3))
            body_tokens = _tokens(body)
            promotional_phrases.update(_ngrams(body_tokens, 2))
            promotional_phrases.update(_ngrams(body_tokens, 3))

        if expected_decision in {"inbox", "conversation"} and predicted_decision == "filter":
            if sender_domain:
                allowlist_domains[sender_domain] += 1
            if sender_email:
                allowlist_senders[sender_email] += 1

        if expected_classification and predicted_classification and expected_classification != predicted_classification:
            tokens = _tokens(subject)
            if not tokens:
                tokens = _tokens(body)
            for phrase in _ngrams(tokens, 2) + _ngrams(tokens, 3):
                reclassify_phrases[(predicted_classification, expected_classification)][phrase] += 1

    suggestions: dict[str, list[str]] = {}
    suggestions["denylist_domains"] = [domain for domain, count in denylist_domains.most_common() if count >= min_hits]
    suggestions["denylist_senders"] = [sender for sender, count in denylist_senders.most_common() if count >= min_hits]
    suggestions["allowlist_domains"] = [domain for domain, count in allowlist_domains.most_common() if count >= min_hits]
    suggestions["allowlist_senders"] = [sender for sender, count in allowlist_senders.most_common() if count >= min_hits]
    suggestions["promotional_phrases"] = [phrase for phrase, count in promotional_phrases.most_common() if count >= min_hits][:20]

    reclass_lines: list[str] = []
    for (predicted, expected), counter in sorted(
        reclassify_phrases.items(),
        key=lambda item: sum(item[1].values()),
        reverse=True,
    ):
        phrases = [phrase for phrase, count in counter.most_common() if count >= min_hits][:8]
        if not phrases:
            continue
        reclass_lines.append(f"# {predicted} -> {expected}")
        for phrase in phrases:
            reclass_lines.append(f"    {phrase!r},")
    suggestions["reclassify_phrases"] = reclass_lines
    return suggestions


def _render_patch(suggestions: dict[str, list[str]], csv_path: Path, min_hits: int) -> str:
    lines = [
        f"# Draft classifier patch suggestions",
        f"# Source: {csv_path}",
        f"# Minimum repeated mistakes required: {min_hits}",
        "",
        "# Candidate additions for backend/services/email_filter.py or email_classifier.py",
        "",
    ]

    def render_set(name: str, values: list[str]) -> None:
        lines.append(f"{name} = {{")
        for value in values:
            lines.append(f"    {value!r},")
        lines.append("}")
        lines.append("")

    render_set("CANDIDATE_NON_JOB_NOTIFICATION_DOMAINS", suggestions["denylist_domains"])
    render_set("CANDIDATE_NON_JOB_SENDERS", suggestions["denylist_senders"])
    render_set("CANDIDATE_HUMAN_ALLOWLIST_DOMAINS", suggestions["allowlist_domains"])
    render_set("CANDIDATE_HUMAN_ALLOWLIST_SENDERS", suggestions["allowlist_senders"])
    render_set("CANDIDATE_PROMOTIONAL_OR_SYSTEM_HINTS", suggestions["promotional_phrases"])

    lines.append("CANDIDATE_RECLASSIFY_PHRASES = {")
    if suggestions["reclassify_phrases"]:
        current_header = None
        for line in suggestions["reclassify_phrases"]:
            if line.startswith("# "):
                if current_header is not None:
                    lines.append("    ],")
                current_header = line[2:]
                lines.append(f"    {current_header!r}: [")
            else:
                lines.append(line)
        lines.append("    ],")
    lines.append("}")
    lines.append("")
    lines.append("# Review before applying. These are draft suggestions, not auto-approved edits.")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate draft classifier constant updates from a reviewed audit CSV.")
    parser.add_argument("csv_path", help="Path to the reviewed audit CSV.")
    parser.add_argument("--min-hits", type=int, default=2, help="Minimum repeated mistakes before suggesting a rule.")
    parser.add_argument(
        "--output",
        help="Optional output file path. If omitted, the draft patch is printed to stdout.",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    incorrect_rows = _incorrect_rows(_read_rows(csv_path))
    if not incorrect_rows:
        raise SystemExit("No reviewed incorrect rows found. Mark some rows with review_correct=no first.")

    suggestions = _collect_patch_suggestions(incorrect_rows, min_hits=args.min_hits)
    rendered = _render_patch(suggestions, csv_path=csv_path, min_hits=args.min_hits)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
        print(f"Wrote draft patch suggestions to {output_path}")
        return

    print(rendered)


if __name__ == "__main__":
    main()
