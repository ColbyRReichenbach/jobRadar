#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

export VITE_API_URL="${VITE_API_URL:-http://localhost:8000}"
export VITE_COPILOT_ENABLED="${VITE_COPILOT_ENABLED:-true}"
export VITE_ADMIN_AI_OPS_ENABLED="${VITE_ADMIN_AI_OPS_ENABLED:-true}"
export VITE_LOCAL_DEV_AUTH="${VITE_LOCAL_DEV_AUTH:-false}"

pytest_targets=(
  tests/test_admin_security.py
  tests/test_ai_hardening.py
  tests/test_copilot_api.py
  tests/test_copilot_security.py
  tests/test_copilot_abuse_controls.py
  tests/test_search_indexing.py
  tests/test_search_user_isolation.py
  tests/test_ai_usage.py
  tests/test_ai_artifacts.py
  tests/test_model_cards.py
  tests/test_ai_token_accounting.py
  tests/test_ai_experiments.py
  tests/test_ai_promotion_reports.py
  tests/test_experiment_statistics.py
  tests/test_admin_ai_telemetry.py
  tests/test_classifier_eval.py
  tests/test_search_eval.py
  tests/test_copilot_eval.py
  tests/test_red_team_eval.py
  tests/test_report_generation.py
  tests/test_progress_index.py
  tests/test_radar_lineage.py
  tests/test_radar_quality_metrics.py
  tests/test_ai_retention.py
  tests/test_ai_reprocessing_policy.py
)

existing_pytest_targets=()
for target in "${pytest_targets[@]}"; do
  if [ -f "$target" ]; then
    existing_pytest_targets+=("$target")
  fi
done

if [ "${#existing_pytest_targets[@]}" -gt 0 ]; then
  pytest -q "${existing_pytest_targets[@]}"
else
  echo "No targeted backend AI feature tests exist yet; skipping backend AI feature suite."
fi

playwright_targets=(
  tests/copilot-contract.spec.ts
  tests/copilot-a11y.spec.ts
  tests/admin-ai-ops.spec.ts
)

existing_playwright_targets=()
for target in "${playwright_targets[@]}"; do
  if [ -f "dashboardv2/$target" ]; then
    existing_playwright_targets+=("$target")
  fi
done

if [ "${#existing_playwright_targets[@]}" -gt 0 ]; then
  (cd dashboardv2 && npx playwright test "${existing_playwright_targets[@]}")
else
  echo "No targeted dashboard AI feature tests exist yet; skipping dashboard AI feature suite."
fi
