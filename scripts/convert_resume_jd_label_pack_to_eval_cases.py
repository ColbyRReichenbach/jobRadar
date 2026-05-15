from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


DEFAULT_PACK_DIR = Path("docs/ai-artifacts/generated/resume-tailoring-jd-label-pack")
DEFAULT_OUTPUT = DEFAULT_PACK_DIR / "jd_cases_labeled.json"


def _normalize_id(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower())
    return re.sub(r"_+", "_", text).strip("_") or "case"


def _split_ids(value: str) -> list[str]:
    return [item.strip() for item in (value or "").split("|") if item.strip()]


def _load_job_statuses(saved_jds_path: Path) -> dict[str, str]:
    if not saved_jds_path.exists():
        return {}
    payload = json.loads(saved_jds_path.read_text(encoding="utf-8"))
    statuses: dict[str, str] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        company = str(item.get("company") or "")
        role_title = str(item.get("role_title") or "")
        status = str(item.get("status") or "saved_app")
        if company and role_title:
            statuses[f"{company} - {role_title}"] = status
    return statuses


def _control_type(status: str) -> str:
    if status in {"negative_control", "near_miss_control"}:
        return status
    return "saved_app"


def convert_label_pack_to_cases(
    *,
    compact_csv: Path,
    saved_jds_path: Path,
    output_path: Path,
) -> list[dict[str, Any]]:
    statuses = _load_job_statuses(saved_jds_path)
    rows = list(csv.DictReader(compact_csv.open(newline="", encoding="utf-8")))
    by_job: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_job[row["job"]].append(row)

    cases: list[dict[str, Any]] = []
    for job, job_rows in by_job.items():
        status = statuses.get(job, "saved_app")
        control_type = _control_type(status)
        requirements = []
        for row in job_rows:
            requirements.append(
                {
                    "id": str(row["requirement_id"]),
                    "query": str(row["requirement"]),
                    "expected_evidence_ids": _split_ids(row.get("expected_evidence_ids", "")),
                    "support_label": str(row.get("support_label") or "unsure"),
                    "review_notes": str(row.get("review_notes") or ""),
                    "control_type": control_type,
                }
            )
        cases.append(
            {
                "id": _normalize_id(job),
                "title": job,
                "control_type": control_type,
                "source_status": status,
                "job_description": " ".join(row["requirement"] for row in job_rows),
                "expected_requirements": requirements,
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(cases, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert labeled resume-tailoring JD CSV into eval jd_cases JSON.")
    parser.add_argument("--pack-dir", type=Path, default=DEFAULT_PACK_DIR)
    parser.add_argument("--compact-csv", type=Path, default=None)
    parser.add_argument("--saved-jds", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    compact_csv = args.compact_csv or args.pack_dir / "jd_requirement_label_queue_compact.csv"
    saved_jds = args.saved_jds or args.pack_dir / "saved_jds.json"
    cases = convert_label_pack_to_cases(compact_csv=compact_csv, saved_jds_path=saved_jds, output_path=args.output)
    requirement_count = sum(len(case["expected_requirements"]) for case in cases)
    supported_count = sum(
        1
        for case in cases
        for requirement in case["expected_requirements"]
        if requirement["expected_evidence_ids"]
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "case_count": len(cases),
                "requirement_count": requirement_count,
                "requirements_with_expected_evidence": supported_count,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
