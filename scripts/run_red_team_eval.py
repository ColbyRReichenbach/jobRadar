#!/usr/bin/env python3
"""Run offline Copilot red-team eval."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from backend.services.red_team import DEFAULT_RED_TEAM_PATHS, run_red_team_eval, write_red_team_outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AppTrail Copilot red-team eval.")
    parser.add_argument("--dataset", action="append", type=Path, help="JSONL red-team dataset path. May be repeated.")
    parser.add_argument("--report", default="docs/interview-artifacts/red-team-eval.md")
    parser.add_argument("--metrics", default="docs/interview-artifacts/generated/red-team-eval-v1-metrics.json")
    args = parser.parse_args()

    result = run_red_team_eval(args.dataset or DEFAULT_RED_TEAM_PATHS)
    report_path, metrics_path = write_red_team_outputs(
        result,
        report_path=Path(args.report),
        metrics_path=Path(args.metrics),
    )
    print(f"Wrote {report_path}")
    print(f"Wrote {metrics_path}")
    print(f"Fail-closed gate: {result.fail_closed_gate}")


if __name__ == "__main__":
    main()
