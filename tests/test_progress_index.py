import json
import re
from pathlib import Path

from backend.services.reports.progress_index import discover_generated_reports, render_progress_index, write_progress_index

ARTIFACT_ROOT = Path("docs/interview-artifacts")
INDEX = ARTIFACT_ROOT / "ai-system-progress-over-time.md"


def _markdown_links(text: str) -> list[str]:
    return re.findall(r"\[[^\]]+\]\(([^)]+)\)", text)


def _write_generated_report(root: Path, folder_name: str, title: str, generated_at: str) -> Path:
    folder = root / folder_name
    folder.mkdir(parents=True)
    (folder / "report.md").write_text(f"# {title}\n", encoding="utf-8")
    (folder / "metadata.json").write_text(
        json.dumps(
            {
                "title": title,
                "report_type": "classifier_eval",
                "generated_at": generated_at,
                "dataset_version": "email-classifier-v1",
                "model": "gpt-4o-mini",
                "prompt_version": "v3",
                "decision": "approved_for_demo",
            }
        ),
        encoding="utf-8",
    )
    return folder


def test_discover_generated_reports_reads_metadata_and_report_links(tmp_path: Path):
    generated = tmp_path / "generated"
    _write_generated_report(generated, "2026-05-02_classifier", "Classifier Eval", "2026-05-02T12:00:00Z")

    reports = discover_generated_reports(generated)

    assert len(reports) == 1
    assert reports[0].metadata["title"] == "Classifier Eval"


def test_render_progress_index_links_to_each_report(tmp_path: Path):
    generated = tmp_path / "generated"
    output = tmp_path / "ai-system-progress-over-time.md"
    _write_generated_report(generated, "2026-05-02_classifier", "Classifier Eval", "2026-05-02T12:00:00Z")

    markdown = render_progress_index(generated, output)

    assert "# AI System Progress Over Time" in markdown
    assert "[Classifier Eval](generated/2026-05-02_classifier/report.md)" in markdown
    assert "| 2026-05-02 |" in markdown


def test_write_progress_index_handles_no_reports(tmp_path: Path):
    output = write_progress_index(tmp_path / "missing", tmp_path / "index.md")

    markdown = output.read_text(encoding="utf-8")
    assert "| No reports yet |" in markdown


def test_progress_index_links_to_every_static_artifact():
    text = INDEX.read_text()
    linked_paths = set(_markdown_links(text))

    expected = {
        "cost-scaling-memo.md",
        "ai-governance-artifact.md",
        "risk-control-artifact.md",
        "model-risk-management.md",
        "architecture-walkthrough.md",
        "demo-script.md",
        "known-ai-limitations-and-deferred-controls.md",
        "generated/2026-05-02-cost-scaling-projection.md",
        "generated/2026-05-02-governance-snapshot.md",
        "generated/2026-05-02-risk-controls-snapshot.md",
    }
    assert expected.issubset(linked_paths)

    for target in linked_paths:
        assert (ARTIFACT_ROOT / target).exists(), f"Broken progress-index link: {target}"


def test_progress_index_labels_projection_and_claim_discipline():
    text = INDEX.read_text()

    assert "Projection" in text
    assert "must not claim live enterprise traffic" in text
    assert "Reading Order" in text
