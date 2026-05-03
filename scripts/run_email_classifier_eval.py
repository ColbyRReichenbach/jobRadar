#!/usr/bin/env python3
"""Run the email classifier eval and generate reproducible artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from backend.services.evals.classifier_eval import build_report_payload, run_classifier_eval_sync
from backend.services.reports.report_templates import report_input_from_dict
from backend.services.reports.report_writer import render_report_markdown, write_report_bundle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="evals/email_classifier/email_classifier_v1.jsonl")
    parser.add_argument("--metrics-output", default="evals/email_classifier/email_classifier_v1.metrics.json")
    parser.add_argument("--report-output", default="docs/interview-artifacts/email-classifier-eval.md")
    parser.add_argument("--generated-dir", default="docs/interview-artifacts/generated")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    eval_result = run_classifier_eval_sync(args.dataset)
    metrics_output = Path(args.metrics_output)
    metrics_output.parent.mkdir(parents=True, exist_ok=True)
    metrics_output.write_text(json.dumps(eval_result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report_payload = build_report_payload(eval_result)
    report = report_input_from_dict(report_payload)
    report_output = Path(args.report_output)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.write_text(render_report_markdown(report), encoding="utf-8")
    generated_output = write_report_bundle(report, args.generated_dir, overwrite=args.overwrite)

    print(json.dumps({"metrics": str(metrics_output), "report": str(report_output), "generated": str(generated_output)}, indent=2))


if __name__ == "__main__":
    main()
