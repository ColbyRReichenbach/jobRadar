from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from backend.services.retrieval.eval_gate import DEFAULT_K, write_retrieval_eval_gate_artifact


def main() -> None:
    parser = argparse.ArgumentParser(description="Write the local retrieval eval gate comparison artifact.")
    parser.add_argument(
        "--output",
        default="docs/interview-artifacts/generated/local-retrieval-eval-gate.json",
        help="Output JSON path.",
    )
    parser.add_argument("--k", type=int, default=DEFAULT_K, help="Retrieval cutoff for comparison metrics.")
    args = parser.parse_args()
    output_path = asyncio.run(write_retrieval_eval_gate_artifact(Path(args.output), k=args.k))
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
