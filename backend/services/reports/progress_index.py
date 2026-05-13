"""Generate a progress-over-time index for immutable AI reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPRODUCIBLE_REPORT_FORMAT_SECTION = """\
## Reproducible Report Format

Generated report folders use this naming convention:

```text
YYYY-MM-DD_<report-type>_<dataset-version>_<model>_<prompt-version>/
```

Each folder contains:

- `report.md`
- `metadata.json`
- `metrics.json`
- `token_breakdown.json`
- `cost_breakdown.json`
- `latency_metrics.json`
- `summary_payload.json`
- `source_input.json`

Regenerate a report from structured JSON:

```bash
scripts/generate_ai_report.py \\
  --input path/to/report-input.json \\
  --output-dir docs/ai-artifacts/generated
```

Regenerate this index:

```bash
scripts/regenerate_ai_progress_index.py \\
  --generated-dir docs/ai-artifacts/generated \\
  --output docs/ai-artifacts/ai-system-progress-over-time.md
```

Deterministic metric tables are the source of truth. Optional AI summaries must be generated only from `metadata.json`, `metrics.json`, `token_breakdown.json`, `cost_breakdown.json`, `latency_metrics.json`, and explicit notes.
"""


@dataclass(frozen=True)
class GeneratedReport:
    folder: Path
    metadata: dict[str, Any]


def discover_generated_reports(generated_dir: Path | str) -> list[GeneratedReport]:
    root = Path(generated_dir)
    reports: list[GeneratedReport] = []
    if not root.exists():
        return reports

    for metadata_path in sorted(root.glob("*/metadata.json")):
        report_path = metadata_path.parent / "report.md"
        if not report_path.exists():
            continue
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        reports.append(GeneratedReport(folder=metadata_path.parent, metadata=metadata))
    return sorted(reports, key=lambda item: (item.metadata.get("generated_at", ""), item.folder.name))


def _relative_link(from_path: Path, to_path: Path) -> str:
    return to_path.relative_to(from_path.parent).as_posix()


def render_progress_index(generated_dir: Path | str, output_path: Path | str) -> str:
    output = Path(output_path)
    reports = discover_generated_reports(generated_dir)
    lines = [
        "# AI System Progress Over Time",
        "",
        "This index is generated from immutable report folders under `docs/ai-artifacts/generated`.",
        "",
        "| Date | Report | Type | Dataset | Model | Prompt | Decision |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]

    if not reports:
        lines.append("| No reports yet | | | | | | |")
    else:
        for report in reports:
            metadata = report.metadata
            report_link = _relative_link(output, report.folder / "report.md")
            lines.append(
                "| {date} | [{title}]({link}) | {report_type} | {dataset} | {model} | {prompt} | {decision} |".format(
                    date=str(metadata.get("generated_at", ""))[:10],
                    title=str(metadata.get("title", report.folder.name)).replace("|", "\\|"),
                    link=report_link,
                    report_type=str(metadata.get("report_type", "")).replace("|", "\\|"),
                    dataset=str(metadata.get("dataset_version", "")).replace("|", "\\|"),
                    model=str(metadata.get("model", "")).replace("|", "\\|"),
                    prompt=str(metadata.get("prompt_version", "")).replace("|", "\\|"),
                    decision=str(metadata.get("decision", "")).replace("|", "\\|"),
                )
            )

    lines.extend(["", REPRODUCIBLE_REPORT_FORMAT_SECTION.rstrip()])
    return "\n".join(lines).rstrip() + "\n"


def write_progress_index(generated_dir: Path | str, output_path: Path | str) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_progress_index(generated_dir, output), encoding="utf-8")
    return output
