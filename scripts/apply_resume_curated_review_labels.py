from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.services.evals.resume_tailoring_eval import load_project_evidence


DEFAULT_INPUT = Path("docs/ai-artifacts/generated/resume-tailoring-curated-evidence/curated_jd_cases_labeled.json")
DEFAULT_REVIEW_CSV = Path(
    "docs/ai-artifacts/generated/resume-tailoring-curated-evidence-review/"
    "curated_citation_requirement_review_queue.csv"
)
DEFAULT_PROJECT_DIR = Path("docs/ai-artifacts/resume-tailoring-curated-evidence")
DEFAULT_OUTPUT = Path(
    "docs/ai-artifacts/generated/resume-tailoring-curated-evidence-reviewed/"
    "curated_jd_cases_reviewed.json"
)
REVIEW_SOURCE = "curated_citation_requirement_review_queue_human_reviewed_v1"


def _split_pipe(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split("|") if item.strip()]


def _load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected list payload in {path}")
    return payload


def _load_review_rows(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    rows: dict[tuple[str, str], dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = (str(row.get("case_id") or ""), str(row.get("requirement_id") or ""))
            if not all(key):
                raise ValueError(f"Review row missing case_id or requirement_id: {row}")
            if key in rows:
                raise ValueError(f"Duplicate review row for {key}")
            rows[key] = row
    return rows


def _reviewed_ids(row: dict[str, str]) -> list[str]:
    decision = str(row.get("review_decision") or "").strip()
    support_label = str(row.get("review_support_label") or "").strip()
    edited_ids = _split_pipe(row.get("review_expected_citation_ids", ""))
    current_ids = _split_pipe(row.get("current_citation_ids", ""))

    if decision == "mark_none" or support_label == "none":
        return []
    if decision == "accept_current":
        return edited_ids or current_ids
    if decision == "edit_citations":
        if not edited_ids:
            raise ValueError(
                "edit_citations rows must provide review_expected_citation_ids: "
                f"{row.get('case_id')} {row.get('requirement_id')}"
            )
        return edited_ids
    raise ValueError(
        "Unexpected review_decision in curated requirement review queue: "
        f"{decision!r} for {row.get('case_id')} {row.get('requirement_id')}"
    )


def apply_review_labels(
    *,
    input_path: Path,
    review_csv: Path,
    project_dir: Path,
    output_path: Path,
) -> dict[str, Any]:
    cases = _load_cases(input_path)
    review_rows = _load_review_rows(review_csv)
    known_evidence_ids = {record.evidence_id for record in load_project_evidence(project_dir)}

    applied_keys: set[tuple[str, str]] = set()
    support_counts: Counter[str] = Counter()
    decision_counts: Counter[str] = Counter()
    citation_labeled_count = 0
    citation_id_count = 0

    for case in cases:
        case_id = str(case.get("id") or "")
        for requirement in case.get("expected_requirements", []):
            requirement_id = str(requirement.get("id") or "")
            key = (case_id, requirement_id)
            row = review_rows.get(key)
            if row is None:
                raise ValueError(f"Missing review row for {case_id} {requirement_id}")

            support_label = str(row.get("review_support_label") or "").strip()
            if support_label not in {"direct", "partial", "none"}:
                raise ValueError(f"Invalid review_support_label {support_label!r} for {case_id} {requirement_id}")

            citation_ids = _reviewed_ids(row)
            unknown_ids = [evidence_id for evidence_id in citation_ids if evidence_id not in known_evidence_ids]
            if unknown_ids:
                raise ValueError(f"Unknown citation ids for {case_id} {requirement_id}: {unknown_ids}")
            if support_label in {"direct", "partial"} and not citation_ids:
                raise ValueError(f"Supported review row has no citation ids: {case_id} {requirement_id}")

            requirement["support_label"] = support_label
            requirement["expected_evidence_ids"] = citation_ids
            requirement["expected_parent_evidence_ids"] = citation_ids
            requirement["expected_citation_evidence_ids"] = citation_ids
            requirement["citation_label_source"] = REVIEW_SOURCE
            requirement["citation_label_review_status"] = "human_reviewed"
            requirement["review_decision"] = str(row.get("review_decision") or "").strip()
            requirement["review_notes"] = str(row.get("review_notes") or "")
            requirement["reviewed_current_citation_ids"] = _split_pipe(row.get("current_citation_ids", ""))

            applied_keys.add(key)
            support_counts[support_label] += 1
            decision_counts[requirement["review_decision"]] += 1
            if citation_ids:
                citation_labeled_count += 1
                citation_id_count += len(citation_ids)

    unused_rows = sorted(set(review_rows) - applied_keys)
    if unused_rows:
        raise ValueError(f"Review rows did not match eval cases: {unused_rows[:10]}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(cases, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    summary = {
        "input": str(input_path),
        "review_csv": str(review_csv),
        "output": str(output_path),
        "review_source": REVIEW_SOURCE,
        "case_count": len(cases),
        "requirement_count": sum(len(case.get("expected_requirements", [])) for case in cases),
        "citation_labeled_requirement_count": citation_labeled_count,
        "citation_id_count": citation_id_count,
        "support_label_counts": dict(sorted(support_counts.items())),
        "review_decision_counts": dict(sorted(decision_counts.items())),
    }
    (output_path.parent / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply reviewed curated citation labels to resume-tailoring eval cases.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--review-csv", type=Path, default=DEFAULT_REVIEW_CSV)
    parser.add_argument("--project-dir", type=Path, default=DEFAULT_PROJECT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    summary = apply_review_labels(
        input_path=args.input,
        review_csv=args.review_csv,
        project_dir=args.project_dir,
        output_path=args.output,
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
