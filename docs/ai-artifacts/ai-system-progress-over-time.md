# AI System Progress Over Time

This index summarizes committed AI evaluation and governance artifacts. Generated report bundles are written under `docs/ai-artifacts/generated` for local/release review and are intentionally ignored by git unless a release explicitly needs to publish one.

## Reading Order

Static architecture and governance artifacts:

- [Cost Scaling Memo](cost-scaling-memo.md)
- [AI Governance Artifact](ai-governance-artifact.md)
- [Risk Control Artifact](risk-control-artifact.md)
- [Model Risk Management](model-risk-management.md)
- [Architecture Walkthrough](architecture-walkthrough.md)
- [Demo Script](demo-script.md)
- [Known AI Limitations and Deferred Controls](known-ai-limitations-and-deferred-controls.md)

Projection artifacts are planning tools and must not claim live enterprise traffic.

Current component eval runs are generated locally and are intentionally not committed.
Use the static changelogs and runbook to understand the workflow:

- [Gmail Classifier Changelog](feature-changelogs/gmail-classifier-changelog.md)
- [Copilot Routing Changelog](feature-changelogs/copilot-routing-changelog.md)
- [Radar Research Changelog](feature-changelogs/radar-research-changelog.md)
- [Search Source Intelligence Changelog](feature-changelogs/search-source-intelligence-changelog.md)
- [Artifact Evaluation Runbook](feature-changelogs/artifact-evaluation-runbook.md)

| Date | Report | Type | Dataset | Model | Prompt | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| No committed generated reports | Run the commands below to regenerate local report bundles. | local artifact | varies | varies | varies | not committed |

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
scripts/generate_ai_report.py \
  --input path/to/report-input.json \
  --output-dir docs/ai-artifacts/generated
```

Regenerate this index:

```bash
scripts/regenerate_ai_progress_index.py \
  --generated-dir docs/ai-artifacts/generated \
  --output docs/ai-artifacts/ai-system-progress-over-time.md
```

Deterministic metric tables are the source of truth. Optional AI summaries must be generated only from `metadata.json`, `metrics.json`, `token_breakdown.json`, `cost_breakdown.json`, `latency_metrics.json`, and explicit notes.
