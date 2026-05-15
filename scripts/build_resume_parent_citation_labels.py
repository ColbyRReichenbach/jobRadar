from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.services.evals.resume_project_ingest import (
    PROJECT_DOC_GRANULARITY_ATOMIC,
    extract_project_doc_results,
)
from backend.services.evals.resume_support_verifier import SUPPORT_VERIFIER_VERSION, verify_requirement_evidence
from backend.services.evals.resume_tailoring_eval import project_records_from_doc_results


DEFAULT_INPUT = Path("docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2/jd_cases_labeled.json")
DEFAULT_OUTPUT = Path(
    "docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-parent-citation/jd_cases_parent_citation_labeled.json"
)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value).upper() for value in values if value))


def _load_cases(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_parent_citation_labels(
    *,
    input_path: Path,
    output_path: Path,
    project_doc_dirs: list[Path],
) -> dict[str, Any]:
    cases = _load_cases(input_path)
    atomic_records = project_records_from_doc_results(
        extract_project_doc_results(project_doc_dirs, granularity=PROJECT_DOC_GRANULARITY_ATOMIC)
    )
    children_by_parent: dict[str, list[Any]] = {}
    for record in atomic_records:
        parent_id = (record.parent_evidence_id or record.evidence_id).upper()
        children_by_parent.setdefault(parent_id, []).append(record)

    parent_labeled_count = 0
    citation_labeled_count = 0
    parent_without_citation_count = 0
    accepted_citation_count = 0
    verifier_decision_count = 0

    for case in cases:
        for requirement in case.get("expected_requirements", []):
            parent_ids = _dedupe(
                list(requirement.get("expected_parent_evidence_ids") or requirement.get("expected_evidence_ids") or [])
            )
            citation_ids: list[str] = []
            decision_summary: list[dict[str, Any]] = []
            for parent_id in parent_ids:
                candidates = children_by_parent.get(parent_id, [])
                for record in candidates:
                    decision = verify_requirement_evidence(
                        requirement_text=str(requirement.get("query") or ""),
                        evidence_id=record.evidence_id,
                        evidence_text=record.text,
                        evidence_skills=record.skills,
                        evidence_claim_type=record.claim_type,
                        evidence_section=record.source_section,
                    )
                    verifier_decision_count += 1
                    decision_summary.append(
                        {
                            "evidence_id": record.evidence_id,
                            "parent_evidence_id": record.parent_evidence_id or record.evidence_id,
                            "label": decision.label,
                            "accepted": decision.accepted,
                            "reasons": decision.reasons,
                            "matched_terms": decision.matched_terms,
                            "category_overlap": decision.category_overlap,
                        }
                    )
                    if decision.accepted:
                        citation_ids.append(record.evidence_id)
            citation_ids = _dedupe(citation_ids)
            requirement["expected_evidence_ids"] = parent_ids
            requirement["expected_parent_evidence_ids"] = parent_ids
            requirement["expected_citation_evidence_ids"] = citation_ids
            requirement["citation_label_source"] = f"derived_from_parent_labels_with_{SUPPORT_VERIFIER_VERSION}"
            requirement["citation_label_review_status"] = "machine_derived_needs_human_review"
            requirement["citation_label_decisions"] = decision_summary
            if parent_ids:
                parent_labeled_count += 1
            if citation_ids:
                citation_labeled_count += 1
                accepted_citation_count += len(citation_ids)
            elif parent_ids:
                parent_without_citation_count += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(cases, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        "output": str(output_path),
        "input": str(input_path),
        "case_count": len(cases),
        "requirement_count": sum(len(case.get("expected_requirements", [])) for case in cases),
        "parent_labeled_requirement_count": parent_labeled_count,
        "citation_labeled_requirement_count": citation_labeled_count,
        "parent_without_citation_requirement_count": parent_without_citation_count,
        "accepted_citation_id_count": accepted_citation_count,
        "verifier_decision_count": verifier_decision_count,
        "citation_label_source": f"derived_from_parent_labels_with_{SUPPORT_VERIFIER_VERSION}",
        "limitation": (
            "Citation labels are machine-derived from reviewed parent labels and the deterministic verifier. "
            "Use them for offline diagnostics, not as final human-labeled truth."
        ),
    }
    (output_path.parent / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Derive parent/citation split labels for resume-tailoring evals.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--project-doc-dir", type=Path, action="append", default=[], required=True)
    args = parser.parse_args()
    summary = build_parent_citation_labels(
        input_path=args.input,
        output_path=args.output,
        project_doc_dirs=list(args.project_doc_dir),
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
