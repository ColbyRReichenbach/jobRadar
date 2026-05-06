# AI System Progress Over Time

This index is generated from immutable report folders under `docs/interview-artifacts/generated`.

## Reading Order

Static architecture and governance artifacts:

- [Cost Scaling Memo](cost-scaling-memo.md)
- [AI Governance Artifact](ai-governance-artifact.md)
- [Risk Control Artifact](risk-control-artifact.md)
- [Model Risk Management](model-risk-management.md)
- [Architecture Walkthrough](architecture-walkthrough.md)
- [Demo Script](demo-script.md)
- [Known AI Limitations and Deferred Controls](known-ai-limitations-and-deferred-controls.md)

Projection snapshots:

- [Cost Scaling Projection](generated/2026-05-02-cost-scaling-projection.md)
- [Governance Snapshot](generated/2026-05-02-governance-snapshot.md)
- [Risk Controls Snapshot](generated/2026-05-02-risk-controls-snapshot.md)

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
| 2026-05-02 | [Radar Lineage Report - Banking AI Assistant Hiring Radar](generated/2026-05-02_radar-lineage_radar-lineage-v1-22222222_gpt-5-4_deterministic-lineage-v1/report.md) | radar_lineage | radar-lineage-v1-22222222 | gpt-5.4 | deterministic-lineage-v1 | pending_admin_review |
| 2026-05-02 | [Email Classifier Eval](generated/2026-05-02_email-classifier-eval_email-classifier-v1_gpt-4o-mini_v3/report.md) | email_classifier_eval | email_classifier_v1 | gpt-4o-mini | v3 | approved_for_demo_artifact |

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
  --output-dir docs/interview-artifacts/generated
```

Regenerate this index:

```bash
scripts/regenerate_ai_progress_index.py \
  --generated-dir docs/interview-artifacts/generated \
  --output docs/interview-artifacts/ai-system-progress-over-time.md
```

Deterministic metric tables are the source of truth. Optional AI summaries must be generated only from `metadata.json`, `metrics.json`, `token_breakdown.json`, `cost_breakdown.json`, `latency_metrics.json`, and explicit notes.
