"""Classify real Gmail emails from MCP-exported JSON and output audit CSV.

Usage:
    python3 -m audit.pull_real_emails [--input audit/raw_emails_batch1.json] [--output audit/real_email_audit.csv]

Uses OpenAI (gpt-4o-mini) when OPENAI_API_KEY is set, falls back to Anthropic Haiku,
then to rule-based keyword classifier.

Requires:
    - OPENAI_API_KEY or ANTHROPIC_API_KEY in .env
    - Raw email JSON exported via Gmail MCP (gmail_search_messages)
"""

import argparse
import asyncio
import csv
import json
import logging
import os
import sys

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

from backend.services.email_classifier import (  # noqa: E402
    _fallback_classify,
    is_likely_person_sender,
    should_create_network_contact,
    SYSTEM_PROMPT,
)
from backend.services.email_parser import extract_sender_parts  # noqa: E402
from backend.services.company_identity import get_company_info  # noqa: E402
from backend.services.email_filter import is_obvious_noise_email  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ─── Classification → pipeline status mapping (mirrors email_matcher.py) ─────
STATUS_UPDATES = {
    "rejection": "rejected",
    "interview_request": "interviewing",
    "offer": "offer",
    "job_update": "applied",
    "action_item": "applied",
    "conversation": None,      # no auto-status change
    "not_relevant": None,
}

# ─── Classification → email_type mapping (mirrors production) ────────────────
CLASSIFICATION_TO_EMAIL_TYPE = {
    "interview_request": "decision",
    "rejection": "decision",
    "offer": "decision",
    "action_item": "decision",
    "job_update": "decision",
    "conversation": "conversation",
    "not_relevant": None,
}

CSV_COLUMNS = [
    "id",
    "gmail_message_id",
    "thread_id",
    "gmail_labels",
    "sender_name",
    "sender_email",
    "subject",
    "received_at",
    "body_snippet",
    # --- Pre-filter ---
    "is_obvious_noise",
    # --- Classifier outputs ---
    "predicted_decision",       # inbox / filter
    "predicted_classification", # job_update, interview_request, rejection, offer, action_item, conversation, not_relevant
    "predicted_confidence",
    "predicted_is_automated",
    "predicted_sender_role",
    "predicted_action_needed",
    "predicted_summary",
    # --- Network contact ---
    "predicted_network_contact", # yes / no
    "is_human_sender",
    # --- Company identity ---
    "company_name",
    "company_domain",
    "company_is_company_domain",
    # --- Application matching layer ---
    "predicted_email_type",       # decision / conversation / None
    "predicted_status_change",    # rejected / interviewing / offer / applied / None
    "predicted_would_create_event", # yes / no (would an EmailEvent be created?)
    "predicted_would_match_app",  # yes / no (would it try to match to an application?)
    "predicted_key_sentence",
    # --- Classifier engine used ---
    "classifier_engine",          # openai / anthropic / fallback
    # --- Manual review columns (empty, for analyst) ---
    "review_correct",
    "review_expected_decision",
    "review_expected_classification",
    "review_expected_network_contact",
    "review_expected_status_change",
    "review_reason",
]


# ─── OpenAI classifier ──────────────────────────────────────────────────────

async def classify_email_openai(subject: str, body: str, sender: str, sender_email: str) -> dict:
    """Classify using OpenAI gpt-4o-mini with the same prompt as Haiku."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    truncated_body = body[:4000] if body else ""

    user_prompt = f"""From: {sender} <{sender_email}>
Subject: {subject}

