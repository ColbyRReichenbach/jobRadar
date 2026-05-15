from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


DEFAULT_METRICS = Path("docs/ai-artifacts/generated/resume-tailoring-real-jd-eval/metrics.json")
DEFAULT_EVIDENCE = Path("docs/ai-artifacts/generated/resume-tailoring-jd-label-pack/evidence_cards_compact.csv")
DEFAULT_OUTPUT = Path("docs/ai-artifacts/generated/resume-tailoring-real-jd-eval/eda_report.md")

STOPWORDS = {
    "a",
    "across",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "our",
    "such",
    "that",
    "the",
    "their",
    "this",
    "to",
    "using",
    "with",
    "you",
    "your",
}
AMBIGUOUS_TERMS = {
    "analysis",
    "analytics",
    "build",
    "data",
    "develop",
    "evaluation",
    "implementation",
    "insights",
    "manage",
    "model",
    "modeling",
    "performance",
    "pipeline",
    "product",
    "reporting",
    "support",
    "systems",
}
DOMAIN_TERMS = {
    "bioinformatics",
    "campaign",
    "genomics",
    "hospitality",
    "imu",
    "lidar",
    "marketing",
    "oncology",
    "perception",
    "quota",
    "robot",
    "robotics",
    "ros",
    "sales",
    "salesforce",
    "sensor",
    "sequencing",
    "slam",
}


def _tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9+.#/-]{2,}", text or "")
        if token.lower() not in STOPWORDS
    }


def _load_evidence(path: Path) -> dict[str, dict[str, str]]:
    evidence: dict[str, dict[str, str]] = {}
    for row in csv.DictReader(path.open(newline="", encoding="utf-8")):
        evidence_id = str(row.get("evidence_id") or "").upper()
        if not evidence_id:
            continue
        normalized = dict(row)
        normalized["evidence_id"] = evidence_id
        normalized["project"] = row.get("project") or row.get("project_id") or row.get("title") or ""
        normalized["claim"] = row.get("claim") or row.get("claim_text") or row.get("text") or ""
        normalized["parent_evidence_id"] = str(row.get("parent_evidence_id") or "").upper()
        evidence[evidence_id] = normalized
    return evidence


def _returned_aliases(row: dict[str, Any], index: int, evidence_id: str) -> set[str]:
    aliases_by_index = row.get("returned_evidence_aliases") or []
    aliases: set[str] = {str(evidence_id).upper()}
    if index < len(aliases_by_index):
        row_aliases = aliases_by_index[index]
        if isinstance(row_aliases, str):
            row_aliases = [row_aliases]
        aliases.update(str(item).upper() for item in row_aliases if item)
    for match in row.get("returned_evidence_matches") or []:
        if str(match.get("evidence_id") or "").upper() == str(evidence_id).upper():
            aliases.update(str(item).upper() for item in match.get("alias_ids") or [] if item)
    return aliases


def _returned_item_is_expected(row: dict[str, Any], index: int, evidence_id: str) -> bool:
    expected = {str(item).upper() for item in row.get("expected_evidence_ids") or []}
    return bool(expected & _returned_aliases(row, index, evidence_id))


def _top_overlap_terms(query: str, evidence_texts: list[str]) -> Counter[str]:
    query_tokens = _tokens(query)
    counter: Counter[str] = Counter()
    for text in evidence_texts:
        counter.update(query_tokens & _tokens(text))
    return counter


def _mean(values: list[float]) -> float:
    return round(mean(values), 6) if values else 0.0


