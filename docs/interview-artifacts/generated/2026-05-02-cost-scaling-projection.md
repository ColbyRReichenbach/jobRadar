---
artifact_type: cost_scaling_projection
generated_at: 2026-05-02
source: deterministic projection
status: projection_not_live_usage
---

# 2026-05-02 Cost Scaling Projection

This generated artifact supports [Cost Scaling Memo](../cost-scaling-memo.md). Values are projections used to explain production AI cost thinking. They are not live AppTrail usage.

| Scenario | Requests | Input Tokens / Request | Output Tokens / Request | Relative Cost |
| --- | ---: | ---: | ---: | ---: |
| Long prompt | 1,000,000 | 3,500 | 700 | 1.00x |
| Compact prompt | 1,000,000 | 1,500 | 650 | 0.53x |
| Compact prompt plus cheaper model | 1,000,000 | 1,500 | 650 | 0.27x |

Decision note: a cheaper model should not be promoted unless evals and red-team checks stay above the task threshold.
