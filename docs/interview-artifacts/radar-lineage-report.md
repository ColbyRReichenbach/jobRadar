# Radar Lineage Report

This artifact demonstrates how Opportunity Radar outputs can be audited after generation.

The report answers:

- Which user-scoped Radar run produced this report?
- Which sources and evidence items supported the findings?
- Which model call or run-step prompt versions contributed to the output?
- What did the report cost in tokens and estimated cents?
- What quality controls passed or need review?

Key metrics:

- `source_freshness_rate`: share of source rows fetched or published inside the freshness window.
- `duplicate_source_url_rate`: duplicate URL pressure after normalized URL comparison.
- `source_coverage_rate`: share of evidence items with a source row or URL.
- `unsupported_claim_rate`: explicit verification failures over total checked claims.
- `effective_cost_per_report_cents`: linked model-call cost when available, otherwise the Radar run aggregate estimate.

Reproduce the sample:

```bash
scripts/run_radar_lineage_report.py \
  --input-json docs/interview-artifacts/fixtures/radar-lineage-payload.json \
  --generated-at 2026-05-02T12:00:00Z \
  --git-sha working-tree \
  --release-version radar-lineage-demo \
  --output-dir docs/interview-artifacts/generated \
  --overwrite
```

Generated reports are immutable interview and QA artifacts. Runtime code should collect lineage from database rows and keep raw source text, raw prompts, and raw model responses out of public demo reports.