def analyze(metrics_path: Path, evidence_path: Path) -> dict[str, Any]:
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    evidence = _load_evidence(evidence_path)
    rows = metrics["requirement_results"]

    misses = [row for row in rows if row["expected_evidence_ids"] and row["hit_count"] == 0]
    hits = [row for row in rows if row["expected_evidence_ids"] and row["hit_count"] > 0]
    unsupported_returns = [row for row in rows if not row["expected_evidence_ids"] and row["returned_evidence_ids"]]

    returned_counter: Counter[str] = Counter()
    false_returned_counter: Counter[str] = Counter()
    overlap_counter: Counter[str] = Counter()
    ambiguous_overlap_counter: Counter[str] = Counter()
    domain_query_counter: Counter[str] = Counter()
    by_project_false: Counter[str] = Counter()
    by_control_false: Counter[str] = Counter()
    returned_count_by_unsupported: list[int] = []

    for row in rows:
        query_for_analysis = row.get("retrieval_query") or row["query"]
        returned_counter.update(row["returned_evidence_ids"])
        returned_texts = [evidence[item]["claim"] for item in row["returned_evidence_ids"] if item in evidence]
        overlap_counter.update(_top_overlap_terms(query_for_analysis, returned_texts))
        ambiguous_overlap_counter.update(
            term for term in _top_overlap_terms(query_for_analysis, returned_texts) if term in AMBIGUOUS_TERMS
        )
        domain_query_counter.update(_tokens(query_for_analysis) & DOMAIN_TERMS)
        for index, evidence_id in enumerate(row["returned_evidence_ids"]):
            if not _returned_item_is_expected(row, index, evidence_id):
                false_returned_counter[evidence_id] += 1
                if evidence_id in evidence:
                    by_project_false[evidence[evidence_id]["project"]] += 1
        if not row["expected_evidence_ids"]:
            returned_count_by_unsupported.append(len(row["returned_evidence_ids"]))
            by_control_false[row["control_type"]] += int(bool(row["returned_evidence_ids"]))

    examples = {
        "missed_supported": [
            _row_example(row, evidence)
            for row in sorted(misses, key=lambda item: (item["support_label"], item["case_title"], item["requirement_id"]))[:8]
        ],
        "unsupported_false_returns": [
            _row_example(row, evidence)
            for row in sorted(unsupported_returns, key=lambda item: (item["control_type"], item["case_title"], item["requirement_id"]))[:8]
        ],
        "successful_hits": [_row_example(row, evidence) for row in hits[:6]],
    }

    return {
        "acceptance_gate": metrics.get("acceptance_gate", {}),
        "support_verifier": metrics.get("support_verifier", {}),
        "requirement_cleaner": metrics.get("requirement_cleaner", {}),
        "retrieval_metrics": metrics.get("retrieval_metrics", {}),
        "summary": {
            "requirement_count": len(rows),
            "supported_requirement_count": sum(1 for row in rows if row["expected_evidence_ids"]),
            "citation_labeled_requirement_count": sum(1 for row in rows if row.get("expected_citation_evidence_ids")),
            "unsupported_requirement_count": sum(1 for row in rows if not row["expected_evidence_ids"]),
            "supported_miss_count": len(misses),
            "supported_hit_count": len(hits),
            "unsupported_rows_with_returned_evidence": len(unsupported_returns),
            "unsupported_returned_count_mean": _mean(returned_count_by_unsupported),
        },
        "top_returned_evidence": returned_counter.most_common(12),
        "top_false_returned_evidence": false_returned_counter.most_common(12),
        "top_false_returned_projects": by_project_false.most_common(),
        "false_returns_by_control_type": dict(by_control_false),
        "top_overlap_terms": overlap_counter.most_common(25),
        "top_ambiguous_overlap_terms": ambiguous_overlap_counter.most_common(20),
        "domain_terms_in_queries": domain_query_counter.most_common(),
        "examples": examples,
    }


def _row_example(row: dict[str, Any], evidence: dict[str, dict[str, str]]) -> dict[str, Any]:
    query_for_analysis = row.get("retrieval_query") or row["query"]
    returned = []
    for index, evidence_id in enumerate(row["returned_evidence_ids"][:5]):
        card = evidence.get(evidence_id, {})
        returned.append(
            {
                "evidence_id": evidence_id,
                "aliases": sorted(_returned_aliases(row, index, evidence_id)),
                "project": card.get("project", ""),
                "claim": card.get("claim", ""),
                "overlap_terms": sorted(_tokens(query_for_analysis) & _tokens(card.get("claim", ""))),
                "is_expected": _returned_item_is_expected(row, index, evidence_id),
            }
        )
    return {
        "case_title": row["case_title"],
        "requirement_id": row["requirement_id"],
        "support_label": row["support_label"],
        "control_type": row["control_type"],
        "query": row["query"],
        "retrieval_query": query_for_analysis,
        "requirement_cleaner": row.get("requirement_cleaner", {}),
        "retrieval_skipped_by_cleaner": row.get("retrieval_skipped_by_cleaner", False),
        "expected_evidence_ids": row["expected_evidence_ids"],
        "returned": returned,
    }


