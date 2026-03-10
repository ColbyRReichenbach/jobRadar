#!/bin/bash
cd "$(git rev-parse --show-toplevel)"
pytest tests/backend/ -q >&2 2>&1
BACKEND_RESULT=$?

if [ $BACKEND_RESULT -eq 0 ]; then
  exit 0
else
  echo "Tests still failing. Fix failing tests before stopping." >&2
  exit 2
fi
