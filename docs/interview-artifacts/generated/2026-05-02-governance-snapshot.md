---
artifact_type: governance_snapshot
generated_at: 2026-05-02
source: implemented schema, services, and tests
status: implementation_evidence
---

# 2026-05-02 Governance Snapshot

Implemented controls:

- `ai_model_calls` records model, prompt version, variant, latency, token, cost, status, and validation metadata.
- `ai_artifacts` links generated outputs to model calls.
- `ai_model_cards` stores intended use, limitations, metrics, approval state, and rollback plan.
- `ai_promotion_reports` requires admin review before promotion.
- Admin AI Ops exposes telemetry, lineage, redacted drilldowns, access logs, and promotion review.
- Full trace access requires a reason and creates an access log.

Validation:

- `tests/test_ai_usage.py`
- `tests/test_ai_artifacts.py`
- `tests/test_model_cards.py`
- `tests/test_ai_promotion_reports.py`
- `tests/test_admin_ai_telemetry.py`
- `tests/test_ai_retention.py`
