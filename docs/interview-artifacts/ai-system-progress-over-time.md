# AI System Progress Over Time

This index is generated from immutable report folders under `docs/interview-artifacts/generated`.

| Date | Report | Type | Dataset | Model | Prompt | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-05-02 | [Radar Lineage Report - Banking AI Assistant Hiring Radar](generated/2026-05-02_radar-lineage_radar-lineage-v1-22222222_gpt-5-4_deterministic-lineage-v1/report.md) | radar_lineage | radar-lineage-v1-22222222 | gpt-5.4 | deterministic-lineage-v1 | pending_admin_review |
| 2026-05-02 | [Email Classifier Eval](generated/2026-05-02_email-classifier-eval_email-classifier-v1_gpt-4o-mini_v3/report.md) | email_classifier_eval | email_classifier_v1 | gpt-4o-mini | v3 | approved_for_demo_artifact |
| 2026-05-06 | [Gmail Classifier Artifact Eval](generated/2026-05-06_gmail-classifier-artifact-eval_email-classifier-synthetic-v1_fallback-rules_rules-v1/report.md) | gmail-classifier-artifact-eval | email_classifier_synthetic_v1 | fallback-rules | rules-v1 | baseline_artifact_ready |
| 2026-05-06 | [Search and Source Retrieval Artifact Eval](generated/2026-05-06_source-retrieval-eval_search-synthetic-v1_postgres-lexical_semantic-expansion-v1/report.md) | source-retrieval-eval | search_synthetic_v1 | postgres-lexical | semantic_expansion_v1 | baseline_artifact_ready |
| 2026-05-06 | [Copilot Router Artifact Eval](generated/2026-05-06_copilot-router-eval_copilot-router-synthetic-v1_deterministic-router_route-rules-v1/report.md) | copilot-router-eval | copilot_router_synthetic_v1 | deterministic-router | route-rules-v1 | baseline_artifact_ready |
| 2026-05-06 | [Radar Evidence Quality Artifact Eval](generated/2026-05-06_radar-evidence-quality-eval_radar-evidence-quality-synthetic-v1_deterministic-evidence-quality_source-quality-gate-v1/report.md) | radar-evidence-quality-eval | radar_evidence_quality_synthetic_v1 | deterministic-evidence-quality | source-quality-gate-v1 | baseline_artifact_ready |
| 2026-05-06 | [Radar Lineage Report - Banking AI Assistant Hiring Radar](generated/2026-05-06_radar-lineage_radar-lineage-v1-22222222_gpt-5-4_deterministic-lineage-v1/report.md) | radar_lineage | radar-lineage-v1-22222222 | gpt-5.4 | deterministic-lineage-v1 | pending_admin_review |

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
