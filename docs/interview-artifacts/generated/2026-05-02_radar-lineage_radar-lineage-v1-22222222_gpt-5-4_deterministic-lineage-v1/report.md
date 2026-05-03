# Radar Lineage Report - Banking AI Assistant Hiring Radar

## Metadata

| Metric | Value |
| --- | --- |
| dataset_version | radar-lineage-v1-22222222 |
| decision | pending_admin_review |
| generated_at | 2026-05-02T12:00:00Z |
| git_sha | working-tree |
| model | gpt-5.4 |
| prompt_version | deterministic-lineage-v1 |
| recommendation | review |
| release_version | radar-lineage-demo |
| report_type | radar_lineage |
| title | Radar Lineage Report - Banking AI Assistant Hiring Radar |

## Summary

No AI summary was generated. Deterministic metric tables below are the source of truth.

## Primary Metrics

| Metric | Value |
| --- | --- |
| claim_count | 2 |
| contributing_model_names | `['gpt-5.4']` |
| contributing_prompt_versions | `['radar-writer-v1', 'radar-normalizer-v1', 'radar-planner-v1', 'radar-extractor-v1', 'radar-verifier-v1']` |
| covered_evidence_count | 2 |
| duplicate_source_url_count | 0 |
| duplicate_source_url_rate | 0 |
| effective_cost_per_report_cents | 18 |
| evidence_count | 2 |
| failed_run_step_count | 0 |
| fresh_source_count | 2 |
| linked_model_call_cost_cents | 18 |
| linked_model_call_count | 1 |
| linked_output_token_count | 700 |
| linked_prompt_token_count | 3800 |
| mean_step_duration_seconds | 31.6 |
| p95_step_duration_seconds | 52 |
| projected_cost_per_1000_reports_cents | 18000 |
| report_id | 33333333-3333-4333-8333-333333333333 |
| run_cost_estimate_cents | 42 |
| run_id | 22222222-2222-4222-8222-222222222222 |
| run_llm_call_count | 5 |
| run_token_input_count | 12000 |
| run_token_output_count | 2600 |
| source_count | 2 |
| source_coverage_rate | 1 |
| source_freshness_rate | 1 |
| source_freshness_window_days | 30 |
| stale_source_count | 0 |
| successful_run_step_count | 5 |
| total_run_duration_seconds | 240 |
| unique_source_url_count | 2 |
| unsupported_claim_count | 0 |
| unsupported_claim_rate | 0 |

## Token Breakdown

| Metric | Value |
| --- | --- |
| linked_output_tokens | 700 |
| linked_prompt_tokens | 3800 |
| linked_total_tokens | 4500 |
| run_tokens_in | 12000 |
| run_tokens_out | 2600 |

## Cost Breakdown

| Metric | Value |
| --- | --- |
| effective_cost_per_report_cents | 18 |
| linked_model_call_cost_cents | 18 |
| projected_cost_per_1000_reports_cents | 18000 |
| run_cost_estimate_cents | 42 |

## Latency Metrics

| Metric | Value |
| --- | --- |
| mean_step_duration_seconds | 31.6 |
| p95_step_duration_seconds | 52 |
| total_run_duration_seconds | 240 |

## Supporting Artifacts

- [Radar lineage source payload](lineage_payload.json)

## Notes

- Lineage payload omits raw source text and raw model prompts/responses.
- Cost uses linked ledger calls when available, otherwise the Radar run aggregate estimate.
- Unsupported-claim rate uses explicit verification counts when present.

## Decision

- Recommendation: review
- Decision: pending_admin_review
