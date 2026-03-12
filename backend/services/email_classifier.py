"""Lightweight LLM email classifier using Claude Haiku.

Every email from Gmail sync passes through this classifier.
Categories:
  - job_update: application confirmation, status change, under review
  - interview_request: interview scheduling, phone screen, onsite
  - rejection: rejection notice
  - offer: job offer, compensation package
  - action_item: assessment, form to complete, next steps requiring action
  - conversation: back-and-forth with a person (recruiter, hiring manager)
  - not_relevant: marketing, newsletters, product updates, unrelated
"""

import asyncio
import json
import logging
import os

import anthropic

from backend.services.email_filter import (
    ATS_DOMAINS,
    AUTOMATED_LOCAL_PART_HINTS,
    NON_JOB_NOTIFICATION_DOMAINS,
    extract_domain,
    extract_local_part,
    has_job_signal,
    has_recruiting_sender_signal,
    is_obvious_noise_email,
)
from backend.utils.retry import with_retry

logger = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

CLASSIFIER_MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You are an email classifier for a job search tracking application.
Classify the email into exactly ONE category and extract key metadata.

Categories:
- interview_request: Scheduling an interview, phone screen, onsite, technical assessment invite
- rejection: Application rejected, not moving forward, position filled
- offer: Job offer, compensation details, offer letter
- action_item: Requires user action — complete assessment, fill form, provide references, sign document
- job_update: Application received/confirmed, status update, under review, moved to next stage
- conversation: Personal message from recruiter/hiring manager, networking, informational
- not_relevant: Marketing, newsletters, product updates, promotions, account notifications, unrelated to job search

Important exclusions:
- Developer tooling notifications such as GitHub, Railway, Vercel, Linear, billing emails, deployment alerts, repository updates, account security notices, invoices, and newsletters are NOT job search emails.
- Product updates from a company domain are still not_relevant unless they directly concern an active application, interview, or recruiting conversation.
- Nuanced rejection phrasing such as "we will not be moving forward", "not selected", "position has been filled", "have not been accepted", and "pursuing other candidates" should all classify as rejection.
- Recruiter or hiring-manager replies like "great speaking with you", "following up", and "can you chat this week" should classify as conversation when they are from a human sender.
- Promotional recruiting-adjacent content from LinkedIn, alumni groups, newsletters, community events, and vendor marketing is still not_relevant unless it is directly tied to an active application or interview process.
- Only treat a sender as human if it looks like a real individual or direct recruiter. Team aliases, no-reply mailboxes, newsletters, and system notifications are automated.

Return ONLY valid JSON with these fields:
{
  "classification": "<one of the categories above>",
  "confidence": <0.0-1.0>,
  "company_name": "<extracted company name or null>",
  "sender_role": "<recruiter/hiring_manager/hr/automated/unknown>",
  "key_sentence": "<the most important sentence from the email>",
  "summary": "<1-2 sentence summary>",
  "action_needed": <true/false>,
  "is_automated": <true if from ATS/no-reply, false if from a person>
}"""


async def classify_email(
    subject: str,
    body: str,
    sender: str,
    sender_email: str = "",
) -> dict:
    """Classify an email using Claude Haiku.

    Args:
        subject: Email subject line
        body: Email body text (plain text, max ~4000 chars sent)
        sender: Sender display name
        sender_email: Sender email address

    Returns:
        Classification dict with category, confidence, metadata
    """
    # Truncate body to keep token usage low
    truncated_body = body[:4000] if body else ""

    user_prompt = f"""From: {sender} <{sender_email}>
Subject: {subject}