def _render_report(analysis: dict[str, Any]) -> str:
    gate = analysis.get("acceptance_gate") or {}
    support = analysis.get("support_verifier") or {}
    cleaner = analysis.get("requirement_cleaner") or {}
    retrieval_metrics = analysis.get("retrieval_metrics") or {}
    gate_enabled = bool(gate.get("enabled"))
    lines = [
        "# Resume Retrieval EDA",
        "",
        (
            "This report inspects accepted evidence after the lexical acceptance gate on the labeled resume-tailoring JD holdout."
            if gate_enabled
            else "This report inspects why raw lexical retrieval is failing on the labeled resume-tailoring JD holdout."
        ),
        "",
        "## Summary",
        "",
    ]
    for key, value in analysis["summary"].items():
        lines.append(f"- {key}: `{value}`")
    if retrieval_metrics:
        lines.extend(
            [
                "",
                "## Parent vs Citation Metrics",
                "",
                f"- parent_recall_at_k_mean: `{retrieval_metrics.get('parent_recall_at_k_mean')}`",
                f"- parent_precision_at_k_mean: `{retrieval_metrics.get('parent_precision_at_k_mean')}`",
                f"- citation_recall_at_k_mean: `{retrieval_metrics.get('citation_recall_at_k_mean')}`",
                f"- citation_precision_at_k_mean: `{retrieval_metrics.get('citation_precision_at_k_mean')}`",
                f"- parent_supported_without_citation_labels: `{retrieval_metrics.get('parent_supported_without_citation_labels')}`",
            ]
        )
    if gate:
        lines.extend(
            [
                "",
                "## Acceptance Gate",
                "",
                f"- enabled: `{gate.get('enabled')}`",
                f"- version: `{gate.get('version')}`",
                f"- raw_candidate_count: `{gate.get('raw_candidate_count')}`",
                f"- accepted_candidate_count: `{gate.get('accepted_candidate_count')}`",
                f"- rejected_candidate_count: `{gate.get('rejected_candidate_count')}`",
                f"- raw_unsupported_false_support_rate: `{gate.get('raw_unsupported_false_support_rate')}`",
                f"- accepted_unsupported_false_support_rate: `{gate.get('accepted_unsupported_false_support_rate')}`",
                f"- rejection_reason_counts: `{gate.get('rejection_reason_counts')}`",
                f"- missing_domain_group_counts: `{gate.get('missing_domain_group_counts')}`",
            ]
        )
    if cleaner:
        lines.extend(
            [
                "",
                "## Requirement Cleaner",
                "",
                f"- enabled: `{cleaner.get('enabled')}`",
                f"- skipped_requirement_count: `{cleaner.get('skipped_requirement_count')}`",
                f"- skipped_supported_requirement_count: `{cleaner.get('skipped_supported_requirement_count')}`",
                f"- skipped_unsupported_requirement_count: `{cleaner.get('skipped_unsupported_requirement_count')}`",
                f"- category_counts: `{cleaner.get('category_counts')}`",
                f"- reason_counts: `{cleaner.get('reason_counts')}`",
            ]
        )
    if support:
        lines.extend(
            [
                "",
                "## Pairwise Support Verifier",
                "",
                f"- enabled: `{support.get('enabled')}`",
                f"- version: `{support.get('version')}`",
                f"- candidate_count: `{support.get('candidate_count')}`",
                f"- accepted_candidate_count: `{support.get('accepted_candidate_count')}`",
                f"- rejected_candidate_count: `{support.get('rejected_candidate_count')}`",
                f"- accepted_candidate_rate: `{support.get('accepted_candidate_rate')}`",
                f"- unsupported_false_support_rate: `{support.get('unsupported_false_support_rate')}`",
                f"- supported_rows_rejected_to_zero: `{support.get('supported_rows_rejected_to_zero')}`",
                f"- label_counts: `{support.get('label_counts')}`",
                f"- rejection_reason_counts: `{support.get('rejection_reason_counts')}`",
                f"- missing_domain_group_counts: `{support.get('missing_domain_group_counts')}`",
            ]
        )
    lines.extend(
        [
            "",
            "## What Accepted Evidence Is Matching" if gate_enabled else "## What Lexical Is Matching",
            "",
            "Top overlap terms across accepted evidence:" if gate_enabled else "Top overlap terms across returned evidence:",
            "",
            _format_counter(analysis["top_overlap_terms"]),
            "",
            "Ambiguous overlap terms that often cause false support:",
            "",
            _format_counter(analysis["top_ambiguous_overlap_terms"]),
            "",
            "Domain terms present in queries that should often force abstention unless evidence also contains that domain:",
            "",
            _format_counter(analysis["domain_terms_in_queries"]),
            "",
            "## False Return Concentration",
            "",
            "Top evidence cards returned when they were not expected:",
            "",
            _format_counter(analysis["top_false_returned_evidence"]),
            "",
            "Projects overrepresented in false returns:",
            "",
            _format_counter(analysis["top_false_returned_projects"]),
            "",
            "Unsupported false returns by control type:",
            "",
            _format_mapping(analysis["false_returns_by_control_type"]),
            "",
            "## Examples",
            "",
        ]
    )
    for section, examples in analysis["examples"].items():
        lines.extend([f"### {section.replace('_', ' ').title()}", ""])
        for example in examples:
            lines.extend(_render_example(example))
            lines.append("")
    lines.extend(
        [
            "## EDA Takeaways",
            "",
            "- Lexical retrieval overweights broad words like `data`, `model`, `analytics`, `pipeline`, `product`, and `performance`.",
            "- Negative-control sales and marketing rows still retrieve evidence because broad business words overlap with product/analytics project descriptions.",
            "- Near-miss robotics and bioinformatics rows expose the same weakness: generic ML/Python terms match, while missing domain anchors like `ROS`, `LiDAR`, `sequencing`, and `single-cell` are not treated as abstention triggers.",
            "- Some strong expected cards are missed because evidence cards use project-specific language while JD rows use generic role language.",
            "- If the cleaner and acceptance gate are enabled, remaining misses are less about boilerplate and more about representation: broad cards help recall, but smaller citation cards help false-support control.",
            "- Before embeddings, the next lexical baseline should test multi-granularity retrieval: broad cards for recall, child evidence cards for citation and support checks.",
            "",
        ]
    )
    return "\n".join(lines)


