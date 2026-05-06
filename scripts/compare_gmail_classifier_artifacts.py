#!/usr/bin/env python3
"""Compare rules-only and live-LLM Gmail classifier artifact bundles."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.services.evals.artifact_packager import write_feature_artifact_bundle
from backend.services.evals.gmail_classifier_lane_comparison import build_lane_comparison_payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rules-dir", type=Path, required=True)
    parser.add_argument("--live-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("docs/interview-artifacts/generated"))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    payload = build_lane_comparison_payload(rules_dir=args.rules_dir, live_dir=args.live_dir)
    output = write_feature_artifact_bundle(payload, args.output_dir, overwrite=args.overwrite)
    print(output)


if __name__ == "__main__":
    main()
