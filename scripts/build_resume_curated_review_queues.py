from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.services.evals.resume_tailoring_eval import ProjectEvidenceRecord, load_project_evidence


DEFAULT_PROJECT_DIR = Path("docs/ai-artifacts/resume-tailoring-curated-evidence")
DEFAULT_CASES = Path("docs/ai-artifacts/generated/resume-tailoring-curated-evidence/curated_jd_cases_labeled.json")
DEFAULT_OUTPUT_DIR = Path("docs/ai-artifacts/generated/resume-tailoring-curated-evidence-review")


def _load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected list payload in {path}")
    return payload


def _join(values: list[str] | None, sep: str = " | ") -> str:
    return sep.join(str(value) for value in values or [] if value)


def _truncate(text: str, limit: int = 700) -> str:
    normalized = " ".join(str(text or "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3] + "..."


def _evidence_lookup(records: list[ProjectEvidenceRecord]) -> dict[str, ProjectEvidenceRecord]:
    return {record.evidence_id: record for record in records}


def _evidence_summary(evidence_ids: list[str], evidence_by_id: dict[str, ProjectEvidenceRecord]) -> str:
    parts: list[str] = []
    for evidence_id in evidence_ids:
        record = evidence_by_id.get(evidence_id)
        if not record:
            parts.append(f"{evidence_id}: <missing>")
            continue
        parts.append(f"{evidence_id}: {_truncate(record.text, 180)}")
    return " || ".join(parts)


def _accepted_decisions(requirement: dict[str, Any]) -> list[dict[str, Any]]:
    return [decision for decision in requirement.get("citation_label_decisions", []) if decision.get("accepted")]


def _top_decisions(requirement: dict[str, Any], *, limit: int = 8) -> list[dict[str, Any]]:
    decisions = list(requirement.get("citation_label_decisions", []))
    return sorted(
        decisions,
        key=lambda item: (
            not bool(item.get("accepted")),
            -float(item.get("selection_score") or 0),
            str(item.get("evidence_id") or ""),
        ),
    )[:limit]


def build_review_queues(*, project_dir: Path, cases_path: Path, output_dir: Path) -> dict[str, Any]:
    records = load_project_evidence(project_dir)
    evidence_by_id = _evidence_lookup(records)
    cases = _load_cases(cases_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    evidence_queue = output_dir / "curated_evidence_card_review_queue.csv"
    with evidence_queue.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "evidence_id",
                "project_id",
                "project_title",
                "claim",
                "evidence_skills",
                "project_tags",
                "source_path",
                "review_decision",
                "corrected_evidence_skills",
                "corrected_claim",
                "review_notes",
            ],
        )
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "evidence_id": record.evidence_id,
                    "project_id": record.project_id,
                    "project_title": record.title,
                    "claim": record.text,
                    "evidence_skills": _join(record.skills, "; "),
                    "project_tags": _join(record.project_tags, "; "),
                    "source_path": record.source_path,
                    "review_decision": "",
                    "corrected_evidence_skills": "",
                    "corrected_claim": "",
                    "review_notes": "",
                }
            )

    requirement_queue = output_dir / "curated_citation_requirement_review_queue.csv"
    requirement_count = 0
    with requirement_queue.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "case_id",
                "role_title",
                "company",
                "control_type",
                "requirement_id",
                "requirement",
                "current_support_label",
                "review_support_label",
                "review_decision",
                "current_citation_ids",
                "current_citation_claims",
                "candidate_project_ids",
                "legacy_parent_ids",
                "review_expected_citation_ids",
                "review_notes",
            ],
        )
        writer.writeheader()
        for case in cases:
            for requirement in case.get("expected_requirements", []):
                requirement_count += 1
                citation_ids = list(requirement.get("expected_citation_evidence_ids") or [])
                support_label = str(requirement.get("support_label") or "none")
                if support_label == "none":
                    review_decision = "verify_none"
                elif citation_ids:
                    review_decision = "review_current_citations"
                else:
                    review_decision = "needs_manual_citation_or_mark_none"
                writer.writerow(
                    {
                        "case_id": case.get("id", ""),
                        "role_title": case.get("role_title") or case.get("title", ""),
                        "company": case.get("company", ""),
                        "control_type": case.get("control_type", requirement.get("control_type", "")),
                        "requirement_id": requirement.get("id", ""),
                        "requirement": requirement.get("query", ""),
                        "current_support_label": support_label,
                        "review_support_label": "",
                        "review_decision": review_decision,
                        "current_citation_ids": _join(citation_ids),
                        "current_citation_claims": _evidence_summary(citation_ids, evidence_by_id),
                        "candidate_project_ids": _join(requirement.get("curated_candidate_project_ids") or []),
                        "legacy_parent_ids": _join(requirement.get("legacy_expected_parent_evidence_ids") or []),
                        "review_expected_citation_ids": "",
                        "review_notes": "",
                    }
                )

    candidate_queue = output_dir / "curated_citation_candidate_review_queue.csv"
    candidate_count = 0
    with candidate_queue.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "case_id",
                "role_title",
                "company",
                "requirement_id",
                "requirement",
                "current_support_label",
                "evidence_id",
                "project_id",
                "claim",
                "evidence_skills",
                "machine_label",
                "machine_accepted",
                "selection_score",
                "matched_terms",
                "machine_reasons",
                "review_decision",
                "review_support_label",
                "review_notes",
            ],
        )
        writer.writeheader()
        for case in cases:
            for requirement in case.get("expected_requirements", []):
                for decision in _top_decisions(requirement):
                    evidence_id = str(decision.get("evidence_id") or "")
                    record = evidence_by_id.get(evidence_id)
                    candidate_count += 1
                    writer.writerow(
                        {
                            "case_id": case.get("id", ""),
                            "role_title": case.get("role_title") or case.get("title", ""),
                            "company": case.get("company", ""),
                            "requirement_id": requirement.get("id", ""),
                            "requirement": requirement.get("query", ""),
                            "current_support_label": requirement.get("support_label", ""),
                            "evidence_id": evidence_id,
                            "project_id": decision.get("project_id") or (record.project_id if record else ""),
                            "claim": record.text if record else "",
                            "evidence_skills": _join(record.skills if record else [], "; "),
                            "machine_label": decision.get("label", ""),
                            "machine_accepted": str(bool(decision.get("accepted"))).lower(),
                            "selection_score": decision.get("selection_score", ""),
                            "matched_terms": _join(decision.get("matched_terms") or [], "; "),
                            "machine_reasons": _join(decision.get("reasons") or [], "; "),
                            "review_decision": "",
                            "review_support_label": "",
                            "review_notes": "",
                        }
                    )

    instructions = output_dir / "README.md"
    instructions.write_text(
        "\n".join(
            [
                "# Curated Resume Evidence Review Queues",
                "",
                "The JD requirement labels do not need to be restarted from scratch. The support labels from the previous review can be reused as a starting point.",
                "",
                "What changed is the evidence-card ID universe. These queues review whether the new curated cards are valid and whether each JD requirement points to the right evidence IDs.",
                "",
                "## Files",
                "",
                "- `curated_evidence_card_review_queue.csv`: review each curated card as keep/edit/drop and verify the narrow evidence-level skills.",
                "- `curated_citation_requirement_review_queue.csv`: one row per JD requirement; easiest file for compact relabeling.",
                "- `curated_citation_candidate_review_queue.csv`: top machine-selected candidate cards per requirement for detailed accept/reject review.",
                "",
                "## Suggested Label Values",
                "",
                "`review_decision` for evidence cards:",
                "",
                "- `keep`",
                "- `edit`",
                "- `drop`",
                "",
                "`review_decision` for requirement rows:",
                "",
                "- `accept_current`",
                "- `edit_citations`",
                "- `mark_none`",
                "- `needs_more_evidence`",
                "",
                "`review_support_label`:",
                "",
                "- `direct`",
                "- `partial`",
                "- `none`",
                "",
                "Use `corrected_evidence_skills` when a card's skills need to be narrower or broader.",
                "",
                "Use `review_expected_citation_ids` for the final pipe-separated evidence IDs when the current citations need changes.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    summary = {
        "project_dir": str(project_dir),
        "cases_path": str(cases_path),
        "output_dir": str(output_dir),
        "evidence_card_count": len(records),
        "requirement_count": requirement_count,
        "candidate_review_row_count": candidate_count,
        "evidence_queue": str(evidence_queue),
        "requirement_queue": str(requirement_queue),
        "candidate_queue": str(candidate_queue),
        "instructions": str(instructions),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build compact review queues for curated resume evidence and citations.")
    parser.add_argument("--project-dir", type=Path, default=DEFAULT_PROJECT_DIR)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    summary = build_review_queues(project_dir=args.project_dir, cases_path=args.cases, output_dir=args.output_dir)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