def _format_counter(items: list[tuple[str, int]]) -> str:
    if not items:
        return "- none"
    return "\n".join(f"- `{key}`: {value}" for key, value in items)


def _format_mapping(mapping: dict[str, int]) -> str:
    if not mapping:
        return "- none"
    return "\n".join(f"- `{key}`: {value}" for key, value in sorted(mapping.items()))


def _render_example(example: dict[str, Any]) -> list[str]:
    lines = [
        f"- `{example['case_title']}` / `{example['requirement_id']}` / `{example['support_label']}` / `{example['control_type']}`",
        f"  - query: {example['query']}",
    ]
    if example.get("retrieval_query") and example["retrieval_query"] != example["query"]:
        lines.append(f"  - retrieval_query: {example['retrieval_query']}")
    cleaner = example.get("requirement_cleaner") or {}
    if cleaner:
        lines.append(
            f"  - cleaner: category={cleaner.get('category')} policy={cleaner.get('retrieval_policy')} reasons={cleaner.get('reasons')}"
        )
    lines.extend([f"  - expected: `{example['expected_evidence_ids'] or []}`", "  - returned:"])
    for returned in example["returned"]:
        lines.append(
            f"    - `{returned['evidence_id']}` expected={returned['is_expected']} aliases={returned.get('aliases', [])} overlap={returned['overlap_terms']} project={returned['project']}"
        )
        lines.append(f"      - {returned['claim']}")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze lexical retrieval failures for resume-tailoring evals.")
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    analysis = analyze(args.metrics, args.evidence)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(_render_report(analysis), encoding="utf-8")
    print(json.dumps({"output": str(args.output), **analysis["summary"]}, sort_keys=True))


if __name__ == "__main__":
    main()
