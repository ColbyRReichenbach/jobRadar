#!/usr/bin/env python3
"""Regenerate the AI progress-over-time index from generated report folders."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.services.reports.progress_index import write_progress_index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated-dir", default="docs/interview-artifacts/generated", help="Generated report directory")
    parser.add_argument(
        "--output",
        default="docs/interview-artifacts/ai-system-progress-over-time.md",
        help="Progress index markdown path",
    )
    args = parser.parse_args()

    output = write_progress_index(Path(args.generated_dir), Path(args.output))
    print(output)


if __name__ == "__main__":
    main()
