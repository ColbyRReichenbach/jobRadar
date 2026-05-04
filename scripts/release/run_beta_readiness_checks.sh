#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

echo "== Extension static, unit, package, and store-readiness checks =="
bash scripts/ci/run_extension_checks.sh

echo "== Backend extension privacy/control checks =="
pytest tests/test_api_keys.py tests/test_company_visits.py tests/test_extraction_reports.py -q

if [[ -n "${APPTRAIL_PRODUCTION_API_URL:-}" ]]; then
  echo "== Production API health check =="
  curl -fsS "${APPTRAIL_PRODUCTION_API_URL%/}/api/health" >/dev/null
else
  echo "== Production API health check skipped =="
  echo "Set APPTRAIL_PRODUCTION_API_URL=https://api.apptrail.com to include it."
fi

if [[ -n "${APPTRAIL_EXTENSION_API_KEY:-}" ]]; then
  echo "== Chrome extension install/auth smoke =="
  node scripts/release/smoke_chrome_extension.mjs
else
  echo "== Chrome extension install/auth smoke skipped =="
  echo "Set APPTRAIL_EXTENSION_API_KEY and optional APPTRAIL_EXTENSION_API_BASE to run it."
fi

if command -v gh >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  BRANCH="$(git branch --show-current)"
  if [[ -n "${BRANCH}" ]]; then
    echo "== Latest GitHub Actions run for ${BRANCH} =="
    gh run list --branch "${BRANCH}" --limit 1 || true
  fi
fi

echo "Beta readiness automation completed."
echo "Manual still required: load the packaged extension in Chrome and verify the save/revoke/clear flow against the target backend."
