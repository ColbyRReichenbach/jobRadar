#!/usr/bin/env python3
"""Generate an immutable Radar lineage report from DB rows or a saved payload."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.services.research_radar.lineage import collect_radar_lineage, write_radar_lineage_report_bundle


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT_DIR,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or "unknown"


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


async def _collect_from_database(args: argparse.Namespace) -> dict:
    from backend.database import async_session_factory

    async with async_session_factory() as db:
        return await collect_radar_lineage(
            db,
            user_id=args.user_id,
            report_id=args.report_id,
            run_id=args.run_id,
            as_of=_parse_datetime(args.generated_at),
        )


def _load_lineage_payload(args: argparse.Namespace) -> dict:
    if args.input_json:
        return json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    if not args.user_id or not (args.report_id or args.run_id):
        raise SystemExit("--user-id and either --report-id or --run-id are required when --input-json is not used")
    return asyncio.run(_collect_from_database(args))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-json", help="Saved Radar lineage JSON payload to render")
    parser.add_argument("--user-id", help="User UUID for DB-backed lineage collection")
    parser.add_argument("--report-id", help="Research report UUID for DB-backed lineage collection")
    parser.add_argument("--run-id", help="Research run UUID for DB-backed lineage collection")
    parser.add_argument("--generated-at", help="ISO timestamp for deterministic report generation")
    parser.add_argument("--git-sha", default=None, help="Git SHA to place in report metadata")
    parser.add_argument("--release-version", default="local", help="Release/version label")
    parser.add_argument("--output-dir", default="docs/ai-artifacts/generated", help="Generated report directory")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing generated report folder")
    parser.add_argument("--ai-summary", default=None, help="Optional summary generated only from computed inputs")
    args = parser.parse_args()

    lineage = _load_lineage_payload(args)
    output = write_radar_lineage_report_bundle(
        lineage,
        args.output_dir,
        generated_at=_parse_datetime(args.generated_at),
        git_sha=args.git_sha or _git_sha(),
        release_version=args.release_version,
        overwrite=args.overwrite,
        ai_summary=args.ai_summary,
    )
    print(output)


if __name__ == "__main__":
    main()
