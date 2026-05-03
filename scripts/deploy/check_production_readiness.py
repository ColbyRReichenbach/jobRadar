#!/usr/bin/env python3
"""Validate production deployment configuration without printing secrets."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services.production_readiness import validate_production_environment  # noqa: E402


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def merged_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for candidate in (ROOT / ".deploy.generated.env", ROOT / ".deploy.secrets.local", ROOT / ".env"):
        values.update({key: value for key, value in read_env_file(candidate).items() if value})
    values.update({key: value for key, value in os.environ.items() if value})
    return values


def alembic_has_single_head() -> bool:
    result = subprocess.run(
        ["alembic", "heads"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        print("Alembic head check failed.")
        print(result.stderr.strip())
        return False
    heads = [line for line in result.stdout.splitlines() if line.strip()]
    if len(heads) != 1:
        print(f"Expected exactly one Alembic head, found {len(heads)}.")
        return False
    print(f"Alembic head: {heads[0]}")
    return True


def main() -> int:
    values = merged_values()
    issues = validate_production_environment(values)
    for issue in issues:
        print(f"{issue.severity.upper()}: {issue.key}: {issue.message}")
    heads_ok = alembic_has_single_head()
    if issues or not heads_ok:
        return 1
    print("Production readiness configuration checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