{truncated_body}"""

    for attempt in range(3):
        try:
            response = await with_retry(
                client.messages.create,
                model=CLASSIFIER_MODEL,
                max_tokens=300,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            result = json.loads(response.content[0].text)

            # Validate classification is a known category
            valid_categories = {
                "interview_request", "rejection", "offer",
                "action_item", "job_update", "conversation", "not_relevant",
            }
            if result.get("classification") not in valid_categories:
                result["classification"] = "job_update"

            return result

        except anthropic.RateLimitError:
            logger.warning(f"Rate limited on attempt {attempt + 1}")
            await asyncio.sleep(30 * (attempt + 1))
        except anthropic.APIStatusError as e:
            if e.status_code == 529:  # overloaded
                await asyncio.sleep(2 ** attempt)
            elif attempt == 2:
                logger.error(f"Classifier API error: {e}")
                break
        except json.JSONDecodeError:
            logger.error(f"Classifier JSON parse failed on attempt {attempt + 1}")
            if attempt == 2:
                break
        except Exception as e:
            logger.error(f"Classifier unexpected error: {e}")
            if attempt == 2:
                break

    # Fallback: basic keyword classification
    return _fallback_classify(subject, body, sender_email, sender=sender)


REJECTION_PHRASES = {
    "unfortunately", "not moving forward", "not move forward", "regret to inform",
    "other candidates", "another candidate", "pursue other candidates",
    "decided not to proceed", "decided not to move forward", "not selected",
    "have not been selected", "have not been accepted", "not accepted",
    "position has been filled", "role has been filled", "filled the role",
    "no longer under consideration", "unable to offer", "won't be advancing",
    "will not be advancing", "were not chosen", "your application was unsuccessful",
    "cannot move ahead", "cannot move forward",
}

INTERVIEW_PHRASES = {
    "interview", "phone screen", "screening call", "onsite", "virtual onsite",
    "panel interview", "technical interview", "final round", "final interview",
    "availability", "calendly", "select a time", "schedule time", "meet with",
    "interview loop", "hiring manager chat",
}

OFFER_PHRASES = {
    "offer letter", "extend an offer", "pleased to offer", "excited to offer",
    "written offer", "compensation package", "offer package", "base salary",
    "equity grant", "benefits package", "sign your offer",
}

ACTION_REQUIRED_PHRASES = {
    "action required", "complete assessment", "coding assessment", "coding challenge",
    "take-home", "take home", "submit references", "background check",
    "complete the form", "please submit", "confirm availability", "pick a time",
    "schedule here", "book time", "complete your application", "next steps",
    "finish your application",
}

JOB_UPDATE_PHRASES = {
    "application received", "thank you for applying", "under review",
    "reviewing your application", "application update", "status update",
    "moving to the next stage", "move to the next stage", "next stage",
    "next round", "we received your application", "application status",
    "candidate portal", "thank you for your interest", "decision has been made",
}

NON_PERSON_SENDER_HINTS = {
    "team", "support", "help", "community", "events", "newsletter",
    "notifications", "notification", "noreply", "no-reply", "mailer",
    "info", "careers", "jobs", "accounts", "security", "billing", "alerts",
    "talent team", "recruiting team", "hiring team", "customer success",
}


def infer_sender_role(sender: str, sender_email: str, is_human: bool) -> str:
    normalized = f"{(sender or '').lower()} {(sender_email or '').lower()}"
    if not is_human:
        return "automated"
    if "hiring manager" in normalized:
        return "hiring_manager"
    if any(token in normalized for token in {"recruiter", "recruiting", "talent", "sourcer"}):
        return "recruiter"
    if any(token in normalized for token in {"hr", "human resources", "people ops"}):
        return "hr"
    return "unknown"


def is_likely_person_sender(sender: str, sender_email: str) -> bool:
    sender_name = (sender or "").strip().lower()
    sender_domain = extract_domain(sender_email)
    sender_local = extract_local_part(sender_email)

    if not sender_email:
        return False
    if sender_domain in NON_JOB_NOTIFICATION_DOMAINS:
        return False
    if any(token in sender_local for token in AUTOMATED_LOCAL_PART_HINTS):
        return False
    if any(token in sender_name for token in NON_PERSON_SENDER_HINTS):
        return False

    if sender_name:
        name_words = [part for part in sender_name.replace(".", " ").split() if part.isalpha()]
        if len(name_words) >= 2:
            return True

    return bool(
        sender_local
        and any(sep in sender_local for sep in {".", "_", "-"})
        and not any(token in sender_local for token in NON_PERSON_SENDER_HINTS)
    ) or bool(sender_local and sender_local.isalpha() and len(sender_local) >= 5)


def should_create_network_contact(sender: str, sender_email: str, classification: str | None = None) -> bool:
    if classification == "not_relevant":
        return False
    return is_likely_person_sender(sender, sender_email)


def _contains_any(combined: str, phrases: set[str]) -> bool:
    return any(phrase in combined for phrase in phrases)


def _fallback_classify(subject: str, body: str, sender_email: str, sender: str = "") -> dict:
    """Rule-based fallback when LLM is unavailable."""
    lower_subject = subject.lower()
    lower_body = (body[:500] if body else "").lower()
    combined = f"{lower_subject} {lower_body}"
    sender_domain = extract_domain(sender_email)
    is_human = is_likely_person_sender(sender, sender_email)

    classification = "not_relevant"
    action_needed = False

    if is_obvious_noise_email({
        "sender": sender_email,
        "sender_email": sender_email,
        "sender_name": sender,
        "subject": subject,
        "body": body,
    }):
        return {
            "classification": "not_relevant",
            "confidence": 0.9,
            "company_name": None,
            "sender_role": "automated",
            "key_sentence": subject,
            "summary": f"Non-job product or account notification from {sender_email}",
            "action_needed": False,
            "is_automated": True,
        }

    if _contains_any(combined, REJECTION_PHRASES):
        classification = "rejection"
    elif _contains_any(combined, OFFER_PHRASES):
        classification = "offer"
        action_needed = True
    elif _contains_any(combined, INTERVIEW_PHRASES):
        classification = "interview_request"
        action_needed = any(token in combined for token in {"availability", "calendly", "select a time", "schedule", "book time"})
    elif _contains_any(combined, ACTION_REQUIRED_PHRASES):
        classification = "action_item"
        action_needed = True
    elif _contains_any(combined, JOB_UPDATE_PHRASES) or sender_domain in ATS_DOMAINS:
        classification = "job_update"
    elif is_human and (has_job_signal(combined) or has_recruiting_sender_signal(sender, sender_email)):
        classification = "conversation"

    return {
        "classification": classification,
        "confidence": 0.45 if classification != "not_relevant" else 0.6,
        "company_name": None,
        "sender_role": infer_sender_role(sender, sender_email, is_human),
        "key_sentence": subject,
        "summary": f"Email from {sender_email}: {subject}",
        "action_needed": action_needed,
        "is_automated": not is_human,
    }


# Map classifier categories to the frontend EmailClassification type
CLASSIFICATION_TO_FRONTEND = {
    "interview_request": "interview",
    "rejection": "rejection",
    "offer": "action_item",
    "action_item": "action_item",
    "job_update": "update",
    "conversation": "update",
    "not_relevant": "update",
}

# Map classifier categories to email_type
CLASSIFICATION_TO_EMAIL_TYPE = {
    "interview_request": "decision",
    "rejection": "decision",
    "offer": "decision",
    "action_item": "decision",
    "job_update": "decision",
    "conversation": "conversation",
    "not_relevant": None,
}

# Map classifier categories to color codes for UI
CLASSIFICATION_TO_COLOR = {
    "interview_request": "green",
    "rejection": "red",
    "offer": "gold",
    "action_item": "orange",
    "job_update": "blue",
    "conversation": "purple",
    "not_relevant": "gray",
}
