#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR/dashboardv2"

export VITE_API_URL="${VITE_API_URL:-http://localhost:8000}"
export VITE_COPILOT_ENABLED="${VITE_COPILOT_ENABLED:-true}"
export VITE_ADMIN_AI_OPS_ENABLED="${VITE_ADMIN_AI_OPS_ENABLED:-true}"
export VITE_LOCAL_DEV_AUTH="${VITE_LOCAL_DEV_AUTH:-false}"

npm run lint
npm run test:smoke
