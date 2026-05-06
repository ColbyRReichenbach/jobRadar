#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/.env.local}"
BACKEND_URL="http://localhost:8000"
DASHBOARD_URL="http://localhost:3000"

log() {
  printf '[apptrail] %s\n' "$1"
}

have_command() {
  command -v "$1" >/dev/null 2>&1
}

open_url() {
  local url="$1"
  if have_command open; then
    open "$url" >/dev/null 2>&1 || true
    return
  fi
  if have_command xdg-open; then
    xdg-open "$url" >/dev/null 2>&1 || true
  fi
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local retries="${3:-120}"
  local delay_seconds="${4:-2}"

  for ((i = 1; i <= retries; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      log "$label is ready."
      return 0
    fi
    sleep "$delay_seconds"
  done

  log "Timed out waiting for $label at $url"
  return 1
}

verify_backend_identity() {
  local openapi
  if ! openapi="$(curl -fsS "$BACKEND_URL/openapi.json" 2>/dev/null)"; then
    log "Backend health responded, but OpenAPI metadata was unavailable at $BACKEND_URL."
    log "Check that AppTrail is the process listening on port 8000."
    return 1
  fi

  if ! python3 -c 'import json,sys; data=json.load(sys.stdin); paths=data.get("paths",{}); raise SystemExit(0 if "/api/gmail/sync" in paths and "/api/auth/local-login" in paths else 1)' <<<"$openapi"; then
    log "Port 8000 is responding, but it is not the AppTrail backend expected by the dashboard."
    log "Stop the process currently using port 8000, then rerun this script."
    if have_command lsof; then
      lsof -nP -iTCP:8000 -sTCP:LISTEN || true
    fi
    return 1
  fi

  log "Backend route check passed."
}

ensure_env_file() {
  if [[ -f "$ENV_FILE" ]]; then
    return
  fi
  log "No local env found. Creating $ENV_FILE"
  "$ROOT_DIR/scripts/setup_local_env.sh" "$ENV_FILE"
}

ensure_docker_running() {
  if docker info >/dev/null 2>&1; then
    return
  fi

  if have_command open; then
    log "Docker is not running. Opening Docker Desktop."
    open -a Docker >/dev/null 2>&1 || true
  fi

  log "Waiting for Docker to become available..."
  for ((i = 1; i <= 120; i++)); do
    if docker info >/dev/null 2>&1; then
      log "Docker is ready."
      return 0
    fi
    sleep 2
  done

  log "Docker did not become available. Start Docker Desktop and rerun this command."
  return 1
}

load_env() {
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
}

attempt_gmail_sync() {
  if [[ "${LOCAL_DEV_AUTH:-}" != "1" && "${LOCAL_DEV_AUTH:-}" != "true" ]]; then
    log "Skipping startup Gmail sync because local dev auth is disabled."
    return 0
  fi

  local login_response
  if ! login_response="$(
    curl -fsS \
      -X POST \
      -H 'Content-Type: application/json' \
      -d '{}' \
      "$BACKEND_URL/api/auth/local-login"
  )"; then
    log "Could not create the local session for Gmail sync."
    return 0
  fi

  local access_token
  access_token="$(
    python3 -c 'import json,sys; print(json.load(sys.stdin).get("access_token",""))' <<<"$login_response"
  )"

  if [[ -z "$access_token" ]]; then
    log "No local access token returned, so Gmail sync was skipped."
    return 0
  fi

  local sync_response
  sync_response="$(
    curl -sS \
      -X POST \
      -H "Authorization: Bearer $access_token" \
      "$BACKEND_URL/api/gmail/sync"
  )"

  local sync_status
  sync_status="$(
    python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("status","")) if isinstance(data, dict) else print("")' <<<"$sync_response" 2>/dev/null || true
  )"
  local sync_detail
  sync_detail="$(
    python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("detail","")) if isinstance(data, dict) else print("")' <<<"$sync_response" 2>/dev/null || true
  )"

  if [[ "$sync_status" == "ok" ]]; then
    log "Startup Gmail sync completed."
    return 0
  fi

  if [[ "$sync_detail" == "Gmail not connected. Please connect your Gmail account first." ]]; then
    log "Startup Gmail sync skipped because Gmail is not connected for the local account yet."
    return 0
  fi

  if [[ -n "$sync_detail" ]]; then
    log "Startup Gmail sync did not complete: $sync_detail"
    return 0
  fi

  log "Startup Gmail sync did not complete."
}

main() {
  cd "$ROOT_DIR"

  if ! have_command docker; then
    log "Docker is required but not installed."
    exit 1
  fi

  if ! have_command curl; then
    log "curl is required but not installed."
    exit 1
  fi

  if ! have_command python3; then
    log "python3 is required but not installed."
    exit 1
  fi

  ensure_env_file
  load_env
  ensure_docker_running

  log "Starting the local stack..."
  docker compose up --build -d

  wait_for_url "$BACKEND_URL/api/health" "Backend API"
  verify_backend_identity
  wait_for_url "$DASHBOARD_URL" "Dashboard"

  open_url "$DASHBOARD_URL"
  attempt_gmail_sync

  log "AppTrail is up."
  log "Dashboard: $DASHBOARD_URL"
  log "API: $BACKEND_URL"
}

main "$@"
