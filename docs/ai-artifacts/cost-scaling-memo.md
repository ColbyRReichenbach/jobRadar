# Cost Scaling Memo

Date: 2026-05-02
System: AppTrail / Opportunity Radar AI platform
Evidence status: Uses implemented token/cost ledger fields and deterministic projections. Projection values are examples, not live production usage.

## Executive Takeaway

The production question is not "which model is best?" It is "which model and prompt version clear the quality bar at the lowest acceptable latency and cost for this task?"

AppTrail tracks this through `ai_model_calls`: provider, model, prompt version, variant, latency, prompt tokens, context tokens, reasoning tokens, output tokens, billable tokens, cost estimate, status, fallback use, and validation result. Admin AI Ops aggregates this by task so the decision can be reviewed without querying the database.

## Decision Frame

For each AI surface, compare:

- quality: task accuracy, groundedness, answer usefulness, false-positive or false-negative cost
- risk: unsupported claims, prompt injection success, data leakage, PII exposure
- cost: prompt tokens, retrieved context tokens, output tokens, reasoning tokens, cached-token discount
- latency: p50, p95, timeout rate, fallback rate
- scale: expected calls per user per month and expected active users

## Projection Example

Assume a copilot-answer task at 1,000,000 requests.

| Option | Accuracy | Prompt Tokens | Output Tokens | Est. Cost / 1M Calls | Notes |
| --- | ---: | ---: | ---: | ---: | --- |
| Frontier model, long prompt | 98.7% | 3,500 | 700 | $52,500 | Highest quality, expensive at scale |
| Smaller model, long prompt | 95.0% | 3,500 | 700 | $26,250 | 3.7 point quality drop, 50% lower cost |
| Frontier model, compact prompt | 97.8% | 1,500 | 650 | $27,900 | Most savings come from prompt reduction |
| Smaller model, compact prompt | 94.8% | 1,500 | 650 | $13,950 | Candidate for low-risk tasks only |

These are projections. Actual values must come from `ai_model_calls.cost_estimate_cents`, token fields, and evaluation reports.

## Prompt-Length Tradeoff

Prompt optimization can be more attractive than model downgrading when it preserves quality. A 2,000-token reduction across 1,000,000 calls removes 2,000,000,000 input tokens. At enterprise traffic, that can be a larger savings lever than small provider-level price differences.

Production workflow:

1. Define a task-specific minimum quality bar.
2. Run deterministic evals for candidate prompt/model variants.
3. Shadow-test candidate variants on real traffic without user-visible output.
4. Compare quality, latency, fallback rate, and cost.
5. Generate a promotion report.
6. Require admin review before promotion.

## Recommended Decision Rule

Promote a cheaper model or shorter prompt only when:

- quality remains above the task-specific threshold
- critical red-team cases still pass
- latency improves or remains neutral
- cost savings are material at projected scale
- the rollback plan is documented in the model card

## What This Shows

This artifact demonstrates that the system treats AI as an operating cost and risk surface, not a single API call. The ledger makes tradeoffs measurable; Admin AI Ops makes them reviewable; promotion reports make changes governed.
