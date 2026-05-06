#!/usr/bin/env python3
"""Generate deterministic synthetic eval inputs for local artifact runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.services.evals.synthetic_fixtures import generate_all_synthetic_eval_inputs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."), help="Repository root or temporary output root.")
    parser.add_argument("--dry-run", action="store_true", help="Print target paths without writing files.")
    args = parser.parse_args()

    if args.dry_run:
        print(
            json.dumps(
                {
                    "schema_version": "synthetic_eval_inputs_v1",
                    "dry_run": True,
                    "root": str(args.root),
                    "targets": [
                        "evals/copilot/copilot_router_synthetic_v1.jsonl",
                        "evals/copilot/copilot_questions_synthetic_v1.jsonl",
                        "evals/email_classifier/email_classifier_synthetic_v1.jsonl",
                        "evals/radar/radar_evidence_quality_synthetic_v1.jsonl",
                        "evals/search/search_documents_synthetic_v1.json",
                        "evals/search/search_queries_synthetic_v1.jsonl",
                        "evals/search/search_baselines_synthetic_v1.json",
                        "evals/red_team/synthetic_safety_v1.jsonl",
                        "evals/synthetic_manifest.json",
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    manifest = generate_all_synthetic_eval_inputs(args.root)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
