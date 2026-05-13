#!/usr/bin/env python3
"""Export private Gmail samples into a redacted labeling CSV.

This reads Gmail messages through the user's already-connected OAuth tokens,
runs the deterministic hybrid classifier with no model calls, and writes a
local-only labeling queue under ``audit/runs``. It intentionally samples before
product storage so filtered/noise messages remain available for eval labeling.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from googleapiclient.discovery import build
from sqlalchemy import select

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.database import async_session_factory
from backend.models import User
from backend.services.company_identity import extract_domain
from backend.services.email_parser import extract_sender_parts, parse_email_body
from backend.services.gmail_auth import get_valid_token
from backend.services.gmail_intelligence.orchestrator import analyze_email
from backend.services.gmail_intelligence.preflight import evaluate_llm_preflight
from backend.services.gmail_intelligence.privacy import redact_email_for_llm, redact_text_for_llm
from backend.services.gmail_intelligence.types import EmailCandidate
from backend.services.source_intelligence.url_classifier import extract_urls_from_gmail_payload


EXPECTED_ROUTES = [
    "filter",
    "application_inbox",
    "opportunity_discovery",
    "conversation",
    "action_review",
    "unsure",
]

EXPECTED_SUBTYPES = [
    "application_received",
    "application_status_update",
    "interview_request",
    "rejection",
    "offer",
    "assessment_or_task",
    "document_request",
    "recruiter_outreach",
    "referral_or_networking",
    "job_alert",
    "job_board_promo",
    "career_fair_or_event",
    "company_newsletter",
    "marketing_promo",
    "finance_noise",
    "retail_noise",
    "system_notification",
    "personal_email",
    "school_or_alumni_update",
    "unknown_other",
    "unsure",
]

ERROR_BUCKETS = [
    "correct",
    "false_positive_noise",
    "false_positive_opportunity_as_lifecycle",
    "false_positive_marketing_as_conversation",
    "false_negative_job_related",
    "wrong_route",
    "wrong_stage",
    "overconfident_score",
    "missing_context",
    "pii_redaction_issue",
    "duplicate_or_thread_noise",
    "unsure",
]

@dataclass(frozen=True)
class AccountSpec:
    email: str
    max_messages: int


def _hash(value: object, *, prefix: str = "") -> str:
    digest = hashlib.sha256(str(value or "").strip().lower().encode("utf-8")).hexdigest()[:16]
    return f"{prefix}{digest}" if prefix else digest


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _truncate(value: str | None, limit: int) -> str:
    normalized = " ".join((value or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _join(values: object) -> str:
    if isinstance(values, list):
        return ";".join(str(value) for value in values)
    if isinstance(values, dict):
        return json.dumps(values, sort_keys=True)
    return str(values or "")


def _parse_account_spec(value: str, default_max: int) -> AccountSpec:
    if ":" not in value:
        return AccountSpec(email=value.strip().lower(), max_messages=default_max)
    email, raw_limit = value.rsplit(":", 1)
    return AccountSpec(email=email.strip().lower(), max_messages=int(raw_limit))


def _parse_account_role(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--account-role must use email=role format")
    email, role = value.split("=", 1)
    email = email.strip().lower()
    role = role.strip()
    if not email or not role:
        raise argparse.ArgumentTypeError("--account-role requires non-empty email and role")
    return email, role


def _load_account_roles(values: list[str]) -> dict[str, str]:
    roles: dict[str, str] = {}
    for value in values:
        email, role = _parse_account_role(value)
        roles[email] = role
    return roles


def _parse_received_at(headers: dict[str, str]) -> datetime | None:
    value = headers.get("date") or ""
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _priority(row: dict[str, Any]) -> tuple[int, str]:
    score = 0
    reasons: list[str] = []
    account_role = row["account_role"]
    route = row["predicted_route"]
    subtype = row["predicted_subtype"]
    domain = row["sender_domain"].lower()

    if account_role == "main_applications":
        score += 15
        reasons.append("main_account")
    if account_role == "junk_noise" and route != "filter":
        score += 65
        reasons.append("junk_not_filtered")
    if account_role == "alumni_job_board_promos":
        score += 15
        reasons.append("alumni_job_board_account")
    if route in {"application_inbox", "conversation", "action_review"}:
        score += 45
        reasons.append("stored_surface_candidate")
    if subtype in {"application_received", "application_status_update", "interview_request", "rejection", "assessment_or_task"}:
        score += 30
        reasons.append("application_lifecycle_subtype")
    if subtype in {"job_alert", "job_board_promo"}:
        score += 20
        reasons.append("job_board_or_alert")
    if row["would_call_llm"] == "true":
        score += 30
        reasons.append("would_call_llm")
    if row["confidence_band"] != "high":
        score += 20
        reasons.append("not_high_confidence")
    if any(token in domain for token in ("handshake", "linkedin", "indeed", "greenhouse", "lever", "ashby", "workday", "icims")):
        score += 15
        reasons.append("known_recruiting_or_ats_domain")
    return score, ";".join(reasons) or "baseline_sample"


async def _fetch_message_ids(service, *, query: str, max_messages: int) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    next_page_token = None
    while len(messages) < max_messages:
        request_kwargs = {
            "userId": "me",
            "q": query,
            "maxResults": min(500, max_messages - len(messages)),
        }
        if next_page_token:
            request_kwargs["pageToken"] = next_page_token
        response = service.users().messages().list(**request_kwargs).execute()
        messages.extend(response.get("messages", []))
        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break
    return messages


async def _classify_message(
    *,
    account_email: str,
    account_roles: dict[str, str],
    user_id: str,
    msg: dict[str, Any],
) -> dict[str, Any]:
    payload = msg.get("payload", {})
    headers = {item["name"].lower(): item["value"] for item in payload.get("headers", [])}
    sender_name, sender_email = extract_sender_parts(headers.get("from", ""))
    sender_domain = extract_domain(sender_email)
    received_at = _parse_received_at(headers)
    body = parse_email_body(payload)
    raw_urls = tuple(extract_urls_from_gmail_payload(payload))
    subject = headers.get("subject", "")

    candidate = EmailCandidate(
        subject=subject,
        body=body or msg.get("snippet", ""),
        sender=sender_name,
        sender_email=sender_email,
        received_at=received_at,
        raw_candidate_urls=raw_urls,
    )
    analysis = await analyze_email(candidate, ai_enabled=False, ai_consent=True)
    preflight = evaluate_llm_preflight(candidate, ai_consent=True, thresholds=analysis.thresholds)
    redacted = redact_email_for_llm(analysis.normalized)
    redacted_snippet, snippet_counts, _ = redact_text_for_llm(msg.get("snippet", ""))
    result = analysis.result
    scores = analysis.scores

    row: dict[str, Any] = {
        "case_id": _hash(f"{user_id}:{msg.get('id')}", prefix="gmail_case_"),
        "account_email": account_email,
        "account_role": account_roles.get(account_email.lower(), "connected_gmail"),
        "received_at": received_at.isoformat() if received_at else "",
        "sender_domain": sender_domain,
        "sender_ref": _hash(sender_email, prefix="sender_") if sender_email else "",
        "thread_ref": _hash(msg.get("threadId"), prefix="thread_") if msg.get("threadId") else "",
        "redacted_sender": redacted.sender,
        "redacted_sender_email": redacted.sender_email,
        "redacted_subject": _truncate(redacted.subject, 240),
        "redacted_snippet": _truncate(redacted_snippet, 300),
        "redacted_body_preview": _truncate(redacted.body, 1200),
        "predicted_route": result.route,
        "predicted_subtype": result.subtype,
        "predicted_classification": result.classification,
        "predicted_confidence": round(float(result.confidence or 0), 4),
        "confidence_band": result.confidence_band,
        "decision_path": result.decision_path,
        "action_needed": str(bool(result.action_needed)).lower(),
        "status_update_allowed": str(bool(result.status_update_allowed)).lower(),
        "is_automated": str(bool(result.is_automated)).lower(),
        "would_call_llm": str(bool(preflight.should_call_llm)).lower(),
        "preflight_blocked": str(bool(preflight.blocked)).lower(),
        "preflight_block_reason": preflight.block_reason or "",
        "job_signal_score": round(float(scores.job_signal_score or 0), 4),
        "noise_score": round(float(scores.noise_score or 0), 4),
        "top_route_score": round(float(scores.top_route_score or 0), 4),
        "second_route_score": round(float(scores.second_route_score or 0), 4),
        "route_margin": round(float(scores.route_margin or 0), 4),
        "top_subtype_score": round(float(scores.top_subtype_score or 0), 4),
        "subtype_margin": round(float(scores.subtype_margin or 0), 4),
        "matched_features": _join(result.matched_features),
        "ambiguity_reasons": _join(result.ambiguity_reasons),
        "redaction_counts": _join(redacted.redaction_counts | snippet_counts),
        "candidate_source_url_count": len(raw_urls),
        "expected_route": "",
        "expected_subtype": "",
        "action_expected": "",
        "expected_action_type": "",
        "is_correct": "",
        "error_bucket": "",
        "human_labeler": "",
        "human_confidence": "",
        "review_notes": "",
        "llm_label_route": "",
        "llm_label_subtype": "",
        "llm_label_action_expected": "",
        "llm_label_confidence": "",
        "llm_label_rationale": "",
        "llm_matches_human": "",
    }
    priority_score, priority_reason = _priority(row)
    row["priority_score"] = priority_score
    row["priority_reason"] = priority_reason
    return row


async def _export(args: argparse.Namespace) -> Path:
    account_specs = [_parse_account_spec(value, args.default_max_messages) for value in args.account]
    account_roles = _load_account_roles(args.account_role)
    output_dir = args.output_dir or Path("audit/runs/gmail_labeling_sample") / _now_stamp()
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    query = args.query or f"newer_than:{args.days}d"

    async with async_session_factory() as db:
        user_stmt = select(User).where(User.gmail_connected.is_(True))
        if account_specs:
            user_stmt = user_stmt.where(User.email.in_([spec.email for spec in account_specs]))
        users = list((await db.execute(user_stmt.order_by(User.email))).scalars().all())
        spec_by_email = {spec.email: spec for spec in account_specs}
        for user in users:
            account_email = (user.email or "").lower()
            max_messages = spec_by_email.get(account_email, AccountSpec(account_email, args.default_max_messages)).max_messages
            creds = await get_valid_token(db, user_id=user.id)
            service = build("gmail", "v1", credentials=creds, cache_discovery=False)
            message_refs = await _fetch_message_ids(service, query=query, max_messages=max_messages)
            for msg_ref in message_refs:
                try:
                    msg = service.users().messages().get(userId="me", id=msg_ref["id"], format="full").execute()
                    rows.append(
                        await _classify_message(
                            account_email=account_email,
                            account_roles=account_roles,
                            user_id=str(user.id),
                            msg=msg,
                        )
                    )
                except Exception as exc:
                    errors.append(
                        {
                            "account_email": account_email,
                            "message_ref": _hash(msg_ref.get("id"), prefix="gmail_"),
                            "error_type": type(exc).__name__,
                            "error": str(exc)[:500],
                        }
                    )

    rows.sort(key=lambda row: (-int(row["priority_score"]), row["account_email"], row["received_at"]), reverse=False)
    fieldnames = list(rows[0].keys()) if rows else []
    for name, selected in [
        ("label_queue_all.csv", rows),
        ("label_queue_priority.csv", rows[: args.priority_limit]),
    ]:
        with (output_dir / name).open("w", newline="", encoding="utf-8") as handle:
            if fieldnames:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(selected)

    (output_dir / "trace.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in rows),
        encoding="utf-8",
    )
    if errors:
        (output_dir / "errors.jsonl").write_text(
            "".join(json.dumps(error, sort_keys=True) + "\n" for error in errors),
            encoding="utf-8",
        )

    summary = {
        "generated_at": _now_stamp(),
        "query": query,
        "row_count": len(rows),
        "error_count": len(errors),
        "account_counts": dict(Counter(row["account_email"] for row in rows)),
        "account_role_counts": dict(Counter(row["account_role"] for row in rows)),
        "predicted_route_counts": dict(Counter(row["predicted_route"] for row in rows)),
        "predicted_subtype_counts": dict(Counter(row["predicted_subtype"] for row in rows)),
        "would_call_llm_count": sum(1 for row in rows if row["would_call_llm"] == "true"),
        "priority_limit": args.priority_limit,
        "llm_calls_made": 0,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "label_values.json").write_text(
        json.dumps(
            {
                "expected_routes": EXPECTED_ROUTES,
                "expected_subtypes": EXPECTED_SUBTYPES,
                "error_buckets": ERROR_BUCKETS,
                "account_roles": account_roles,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (output_dir / "labeling_guidelines.md").write_text(_render_guidelines(), encoding="utf-8")
    return output_dir


def _render_guidelines() -> str:
    return """# Gmail Labeling Sample Guidelines

