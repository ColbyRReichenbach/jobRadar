# Copilot Eval Report

- Generated at: `2026-05-02T19:45:54.886887+00:00`
- Dataset version: `copilot_questions_v1`
- Decision note: Offline fallback answers are fully grounded on this fixture; live model variants still require red-team and production telemetry gates.

## Metrics

| Metric | Value |
| --- | ---: |
| `case_count` | 4 |
| `pass_rate` | 1.0 |
| `groundedness` | 1.0 |
| `citation_coverage` | 1.0 |
| `unsupported_claim_rate` | 0.0 |
| `refusal_correctness` | 1.0 |
| `p95_latency_ms` | 0.0695 |
| `cost_estimate_cents` | 0 |

## Case Results

| Case | Passed | Citation coverage | Unsupported claim | Failures |
| --- | --- | ---: | --- | --- |
| `copilot-001` | `True` | 1.0 | `False` | none |
| `copilot-002` | `True` | 1.0 | `False` | none |
| `copilot-003` | `True` | 1.0 | `False` | none |
| `copilot-004` | `True` | 1.0 | `False` | none |

## Good Example

- Case: `copilot-001`
- Answer: I found these relevant AppTrail records:
1. TraceBank Assistant Search Data Scientist (application): Applied role focused on NLP search quality models for assistant conversations.

## Bad Examples Caught By Scorer

- `copilot-001` would fail: unsupported_claim, missing_citation
