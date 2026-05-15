from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.services.evals.resume_support_verifier import SUPPORT_VERIFIER_VERSION, verify_requirement_evidence
from backend.services.evals.resume_tailoring_eval import ProjectEvidenceRecord, load_project_evidence


DEFAULT_INPUT = Path("docs/ai-artifacts/generated/resume-tailoring-jd-expansion-v3/jd_cases_labeled.json")
DEFAULT_PROJECT_DIR = Path("docs/ai-artifacts/resume-tailoring-curated-evidence")
DEFAULT_OUTPUT = Path(
    "docs/ai-artifacts/generated/resume-tailoring-curated-evidence/curated_jd_cases_labeled.json"
)
DEFAULT_MAX_CITATIONS_PER_REQUIREMENT = 5

PROJECT_PREFIXES = {
    "EV-APPTRAIL_JOBRADAR_": "apptrail",
    "EV-SPEC_NYC_SPEC_NYC_": "spec_nyc",
    "EV-SHELFOPS_SHELFOPS_": "shelfops",
    "EV-AIBS_ABS_OBSERVATO": "aibs_abs_observatory",
    "EV-PULSE_TRACKER_WORK": "pulse_tracker",
    "EV-AUGUSTA_DEFENDED_M": "augusta_defended",
}

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+.#/-]*")
STOPWORDS = {
    "a",
    "an",
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
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "with",
}


def _load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected list payload in {path}")
    return payload


def _projects_for_parent_ids(parent_ids: list[str]) -> list[str]:
    projects: list[str] = []
    for evidence_id in parent_ids:
        upper_id = str(evidence_id).upper()
        for prefix, project_id in PROJECT_PREFIXES.items():
            if upper_id.startswith(prefix):
                projects.append(project_id)
                break
    return list(dict.fromkeys(projects))


def _records_by_project(records: list[ProjectEvidenceRecord]) -> dict[str, list[ProjectEvidenceRecord]]:
    by_project: dict[str, list[ProjectEvidenceRecord]] = {}
    for record in records:
        by_project.setdefault(record.project_id, []).append(record)
    return by_project


def _tokens(text: str) -> set[str]:
    return {token for token in TOKEN_RE.findall(text.lower()) if token not in STOPWORDS and len(token) > 2}


def _decision_score(*, requirement_text: str, record: ProjectEvidenceRecord, decision: Any) -> float:
    query_tokens = _tokens(requirement_text)
    evidence_tokens = _tokens(record.text)
    overlap = query_tokens & evidence_tokens
    label_weight = 100.0 if decision.label == "supports" else 55.0
    category_weight = 4.0 * len(decision.category_overlap)
    matched_weight = 6.0 * len(decision.matched_terms)
    overlap_weight = 2.0 * len(overlap)
    strength_weight = 8.0 if record.evidence_strength == "high" else 3.0 if record.evidence_strength == "medium" else 0.0
    return label_weight + category_weight + matched_weight + overlap_weight + strength_weight


