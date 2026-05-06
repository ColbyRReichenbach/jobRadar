from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_feature_artifact_suite.py"


def load_suite_module():
    spec = importlib.util.spec_from_file_location("run_feature_artifact_suite", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_suite_commands_includes_expected_commands_and_overwrite():
    suite = load_suite_module()

    commands = suite.build_suite_commands(
        python="python",
        generated_dir=Path("generated"),
        index_output=Path("index.md"),
        overwrite=True,
        include_radar_lineage=True,
        radar_fixture=Path("fixture.json"),
        update_index=True,
    )

    names = [command.name for command in commands]
    assert names == [
        "gmail_classifier_artifact_eval",
        "source_retrieval_artifact_eval",
        "copilot_router_artifact_eval",
        "radar_evidence_artifact_eval",
        "copilot_grounded_answer_eval",
        "red_team_eval",
        "radar_lineage_report",
        "progress_index",
    ]
    assert "--overwrite" in commands[0].command
    assert commands[-1].command == [
        "python",
        "scripts/regenerate_ai_progress_index.py",
        "--generated-dir",
        "generated",
        "--output",
        "index.md",
    ]


def test_run_command_records_failure_without_raising():
    suite = load_suite_module()
    command = suite.ArtifactCommand(
        name="example",
        command=["python", "missing.py"],
        expected_outputs=["out.json"],
        description="Example",
    )

    def fake_executor(cmd):
        return subprocess.CompletedProcess(cmd, 7, stdout="ok", stderr="failed")

    result = suite.run_command(command, executor=fake_executor)

    assert result.name == "example"
    assert result.exit_code == 7
    assert result.stdout_tail == "ok"
    assert result.stderr_tail == "failed"
    assert result.expected_outputs == ["out.json"]


def test_dry_run_writes_suite_summary(tmp_path: Path):
    suite = load_suite_module()
    summary_path = tmp_path / "summary.json"

    exit_code = suite.main(
        [
            "--dry-run",
            "--no-radar-lineage",
            "--generated-dir",
            str(tmp_path / "generated"),
            "--index-output",
            str(tmp_path / "index.md"),
            "--summary-output",
            str(summary_path),
        ]
    )

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["dry_run"] is True
    assert payload["status"] == "passed"
    assert payload["command_count"] == 7
    assert payload["failed_count"] == 0
    assert {item["name"] for item in payload["commands"]} == {
        "gmail_classifier_artifact_eval",
        "source_retrieval_artifact_eval",
        "copilot_router_artifact_eval",
        "radar_evidence_artifact_eval",
        "copilot_grounded_answer_eval",
        "red_team_eval",
        "progress_index",
    }
    assert all(item["skipped"] for item in payload["commands"])
    assert {item["skip_reason"] for item in payload["commands"]} == {"dry_run"}


def test_write_suite_summary_marks_failures(tmp_path: Path):
    suite = load_suite_module()
    results = [
        suite.ArtifactCommandResult(
            name="passed",
            command=["true"],
            expected_outputs=[],
            exit_code=0,
            duration_ms=1,
            stdout_tail="",
            stderr_tail="",
        ),
        suite.ArtifactCommandResult(
            name="failed",
            command=["false"],
            expected_outputs=[],
            exit_code=1,
            duration_ms=1,
            stdout_tail="",
            stderr_tail="error",
        ),
    ]

    output = suite.write_suite_summary(output_path=tmp_path / "summary.json", results=results, dry_run=False)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["status"] == "failed"
    assert payload["failed_count"] == 1
    assert payload["commands"][1]["name"] == "failed"
    assert payload["commands"][1]["stderr_tail"] == "error"


def test_synthetic_profile_points_commands_at_synthetic_datasets(tmp_path: Path):
    suite = load_suite_module()
    summary_path = tmp_path / "summary.json"

    exit_code = suite.main(
        [
            "--dry-run",
            "--dataset-profile",
            "synthetic",
            "--no-radar-lineage",
            "--no-index",
            "--summary-output",
            str(summary_path),
        ]
    )

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    commands = {item["name"]: item["command"] for item in payload["commands"]}
    assert exit_code == 0
    assert "evals/email_classifier/email_classifier_synthetic_v1.jsonl" in commands["gmail_classifier_artifact_eval"]
    assert "evals/copilot/copilot_router_synthetic_v1.jsonl" in commands["copilot_router_artifact_eval"]
    assert "evals/copilot/copilot_questions_synthetic_v1.jsonl" in commands["copilot_grounded_answer_eval"]
    assert "evals/radar/radar_evidence_quality_synthetic_v1.jsonl" in commands["radar_evidence_artifact_eval"]
    assert "evals/search/search_documents_synthetic_v1.json" in commands["source_retrieval_artifact_eval"]
    assert "evals/red_team/synthetic_safety_v1.jsonl" in commands["red_team_eval"]
