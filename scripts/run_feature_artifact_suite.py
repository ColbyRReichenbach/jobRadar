#!/usr/bin/env python3
"""Run the local AI feature artifact suite and refresh the artifact index.

This wrapper intentionally orchestrates existing deterministic/offline scripts
instead of inventing new metrics. It records what ran, where outputs should
land, and whether any artifact command failed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]


DEFAULT_GENERATED_DIR = Path("docs/ai-artifacts/generated")
DEFAULT_INDEX_OUTPUT = Path("docs/ai-artifacts/ai-system-progress-over-time.md")
DEFAULT_SUMMARY_OUTPUT = DEFAULT_GENERATED_DIR / "feature-artifact-suite-summary.json"
DEFAULT_RADAR_FIXTURE = Path("docs/ai-artifacts/fixtures/radar-lineage-payload.json")
SEED_DATASETS = {
    "gmail_dataset": Path("evals/email_classifier/email_classifier_v1.jsonl"),
    "copilot_router_dataset": Path("evals/copilot/copilot_router_v1.jsonl"),
    "copilot_questions_dataset": Path("evals/copilot/copilot_questions_v1.jsonl"),
    "radar_evidence_dataset": Path("evals/radar/radar_evidence_quality_v1.jsonl"),
    "search_documents": Path("evals/search/search_documents_v1.json"),
    "search_queries": Path("evals/search/search_queries_v1.jsonl"),
    "search_baselines": Path("evals/search/search_baselines_v1.json"),
}
SYNTHETIC_DATASETS = {
    "gmail_dataset": Path("evals/email_classifier/email_classifier_synthetic_v1.jsonl"),
    "copilot_router_dataset": Path("evals/copilot/copilot_router_synthetic_v1.jsonl"),
    "copilot_questions_dataset": Path("evals/copilot/copilot_questions_synthetic_v1.jsonl"),
    "radar_evidence_dataset": Path("evals/radar/radar_evidence_quality_synthetic_v1.jsonl"),
    "search_documents": Path("evals/search/search_documents_synthetic_v1.json"),
    "search_queries": Path("evals/search/search_queries_synthetic_v1.jsonl"),
    "search_baselines": Path("evals/search/search_baselines_synthetic_v1.json"),
    "red_team_dataset": Path("evals/red_team/synthetic_safety_v1.jsonl"),
}


@dataclass(frozen=True)
class ArtifactCommand:
    name: str
    command: list[str]
    expected_outputs: list[str]
    description: str


@dataclass
class ArtifactCommandResult:
    name: str
    command: list[str]
    expected_outputs: list[str]
    exit_code: int
    duration_ms: int
    stdout_tail: str
    stderr_tail: str
    skipped: bool = False
    skip_reason: str | None = None


Executor = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def _rel(path: Path | str) -> str:
    return str(path)


def _tail(value: str, *, max_chars: int = 4000) -> str:
    if len(value) <= max_chars:
        return value
    return value[-max_chars:]


def build_suite_commands(
    *,
    python: str,
    generated_dir: Path,
    index_output: Path,
    overwrite: bool,
    include_radar_lineage: bool,
    radar_fixture: Path,
    update_index: bool,
    gmail_dataset: Path = SEED_DATASETS["gmail_dataset"],
    copilot_router_dataset: Path = SEED_DATASETS["copilot_router_dataset"],
    copilot_questions_dataset: Path = SEED_DATASETS["copilot_questions_dataset"],
    radar_evidence_dataset: Path = SEED_DATASETS["radar_evidence_dataset"],
    search_documents: Path = SEED_DATASETS["search_documents"],
    search_queries: Path = SEED_DATASETS["search_queries"],
    search_baselines: Path = SEED_DATASETS["search_baselines"],
    red_team_dataset: Path | None = None,
) -> list[ArtifactCommand]:
    generated = _rel(generated_dir)
    commands = [
        ArtifactCommand(
            name="gmail_classifier_artifact_eval",
            command=[
                python,
                "scripts/run_gmail_classifier_artifact_eval.py",
                "--dataset",
                _rel(gmail_dataset),
                "--output-dir",
                generated,
                *(("--overwrite",) if overwrite else ()),
            ],
            expected_outputs=[generated],
            description="Run Gmail classifier artifact eval and write generated report bundle.",
        ),
        ArtifactCommand(
            name="source_retrieval_artifact_eval",
            command=[
                python,
                "scripts/run_source_retrieval_eval.py",
                "--documents",
                _rel(search_documents),
                "--queries",
                _rel(search_queries),
                "--baselines",
                _rel(search_baselines),
                "--output-dir",
                generated,
                *(("--overwrite",) if overwrite else ()),
            ],
            expected_outputs=[generated],
            description="Run search/source retrieval artifact eval and write generated report bundle.",
        ),
        ArtifactCommand(
            name="copilot_router_artifact_eval",
            command=[
                python,
                "scripts/run_copilot_router_eval.py",
                "--dataset",
                _rel(copilot_router_dataset),
                "--output-dir",
                generated,
                *(("--overwrite",) if overwrite else ()),
            ],
            expected_outputs=[generated],
            description="Run Copilot router artifact eval and write generated report bundle.",
        ),
        ArtifactCommand(
            name="radar_evidence_artifact_eval",
            command=[
                python,
                "scripts/run_radar_evidence_eval.py",
                "--dataset",
                _rel(radar_evidence_dataset),
                "--output-dir",
                generated,
                *(("--overwrite",) if overwrite else ()),
            ],
            expected_outputs=[generated],
            description="Run Radar evidence-quality artifact eval and write generated report bundle.",
        ),
        ArtifactCommand(
            name="copilot_grounded_answer_eval",
            command=[
                python,
                "scripts/run_copilot_eval.py",
                "--dataset",
                _rel(copilot_questions_dataset),
                "--report",
                _rel(generated_dir / "copilot-grounded-eval.md"),
                "--metrics",
                _rel(generated_dir / "copilot-grounded-eval-metrics.json"),
            ],
            expected_outputs=[
                _rel(generated_dir / "copilot-grounded-eval.md"),
                _rel(generated_dir / "copilot-grounded-eval-metrics.json"),
            ],
            description="Run offline Copilot grounded-answer eval.",
        ),
        ArtifactCommand(
            name="red_team_eval",
            command=[
                python,
                "scripts/run_red_team_eval.py",
                *(("--dataset", _rel(red_team_dataset)) if red_team_dataset else ()),
                "--report",
                _rel(generated_dir / "red-team-eval.md"),
                "--metrics",
                _rel(generated_dir / "red-team-eval-v1-metrics.json"),
            ],
            expected_outputs=[
                _rel(generated_dir / "red-team-eval.md"),
                _rel(generated_dir / "red-team-eval-v1-metrics.json"),
            ],
            description="Run offline red-team guardrail eval.",
        ),
    ]

    if include_radar_lineage:
        radar_command = [
            python,
            "scripts/run_radar_lineage_report.py",
            "--input-json",
            _rel(radar_fixture),
            "--output-dir",
            generated,
        ]
        if overwrite:
            radar_command.append("--overwrite")
        commands.append(
            ArtifactCommand(
                name="radar_lineage_report",
                command=radar_command,
                expected_outputs=[generated],
                description="Render Radar lineage report from saved fixture payload.",
            )
        )

    if update_index:
        commands.append(
            ArtifactCommand(
                name="progress_index",
                command=[
                    python,
                    "scripts/regenerate_ai_progress_index.py",
                    "--generated-dir",
                    generated,
                    "--output",
                    _rel(index_output),
                ],
                expected_outputs=[_rel(index_output)],
                description="Refresh generated artifact index.",
            )
        )

    return commands


def run_command(command: ArtifactCommand, *, executor: Executor | None = None) -> ArtifactCommandResult:
    runner = executor or (
        lambda cmd: subprocess.run(
            list(cmd),
            cwd=ROOT_DIR,
            check=False,
            capture_output=True,
            text=True,
        )
    )
    started = time.perf_counter()
    completed = runner(command.command)
    duration_ms = int((time.perf_counter() - started) * 1000)
    return ArtifactCommandResult(
        name=command.name,
        command=command.command,
        expected_outputs=command.expected_outputs,
        exit_code=completed.returncode,
        duration_ms=duration_ms,
        stdout_tail=_tail(completed.stdout or ""),
        stderr_tail=_tail(completed.stderr or ""),
    )


def write_suite_summary(
    *,
    output_path: Path,
    results: Iterable[ArtifactCommandResult],
    dry_run: bool,
) -> Path:
    result_list = list(results)
    payload = {
        "schema_version": "feature_artifact_suite_v1",
        "dry_run": dry_run,
        "status": "passed" if all(item.exit_code == 0 or item.skipped for item in result_list) else "failed",
        "command_count": len(result_list),
        "failed_count": sum(1 for item in result_list if item.exit_code != 0 and not item.skipped),
        "commands": [asdict(item) for item in result_list],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def _filter_commands(commands: list[ArtifactCommand], only: set[str], skip: set[str]) -> list[ArtifactCommand]:
    filtered = []
    for command in commands:
        if only and command.name not in only:
            continue
        if command.name in skip:
            continue
        filtered.append(command)
    return filtered


def _skipped_result(command: ArtifactCommand, reason: str) -> ArtifactCommandResult:
    return ArtifactCommandResult(
        name=command.name,
        command=command.command,
        expected_outputs=command.expected_outputs,
        exit_code=0,
        duration_ms=0,
        stdout_tail="",
        stderr_tail="",
        skipped=True,
        skip_reason=reason,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated-dir", type=Path, default=DEFAULT_GENERATED_DIR)
    parser.add_argument("--index-output", type=Path, default=DEFAULT_INDEX_OUTPUT)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY_OUTPUT)
    parser.add_argument("--radar-fixture", type=Path, default=DEFAULT_RADAR_FIXTURE)
    parser.add_argument("--dataset-profile", choices=["seed", "synthetic"], default="seed")
    parser.add_argument("--gmail-dataset", type=Path)
    parser.add_argument("--copilot-router-dataset", type=Path)
    parser.add_argument("--copilot-questions-dataset", type=Path)
    parser.add_argument("--radar-evidence-dataset", type=Path)
    parser.add_argument("--search-documents", type=Path)
    parser.add_argument("--search-queries", type=Path)
    parser.add_argument("--search-baselines", type=Path)
    parser.add_argument("--red-team-dataset", type=Path)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Write the suite summary without executing commands.")
    parser.add_argument("--continue-on-error", action="store_true", help="Run remaining commands after a failure.")
    parser.add_argument("--no-index", action="store_true", help="Do not refresh the generated artifact index.")
    parser.add_argument("--no-radar-lineage", action="store_true", help="Skip Radar lineage report generation.")
    parser.add_argument("--only", action="append", default=[], help="Run only a named command. May be repeated.")
    parser.add_argument("--skip", action="append", default=[], help="Skip a named command. May be repeated.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    dataset_defaults = SYNTHETIC_DATASETS if args.dataset_profile == "synthetic" else SEED_DATASETS
    include_radar_lineage = not args.no_radar_lineage and args.radar_fixture.exists()
    commands = build_suite_commands(
        python=args.python,
        generated_dir=args.generated_dir,
        index_output=args.index_output,
        overwrite=args.overwrite,
        include_radar_lineage=include_radar_lineage,
        radar_fixture=args.radar_fixture,
        update_index=not args.no_index,
        gmail_dataset=args.gmail_dataset or dataset_defaults["gmail_dataset"],
        copilot_router_dataset=args.copilot_router_dataset or dataset_defaults["copilot_router_dataset"],
        copilot_questions_dataset=args.copilot_questions_dataset or dataset_defaults["copilot_questions_dataset"],
        radar_evidence_dataset=args.radar_evidence_dataset or dataset_defaults["radar_evidence_dataset"],
        search_documents=args.search_documents or dataset_defaults["search_documents"],
        search_queries=args.search_queries or dataset_defaults["search_queries"],
        search_baselines=args.search_baselines or dataset_defaults["search_baselines"],
        red_team_dataset=args.red_team_dataset or dataset_defaults.get("red_team_dataset"),
    )
    commands = _filter_commands(commands, only=set(args.only), skip=set(args.skip))

    results: list[ArtifactCommandResult] = []
    if not include_radar_lineage and not args.no_radar_lineage:
        skipped = ArtifactCommand(
            name="radar_lineage_report",
            command=[
                args.python,
                "scripts/run_radar_lineage_report.py",
                "--input-json",
                _rel(args.radar_fixture),
                "--output-dir",
                _rel(args.generated_dir),
            ],
            expected_outputs=[_rel(args.generated_dir)],
            description="Render Radar lineage report from saved fixture payload.",
        )
        if not args.only or "radar_lineage_report" in set(args.only):
            results.append(_skipped_result(skipped, f"fixture not found: {args.radar_fixture}"))

    for command in commands:
        if args.dry_run:
            results.append(_skipped_result(command, "dry_run"))
            continue
        result = run_command(command)
        results.append(result)
        if result.exit_code != 0 and not args.continue_on_error:
            break

    summary = write_suite_summary(output_path=args.summary_output, results=results, dry_run=args.dry_run)
    print(json.dumps({"summary": str(summary), "status": "passed" if all(r.exit_code == 0 or r.skipped for r in results) else "failed"}, indent=2))
    return 0 if all(result.exit_code == 0 or result.skipped for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
