#!/usr/bin/env python3
"""Package a feature eval payload into an immutable generated artifact bundle."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.services.evals.artifact_packager import load_payload, write_feature_artifact_bundle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Structured feature artifact payload JSON")
    parser.add_argument("--output-dir", default="docs/ai-artifacts/generated")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    output = write_feature_artifact_bundle(load_payload(args.input), Path(args.output_dir), overwrite=args.overwrite)
    print(output)


if __name__ == "__main__":
    main()
