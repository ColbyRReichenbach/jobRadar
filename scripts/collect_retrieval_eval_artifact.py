from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from backend.services.retrieval.eval_artifacts import write_local_retrieval_eval_artifact


def main() -> None:
    parser = argparse.ArgumentParser(description="Write the local retrieval foundation eval artifact.")
    parser.add_argument(
        "--output",
        default="docs/ai-artifacts/generated/local-retrieval-eval.json",
        help="Output JSON path.",
    )
    args = parser.parse_args()
    output_path = write_local_retrieval_eval_artifact(Path(args.output))
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
