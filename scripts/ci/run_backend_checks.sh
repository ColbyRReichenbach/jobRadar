#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

pytest -q
python3 -m compileall -q backend
heads_count="$(alembic heads | sed '/^[[:space:]]*$/d' | wc -l | tr -d ' ')"
if [ "$heads_count" != "1" ]; then
  echo "Expected exactly one Alembic head, found $heads_count"
  alembic heads
  exit 1
fi
