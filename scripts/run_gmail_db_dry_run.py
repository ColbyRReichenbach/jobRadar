#!/usr/bin/env python3
"""Run the hybrid Gmail classifier against local DB email_events with no LLM calls."""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.database import async_session_factory
from backend.services.evals.gmail_db_dry_run import (
    GmailDbDryRunOptions,
    run_db_gmail_dry_run,
    write_db_dry_run_artifacts,
)


def _default_output_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    return Path("audit/runs/gmail_classifier_dry_run") / stamp


async def _run(args: argparse.Namespace) -> Path:
    options = GmailDbDryRunOptions(
        user_id=uuid.UUID(args.user_id) if args.user_id else None,
        limit=args.limit,
        include_hidden=args.include_hidden,
        ai_consent=not args.no_ai_consent,
        include_redacted_body_preview=not args.no_redacted_body_preview,
        manual_review_limit=args.manual_review_limit,
    )
    async with async_session_factory() as db:
        result = await run_db_gmail_dry_run(db, options)
    output_dir = args.output_dir or _default_output_dir()
    return write_db_dry_run_artifacts(result, output_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", help="Optional user UUID filter.")
    parser.add_argument("--limit", type=int, default=500, help="Maximum email_events rows to dry-run.")
    parser.add_argument("--manual-review-limit", type=int, default=300)
    parser.add_argument("--include-hidden", action="store_true")
    parser.add_argument("--no-ai-consent", action="store_true", help="Simulate missing AI consent for preflight.")
    parser.add_argument("--no-redacted-body-preview", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    output = asyncio.run(_run(args))
    print(output)


if __name__ == "__main__":
    main()
