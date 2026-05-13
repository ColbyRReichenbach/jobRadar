#!/usr/bin/env python3
"""Run offline Copilot groundedness eval."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from backend.services.evals.assistant_eval import run_copilot_eval, write_copilot_eval_outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AppTrail Copilot eval.")
    parser.add_argument("--dataset", default="evals/copilot/copilot_questions_v1.jsonl")
    parser.add_argument("--report", default="docs/ai-artifacts/copilot-eval.md")
    parser.add_argument("--metrics", default="docs/ai-artifacts/generated/copilot-eval-v1-metrics.json")
    args = parser.parse_args()

    result = run_copilot_eval(Path(args.dataset))
    report_path, metrics_path = write_copilot_eval_outputs(
        result,
        report_path=Path(args.report),
        metrics_path=Path(args.metrics),
    )
    print(f"Wrote {report_path}")
    print(f"Wrote {metrics_path}")
    print(f"Pass rate: {result.metrics['pass_rate']}")


if __name__ == "__main__":
    main()
