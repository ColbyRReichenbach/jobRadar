#!/usr/bin/env bash
set -euo pipefail

require_url() {
  local name="$1"
  local value="${!name:-}"
  if [ -z "$value" ]; then
    echo "$name is required for post-deploy smoke checks" >&2
    exit 1
  fi
}

trim_trailing_slash() {
  local value="$1"
  printf '%s' "${value%/}"
}

require_url PRODUCTION_API_URL
require_url PRODUCTION_DASHBOARD_URL

API_URL="$(trim_trailing_slash "$PRODUCTION_API_URL")"
DASHBOARD_URL="$(trim_trailing_slash "$PRODUCTION_DASHBOARD_URL")"

curl -fsS "$API_URL/api/health" >/dev/null
curl -fsS "$DASHBOARD_URL" >/dev/null

if [ "${POST_DEPLOY_DEEP_SMOKE:-false}" = "true" ]; then
  curl -fsS "$API_URL/api/ready" >/dev/null
fi

admin_metrics_status="$(curl -sS -o /dev/null -w "%{http_code}" "$API_URL/api/ai/metrics")"
case "$admin_metrics_status" in
  401|403)
    ;;
  *)
    echo "Expected /api/ai/metrics to deny unauthenticated access; got HTTP $admin_metrics_status" >&2
    exit 1
    ;;
esac

if [ "${POST_DEPLOY_DEEP_SMOKE:-false}" = "true" ] && [ -n "${POST_DEPLOY_SMOKE_BEARER:-}" ]; then
  curl -fsS \
    -H "Authorization: Bearer $POST_DEPLOY_SMOKE_BEARER" \
    "$API_URL/api/ready" >/dev/null
fi