{truncated_body}"""

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=300,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )

    result = json.loads(response.choices[0].message.content)

    valid_categories = {
        "interview_request", "rejection", "offer",
        "action_item", "job_update", "conversation", "not_relevant",
    }
    if result.get("classification") not in valid_categories:
        result["classification"] = "job_update"

    return result


async def classify_with_fallback(subject: str, body: str, sender: str, sender_email: str) -> tuple[dict, str]:
    """Try OpenAI → Anthropic → fallback. Returns (classification_dict, engine_used)."""

    # 1. Try OpenAI
    if os.getenv("OPENAI_API_KEY"):
        try:
            result = await classify_email_openai(subject, body, sender, sender_email)
            return result, "openai"
        except Exception as exc:
            logger.warning(f"OpenAI failed: {exc}")

    # 2. Try Anthropic
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            from backend.services.email_classifier import classify_email
            result = await classify_email(subject, body, sender, sender_email)
            # Check if it fell back internally
            if result.get("confidence", 0) <= 0.6:
                return result, "fallback"
            return result, "anthropic"
        except Exception as exc:
            logger.warning(f"Anthropic failed: {exc}")

    # 3. Rule-based fallback
    result = _fallback_classify(subject, body, sender_email, sender=sender)
    return result, "fallback"


async def process_message(msg: dict, row_id: int) -> dict | None:
    """Classify a single message and return a CSV row dict."""
    msg_id = msg.get("id", "")
    thread_id = msg.get("threadId", "")
    labels = msg.get("labelIds", [])
    snippet = msg.get("snippet", "")
    headers = msg.get("headers", {})

    from_header = headers.get("From", "")
    subject = headers.get("Subject", "")
    date_str = headers.get("Date", "")

    sender_name, sender_email = extract_sender_parts(from_header)
    body = snippet  # MCP gives snippet, not full payload

    # Build email dict for noise filter
    email_dict = {
        "sender_email": sender_email,
        "sender_name": sender_name,
        "subject": subject,
        "body": body,
    }

    noise = is_obvious_noise_email(email_dict)

    # Classify
    classification, engine = await classify_with_fallback(
        subject=subject,
        body=body,
        sender=sender_name,
        sender_email=sender_email,
    )

    cls = classification.get("classification", "not_relevant")

    # Decision: inbox or filter
    if noise or cls == "not_relevant":
        decision = "filter"
    else:
        decision = "inbox"

    # Network contact check
    is_human = is_likely_person_sender(sender_name, sender_email)
    network_contact = should_create_network_contact(sender_name, sender_email, cls)

    # Company identity
    company_info = get_company_info(sender_email)

    # --- Application matching layer (simulated, no DB) ---
    email_type = CLASSIFICATION_TO_EMAIL_TYPE.get(cls)
    status_change = STATUS_UPDATES.get(cls)
    # Would create EmailEvent if not filtered
    would_create_event = decision == "inbox"
    # Would try to match to application if it's a "decision" type email
    would_match_app = email_type == "decision" and decision == "inbox"

    body_snippet = body[:300].replace("\n", " ").replace("\r", " ") if body else ""

    return {
        "id": row_id,
        "gmail_message_id": msg_id,
        "thread_id": thread_id,
        "gmail_labels": "|".join(labels),
        "sender_name": sender_name,
        "sender_email": sender_email,
        "subject": subject,
        "received_at": date_str,
        "body_snippet": body_snippet,
        "is_obvious_noise": "yes" if noise else "no",
        "predicted_decision": decision,
        "predicted_classification": cls,
        "predicted_confidence": classification.get("confidence", 0.0),
        "predicted_is_automated": "yes" if classification.get("is_automated") else "no",
        "predicted_sender_role": classification.get("sender_role", "unknown"),
        "predicted_action_needed": "yes" if classification.get("action_needed") else "no",
        "predicted_summary": classification.get("summary", ""),
        "predicted_network_contact": "yes" if network_contact else "no",
        "is_human_sender": "yes" if is_human else "no",
        "company_name": company_info.get("company_name", "") or classification.get("company_name", "") or "",
        "company_domain": company_info.get("domain", ""),
        "company_is_company_domain": "yes" if company_info.get("is_company") else "no",
        # Application matching layer
        "predicted_email_type": email_type or "",
        "predicted_status_change": status_change or "",
        "predicted_would_create_event": "yes" if would_create_event else "no",
        "predicted_would_match_app": "yes" if would_match_app else "no",
        "predicted_key_sentence": classification.get("key_sentence", ""),
        "classifier_engine": engine,
        # Empty review columns
        "review_correct": "",
        "review_expected_decision": "",
        "review_expected_classification": "",
        "review_expected_network_contact": "",
        "review_expected_status_change": "",
        "review_reason": "",
    }


async def main():
    parser = argparse.ArgumentParser(description="Classify real Gmail emails for audit")
    parser.add_argument("--input", type=str, default="audit/raw_emails_batch1.json", help="Input JSON from MCP export")
    parser.add_argument("--output", type=str, default="audit/real_email_audit.csv", help="Output CSV path")
    parser.add_argument("--batch-delay", type=float, default=0.2, help="Delay between LLM calls (default: 0.2s)")
    args = parser.parse_args()

    # Show which engine will be used
    if os.getenv("OPENAI_API_KEY"):
        logger.info("Using OpenAI gpt-4o-mini as classifier")
    elif os.getenv("ANTHROPIC_API_KEY"):
        logger.info("Using Anthropic Haiku as classifier")
    else:
        logger.info("No LLM API key found — using rule-based fallback only")

    # Load raw emails
    with open(args.input) as f:
        data = json.load(f)

    messages = data.get("messages", [])
    logger.info(f"Loaded {len(messages)} emails from {args.input}")

    if not messages:
        logger.info("No messages found. Exiting.")
        return

    # Process each message through classifier
    rows = []
    for i, msg in enumerate(messages):
        row = await process_message(msg, row_id=i + 1)
        if row:
            rows.append(row)

        if (i + 1) % 10 == 0:
            logger.info(f"  Classified {i + 1}/{len(messages)} emails...")

        await asyncio.sleep(args.batch_delay)

    # Write CSV
    output_path = args.output
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    logger.info(f"\nWrote {len(rows)} rows to {output_path}")

    # Quick stats
    decisions = {}
    classifications = {}
    engines = {}
    status_changes = {}
    for r in rows:
        d = r["predicted_decision"]
        c = r["predicted_classification"]
        e = r["classifier_engine"]
        s = r["predicted_status_change"]
        decisions[d] = decisions.get(d, 0) + 1
        classifications[c] = classifications.get(c, 0) + 1
        engines[e] = engines.get(e, 0) + 1
        if s:
            status_changes[s] = status_changes.get(s, 0) + 1

    logger.info("--- Decision breakdown ---")
    for k, v in sorted(decisions.items()):
        logger.info(f"  {k}: {v}")

    logger.info("--- Classification breakdown ---")
    for k, v in sorted(classifications.items()):
        logger.info(f"  {k}: {v}")

    logger.info("--- Classifier engine ---")
    for k, v in sorted(engines.items()):
        logger.info(f"  {k}: {v}")

    logger.info("--- Status changes that would trigger ---")
    for k, v in sorted(status_changes.items()):
        logger.info(f"  {k}: {v}")

    network_contacts = sum(1 for r in rows if r["predicted_network_contact"] == "yes")
    noise_count = sum(1 for r in rows if r["is_obvious_noise"] == "yes")
    events_created = sum(1 for r in rows if r["predicted_would_create_event"] == "yes")
    app_matches = sum(1 for r in rows if r["predicted_would_match_app"] == "yes")
    logger.info(f"Network contacts identified: {network_contacts}")
    logger.info(f"Pre-filter noise caught: {noise_count}")
    logger.info(f"EmailEvents that would be created: {events_created}")
    logger.info(f"Emails that would try app matching: {app_matches}")


if __name__ == "__main__":
    asyncio.run(main())
