# AI System Progress Over Time

Date: 2026-05-02
Purpose: clickable index of product, governance, scale, and generated evaluation artifacts for interview walkthroughs.

## Core Artifacts

| Artifact | What It Shows |
| --- | --- |
| [Cost Scaling Memo](cost-scaling-memo.md) | Model, prompt, token, and scale tradeoffs |
| [AI Governance Artifact](ai-governance-artifact.md) | Reproducibility, auditability, model cards, approval, rollback, retention |
| [Risk Control Artifact](risk-control-artifact.md) | User isolation, admin access, trace redaction, prompt injection, data leakage |
| [Model Risk Management](model-risk-management.md) | Model lifecycle, reprocessing, promotion, rollback |
| [Architecture Walkthrough](architecture-walkthrough.md) | End-to-end AI platform architecture |
| [Demo Script](demo-script.md) | Interview-ready product and governance story |
| [Known AI Limitations And Deferred Controls](known-ai-limitations-and-deferred-controls.md) | Honest boundary between implemented controls, projections, and deferred work |

## Generated Snapshots

| Snapshot | Source |
| --- | --- |
| [2026-05-02 Cost Scaling Projection](generated/2026-05-02-cost-scaling-projection.md) | Deterministic projection, not live usage |
| [2026-05-02 Governance Snapshot](generated/2026-05-02-governance-snapshot.md) | Implemented schema, services, routes, and tests |
| [2026-05-02 Risk Controls Snapshot](generated/2026-05-02-risk-controls-snapshot.md) | Implemented controls and known limitations |

## Generated Evaluation Reports

| Date | Report | Type | Dataset | Model | Prompt | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-05-02 | [Email Classifier Eval](generated/2026-05-02_email-classifier-eval_email-classifier-v1_gpt-4o-mini_v3/report.md) | email_classifier_eval | email_classifier_v1 | gpt-4o-mini | v3 | approved_for_demo_artifact |
| 2026-05-02 | [Radar Lineage Report - Banking AI Assistant Hiring Radar](generated/2026-05-02_radar-lineage_radar-lineage-v1-22222222_gpt-5-4_deterministic-lineage-v1/report.md) | radar_lineage | radar-lineage-v1-22222222 | gpt-5.4 | deterministic-lineage-v1 | pending_admin_review |

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

Regenerate this index from immutable generated report folders:

```bash
scripts/regenerate_ai_progress_index.py \
  --generated-dir docs/interview-artifacts/generated \
  --output docs/interview-artifacts/ai-system-progress-over-time.md
```

Deterministic metric tables are the source of truth. Optional AI summaries must be generated only from `metadata.json`, `metrics.json`, `token_breakdown.json`, `cost_breakdown.json`, `latency_metrics.json`, and explicit notes.

## Reading Order

1. Start with [Demo Script](demo-script.md).
2. Use [Architecture Walkthrough](architecture-walkthrough.md) to show how the product is built.
3. Use [AI Governance Artifact](ai-governance-artifact.md) to show reproducibility and auditability.
4. Use [Cost Scaling Memo](cost-scaling-memo.md) to show model and prompt tradeoff thinking.
5. Use [Risk Control Artifact](risk-control-artifact.md) and [Model Risk Management](model-risk-management.md) to show production risk thinking.

## Claim Discipline

Static docs and generated snapshots must not claim live enterprise traffic, bank-grade approval, or production-scale reliability. Projections must be labeled as projections.
