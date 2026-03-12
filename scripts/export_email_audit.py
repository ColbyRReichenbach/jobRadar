#!/usr/bin/env python3
"""Export synced emails into a reviewable CSV for classification audits."""

from __future__ import annotations

import argparse
import asyncio
import csv
from pathlib import Path
import sys

from sqlalchemy import select

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.database import async_session_factory
from backend.models import EmailEvent, User
from backend.services.email_classifier import classify_email, should_create_network_contact


def _decision_bucket(classification: str | None, email_type: str | None) -> str:
    if classification == "not_relevant":
        return "filter"
    if email_type == "conversation" or classification == "conversation":
        return "conversation"
    return "inbox"


def _inbox_tag(classification: str | None) -> str:
    if classification in {"interview_request", "rejection", "offer", "action_item", "job_update"}:
        return classification
    return ""


def _clip(text: str | None, limit: int = 600) -> str:
    if not text:
        return ""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


async def _resolve_user_id(user_email: str | None, user_id: str | None) -> tuple[str, str]:
    async with async_session_factory() as session:
        if user_id:
            stmt = select(User).where(User.id == user_id)
        elif user_email:
            stmt = select(User).where(User.email == user_email)
        else:
            stmt = select(User).order_by(User.created_at.desc()).limit(2)
            result = await session.execute(stmt)
            users = result.scalars().all()
            if not users:
                raise SystemExit("No users found in the database.")
            if len(users) > 1:
                raise SystemExit("Multiple users found. Pass --user-email or --user-id.")
            return str(users[0].id), users[0].email

        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if not user:
            raise SystemExit("Could not find the requested user.")
        return str(user.id), user.email


async def _load_emails(user_id: str, limit: int, include_hidden: bool) -> list[EmailEvent]:
    async with async_session_factory() as session:
        stmt = select(EmailEvent).where(EmailEvent.user_id == user_id)
        if not include_hidden:
            stmt = stmt.where(EmailEvent.hidden.is_(False))
        stmt = stmt.order_by(EmailEvent.received_at.desc()).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def _audit_email(email: EmailEvent, rerun_llm: bool) -> dict[str, str]:
    existing_decision = _decision_bucket(email.classification, email.email_type)
    row = {
        "email_id": str(email.id),
        "gmail_message_id": email.gmail_message_id or "",
        "received_at": email.received_at.isoformat() if email.received_at else "",
        "sender": email.sender or "",
        "sender_email": email.sender_email or "",
        "sender_domain": email.sender_domain or "",
        "subject": email.subject or "",
        "body_excerpt": _clip(email.body or email.snippet),
        "existing_classification": email.classification or "",
        "existing_decision": existing_decision,
        "existing_inbox_tag": _inbox_tag(email.classification),
        "existing_confidence": str(email.confidence or ""),
        "predicted_classification": email.classification or "",
        "predicted_decision": existing_decision,
        "predicted_inbox_tag": _inbox_tag(email.classification),
        "predicted_confidence": str(email.confidence or ""),
        "predicted_sender_role": "",
        "predicted_is_automated": "",
        "predicted_action_needed": str(bool(email.action_needed)),
        "predicted_network_contact": str(
            should_create_network_contact(email.sender or "", email.sender_email or "", email.classification)
        ),
        "predicted_summary": email.summary or "",
        "predicted_key_sentence": email.key_sentence or "",
        "review_correct": "",
        "review_expected_decision": "",
        "review_expected_classification": "",
        "review_expected_network_contact": "",
        "review_reason": "",
    }

    if not rerun_llm:
        return row

    body = email.body or email.snippet or ""
    prediction = await classify_email(
        subject=email.subject or "",
        body=body,
        sender=email.sender or "",
        sender_email=email.sender_email or "",
    )
    predicted_classification = prediction.get("classification", email.classification or "")
    predicted_decision = _decision_bucket(predicted_classification, None if predicted_classification != "conversation" else "conversation")

    row.update(
        predicted_classification=predicted_classification,
        predicted_decision=predicted_decision,
        predicted_inbox_tag=_inbox_tag(predicted_classification),
        predicted_confidence=str(prediction.get("confidence", "")),
        predicted_sender_role=prediction.get("sender_role", "") or "",
        predicted_is_automated=str(bool(prediction.get("is_automated", False))),
        predicted_action_needed=str(bool(prediction.get("action_needed", False))),
        predicted_network_contact=str(
            should_create_network_contact(email.sender or "", email.sender_email or "", predicted_classification)
        ),
        predicted_summary=prediction.get("summary", "") or "",
        predicted_key_sentence=prediction.get("key_sentence", "") or "",
    )
    return row


async def main() -> None:
    parser = argparse.ArgumentParser(description="Export a CSV to audit email classification decisions.")
    parser.add_argument("--user-email", help="Email of the user whose synced emails should be exported.")
    parser.add_argument("--user-id", help="UUID of the user whose synced emails should be exported.")
    parser.add_argument("--limit", type=int, default=250, help="Number of emails to export. Default: 250.")
    parser.add_argument("--include-hidden", action="store_true", help="Include locally hidden emails in the audit.")
    parser.add_argument(
        "--use-stored-only",
        action="store_true",
        help="Do not re-run the LLM. Export stored classifications only.",
    )
    parser.add_argument(
        "--output",
        default="email_audit.csv",
        help="Output CSV path. Default: email_audit.csv",
    )
    args = parser.parse_args()

    user_id, resolved_email = await _resolve_user_id(args.user_email, args.user_id)
    emails = await _load_emails(user_id=user_id, limit=args.limit, include_hidden=args.include_hidden)
    if not emails:
        raise SystemExit("No emails found for the selected user.")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    for index, email in enumerate(emails, start=1):
        print(f"[{index}/{len(emails)}] auditing {email.subject or '(no subject)'}")
        rows.append(await _audit_email(email, rerun_llm=not args.use_stored_only))

    fieldnames = [
        "email_id",
        "gmail_message_id",
        "received_at",
        "sender",
        "sender_email",
        "sender_domain",
        "subject",
        "body_excerpt",
        "existing_classification",
        "existing_decision",
        "existing_inbox_tag",
        "existing_confidence",
        "predicted_classification",
        "predicted_decision",
        "predicted_inbox_tag",
        "predicted_confidence",
        "predicted_sender_role",
        "predicted_is_automated",
        "predicted_action_needed",
        "predicted_network_contact",
        "predicted_summary",
        "predicted_key_sentence",
        "review_correct",
        "review_expected_decision",
        "review_expected_classification",
        "review_expected_network_contact",
        "review_reason",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows for {resolved_email} to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