def build_curated_labels(
    *,
    input_path: Path,
    project_dir: Path,
    output_path: Path,
    max_citations_per_requirement: int = DEFAULT_MAX_CITATIONS_PER_REQUIREMENT,
) -> dict[str, Any]:
    cases = _load_cases(input_path)
    records = load_project_evidence(project_dir)
    records_by_project = _records_by_project(records)

    labeled_requirement_count = 0
    parent_supported_without_curated_citation_count = 0
    accepted_citation_id_count = 0
    verifier_decision_count = 0
    support_label_counts: Counter[str] = Counter()
    project_counts: Counter[str] = Counter()

    for case in cases:
        for requirement in case.get("expected_requirements", []):
            legacy_parent_ids = list(
                requirement.get("expected_parent_evidence_ids")
                or requirement.get("expected_evidence_ids")
                or []
            )
            support_label = str(requirement.get("support_label") or ("direct" if legacy_parent_ids else "none"))
            support_label_counts[support_label] += 1
            project_ids = _projects_for_parent_ids(legacy_parent_ids)
            candidate_records: list[ProjectEvidenceRecord] = []
            for project_id in project_ids:
                project_counts[project_id] += 1
                candidate_records.extend(records_by_project.get(project_id, []))

            scored_citations: list[tuple[float, str]] = []
            decisions: list[dict[str, Any]] = []
            requirement_text = str(requirement.get("query") or "")
            if support_label != "none":
                for record in candidate_records:
                    decision = verify_requirement_evidence(
                        requirement_text=requirement_text,
                        evidence_id=record.evidence_id,
                        evidence_text=record.text,
                        evidence_skills=record.skills,
                        evidence_claim_type=record.claim_type,
                        evidence_section=record.source_section,
                    )
                    verifier_decision_count += 1
                    score = _decision_score(requirement_text=requirement_text, record=record, decision=decision)
                    decisions.append(
                        {
                            "evidence_id": record.evidence_id,
                            "project_id": record.project_id,
                            "label": decision.label,
                            "accepted": decision.accepted,
                            "selection_score": round(score, 3),
                            "reasons": decision.reasons,
                            "matched_terms": decision.matched_terms,
                            "category_overlap": decision.category_overlap,
                        }
                    )
                    if decision.accepted:
                        scored_citations.append((score, record.evidence_id))

            support_labels = {
                decision["label"]
                for decision in decisions
                if decision.get("accepted")
            }
            preferred_labels = {"supports"} if "supports" in support_labels else {"partial_support"}
            scored_citations = [
                (score, evidence_id)
                for score, evidence_id in scored_citations
                if any(
                    decision["evidence_id"] == evidence_id
                    and decision.get("accepted")
                    and decision.get("label") in preferred_labels
                    for decision in decisions
                )
            ]
            scored_citations = sorted(scored_citations, key=lambda item: (-item[0], item[1]))
            citation_ids = list(
                dict.fromkeys(evidence_id for _, evidence_id in scored_citations[:max_citations_per_requirement])
            )
            requirement["legacy_expected_parent_evidence_ids"] = legacy_parent_ids
            requirement["curated_candidate_project_ids"] = project_ids
            requirement["expected_evidence_ids"] = citation_ids
            requirement["expected_parent_evidence_ids"] = citation_ids
            requirement["expected_citation_evidence_ids"] = citation_ids
            requirement["citation_label_source"] = (
                f"curated_cards_derived_from_project_scoped_parent_labels_with_{SUPPORT_VERIFIER_VERSION}"
            )
            requirement["citation_label_review_status"] = "machine_derived_needs_human_review"
            requirement["citation_label_decisions"] = decisions
            if citation_ids:
                labeled_requirement_count += 1
                accepted_citation_id_count += len(citation_ids)
            elif legacy_parent_ids and support_label != "none":
                parent_supported_without_curated_citation_count += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(cases, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    evidence_cards_path = output_path.parent / "curated_evidence_cards.csv"
    with evidence_cards_path.open("w", newline="", encoding="utf-8") as handle:
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
                    "evidence_skills": "; ".join(record.skills),
                    "project_tags": "; ".join(record.project_tags),
                    "source_path": record.source_path,
                }
            )
    summary = {
        "input": str(input_path),
        "output": str(output_path),
        "curated_evidence_cards_csv": str(evidence_cards_path),
        "project_dir": str(project_dir),
        "case_count": len(cases),
        "requirement_count": sum(len(case.get("expected_requirements", [])) for case in cases),
        "curated_evidence_count": len(records),
        "curated_labeled_requirement_count": labeled_requirement_count,
        "max_citations_per_requirement": max_citations_per_requirement,
        "parent_supported_without_curated_citation_count": parent_supported_without_curated_citation_count,
        "accepted_citation_id_count": accepted_citation_id_count,
        "verifier_decision_count": verifier_decision_count,
        "support_label_counts": dict(sorted(support_label_counts.items())),
        "candidate_project_counts": dict(sorted(project_counts.items())),
        "citation_label_source": f"project_scoped_parent_labels_with_{SUPPORT_VERIFIER_VERSION}",
        "limitation": (
            "Curated citation labels are machine-derived from existing reviewed parent labels and "
            "the deterministic support verifier. Use for offline diagnostics, then human-review."
        ),
    }
    (output_path.parent / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Map reviewed resume JD labels onto curated project evidence cards.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--project-dir", type=Path, default=DEFAULT_PROJECT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-citations-per-requirement", type=int, default=DEFAULT_MAX_CITATIONS_PER_REQUIREMENT)
    args = parser.parse_args()
    summary = build_curated_labels(
        input_path=args.input,
        project_dir=args.project_dir,
        output_path=args.output,
        max_citations_per_requirement=args.max_citations_per_requirement,
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
