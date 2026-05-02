import json
import re
from pathlib import Path

import pytest

from backend.services.reports.report_templates import report_input_from_dict
from backend.services.reports.report_writer import render_report_markdown, write_report_bundle, write_report_from_json
from backend.services.reports.summary_writer import SUMMARY_INSTRUCTION, build_summary_payload

ARTIFACT_ROOT = Path("docs/interview-artifacts")
GENERATED_ROOT = ARTIFACT_ROOT / "generated"


def _report_payload():
    return {
        "metadata": {
            "report_type": "classifier_eval",
            "title": "Email Classifier Eval",
            "generated_at": "2026-05-02T12:00:00Z",
            "git_sha": "abc123",
            "release_version": "test-release",
            "dataset_version": "email-classifier-v1",
            "model": "gpt-4o-mini",
            "prompt_version": "v3",
            "recommendation": "promote",
            "decision": "approved_for_demo",
        },
        "metrics": {
            "precision": 0.94,
            "recall": 0.98,
            "f1": 0.96,
        },
        "token_breakdown": {
            "prompt_tokens": 1200,
            "output_tokens": 200,
        },
        "cost_breakdown": {
            "total_cost_cents": 1,
            "cost_per_1000_calls_cents": 1000,
        },
        "latency_metrics": {
            "p50_ms": 450,
            "p95_ms": 900,
        },
        "supporting_artifacts": [
            {"label": "Confusion Matrix", "path": "confusion_matrix.csv"},
        ],
        "notes": ["Recall is weighted above precision because missed job emails are higher risk."],
    }


def test_report_metadata_validation_requires_reproducibility_fields():
    payload = _report_payload()
    del payload["metadata"]["git_sha"]

    with pytest.raises(ValueError, match="metadata.git_sha"):
        report_input_from_dict(payload)


def test_render_report_markdown_is_deterministic_and_table_based():
    report = report_input_from_dict(_report_payload())

    markdown = render_report_markdown(report)

    assert "# Email Classifier Eval" in markdown
    assert "| git_sha | abc123 |" in markdown
    assert "| recall | 0.98 |" in markdown
    assert "| prompt_tokens | 1200 |" in markdown
    assert "[Confusion Matrix](confusion_matrix.csv)" in markdown
    assert "Recommendation: promote" in markdown


def test_write_report_bundle_is_immutable_by_default(tmp_path: Path):
    report = report_input_from_dict(_report_payload())

    output_dir = write_report_bundle(report, tmp_path)

    assert (output_dir / "report.md").exists()
    assert (output_dir / "metadata.json").exists()
    assert (output_dir / "metrics.json").exists()
    assert (output_dir / "source_input.json").exists()

    with pytest.raises(FileExistsError):
        write_report_bundle(report, tmp_path)


def test_write_report_from_json_regenerates_from_structured_input(tmp_path: Path):
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(_report_payload()), encoding="utf-8")

    output_dir = write_report_from_json(input_path, tmp_path / "generated")

    metadata = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    metrics = json.loads((output_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metadata["dataset_version"] == "email-classifier-v1"
    assert metrics["f1"] == 0.96


def test_summary_payload_is_constrained_to_computed_inputs():
    report = report_input_from_dict(_report_payload())

    payload = build_summary_payload(report)

    assert payload["instruction"] == SUMMARY_INSTRUCTION
    assert payload["metrics"]["recall"] == 0.98
    assert "Confusion Matrix" not in json.dumps(payload)


def test_generated_artifacts_have_reproducible_metadata_and_claim_status():
    generated = sorted(path for path in GENERATED_ROOT.glob("2026-05-02-*.md"))
    assert generated, "Expected dated generated artifacts"

    for path in generated:
        text = path.read_text()
        assert text.startswith("---\n"), f"{path} missing frontmatter"
        assert "artifact_type:" in text
        assert "generated_at: 2026-05-02" in text
        assert "source:" in text
        assert "status:" in text
        assert "live enterprise traffic" not in text.lower().replace("no live enterprise traffic", "")


def test_core_interview_artifacts_label_evidence_and_avoid_overclaims():
    docs = [
        ARTIFACT_ROOT / "cost-scaling-memo.md",
        ARTIFACT_ROOT / "ai-governance-artifact.md",
        ARTIFACT_ROOT / "risk-control-artifact.md",
        ARTIFACT_ROOT / "model-risk-management.md",
        ARTIFACT_ROOT / "architecture-walkthrough.md",
    ]

    forbidden_patterns = [
        r"\bproven at million-user scale\b",
        r"\bbank-grade certified\b",
        r"\bguarantees no data leakage\b",
        r"\bfully automated model promotion\b",
    ]
    for path in docs:
        text = path.read_text()
        assert "Evidence status:" in text
        lowered = text.lower()
        for pattern in forbidden_patterns:
            assert re.search(pattern, lowered) is None, f"{path} overclaims with {pattern}"


def test_cost_scaling_memo_covers_model_prompt_token_and_scale_tradeoffs():
    text = (ARTIFACT_ROOT / "cost-scaling-memo.md").read_text().lower()

    for term in ["model", "prompt", "tokens", "cost", "latency", "1,000,000 requests", "projection"]:
        assert term in text