These files are private real-email-derived artifacts. Keep them under `audit/runs/` and do not commit completed labels.

## Labeling Columns

Fill these manually:

- `expected_route`
- `expected_subtype`
- `action_expected`
- `expected_action_type`
- `is_correct`
- `error_bucket`
- `human_labeler`
- `human_confidence`
- `review_notes`

Leave `llm_label_*` columns blank for now. They are reserved for a separate LLM-as-labeler experiment so we can compare LLM labels against human labels without mixing that into product classifier metrics.

## Expected Routes

- `filter`: should not appear in AppTrail.
- `application_inbox`: application lifecycle email tied to a candidate process.
- `conversation`: human recruiter, referral, alumni, or networking message.
- `action_review`: job-related but too ambiguous or action-heavy for automatic routing.
- `opportunity_discovery`: future source-intelligence signal, not a normal product inbox item.
- `unsure`: redacted preview is insufficient.

## Expected Subtypes

Use values from `label_values.json`. Common decisions:

- Application confirmations: `application_received`.
- Rejections: `rejection`.
- Interview/scheduling requests: `interview_request`.
- Take-home or assessment requests: `assessment_or_task`.
- Human recruiter outreach: `recruiter_outreach`.
- Job alerts or recommendation digests: `job_alert`, usually with `expected_route=filter`.
- Job-board platform promos: `job_board_promo`, usually with `expected_route=filter`.
- Generic junk: `marketing_promo`, `retail_noise`, `finance_noise`, or `system_notification`.

## Recommended Workflow

1. Label `label_queue_priority.csv` first.
2. Do not label every row immediately. Stop after 100-150 rows and run metrics.
3. Prioritize rows where `would_call_llm=true`, route is not `filter`, or account role is `junk_noise` but predicted route is not `filter`.
4. Use `label_queue_all.csv` only to fill coverage gaps after the first metrics pass.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--account",
        action="append",
        default=[],
        help="Account email or email:max_messages. Repeatable. Defaults to all connected Gmail accounts.",
    )
    parser.add_argument(
        "--account-role",
        action="append",
        default=[],
        help=(
            "Optional email=role hint for local priority sampling. Repeatable. "
            "Example roles: main_applications, junk_noise, alumni_job_board_promos."
        ),
    )
    parser.add_argument("--default-max-messages", type=int, default=100)
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--query", help="Override Gmail query. Defaults to newer_than:<days>d.")
    parser.add_argument("--priority-limit", type=int, default=180)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output = asyncio.run(_export(args))
    print(output)


if __name__ == "__main__":
    main()
