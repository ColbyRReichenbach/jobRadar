#!/usr/bin/env python3
"""Generate an immutable AI report bundle from structured JSON input."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.services.reports.report_writer import write_report_from_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Path to structured report JSON input")
    parser.add_argument("--output-dir", default="docs/interview-artifacts/generated", help="Generated report output directory")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing generated report folder")
    args = parser.parse_args()

    output = write_report_from_json(Path(args.input), Path(args.output_dir), overwrite=args.overwrite)
    print(output)


if __name__ == "__main__":
    main()
