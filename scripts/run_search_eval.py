#!/usr/bin/env python3
"""Run deterministic search eval and write interview artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.services.evals.search_eval import (
    DEFAULT_BASELINES_PATH,
    DEFAULT_DOCUMENTS_PATH,
    DEFAULT_QUERIES_PATH,
    run_search_eval,
    write_search_eval_outputs,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AppTrail search retrieval eval.")
    parser.add_argument("--documents", default=str(DEFAULT_DOCUMENTS_PATH))
    parser.add_argument("--queries", default=str(DEFAULT_QUERIES_PATH))
    parser.add_argument("--baselines", default=str(DEFAULT_BASELINES_PATH))
    parser.add_argument("--report", default="docs/interview-artifacts/search-eval.md")
    parser.add_argument("--metrics", default="docs/interview-artifacts/generated/search-eval-v1-metrics.json")
    args = parser.parse_args()

    result = run_search_eval(
        documents_path=Path(args.documents),
        queries_path=Path(args.queries),
        baselines_path=Path(args.baselines),
    )
    report_path, metrics_path = write_search_eval_outputs(
        result,
        report_path=Path(args.report),
        metrics_path=Path(args.metrics),
    )
    print(f"Wrote {report_path}")
    print(f"Wrote {metrics_path}")
    print(f"Recommended strategy: {result.recommended_strategy}")


if __name__ == "__main__":
    main()
