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
    return _fallback_classify(subject, body, sender_email)


def _fallback_classify(subject: str, body: str, sender_email: str) -> dict:
    """Rule-based fallback when LLM is unavailable."""
    lower_subject = subject.lower()
    lower_body = (body[:500] if body else "").lower()
    combined = f"{lower_subject} {lower_body}"

    classification = "job_update"
    action_needed = False

    if any(w in lower_subject for w in ["interview", "schedule", "phone screen", "onsite", "technical"]):
        classification = "interview_request"
        action_needed = True
    elif any(w in combined for w in ["unfortunately", "not moving forward", "other candidates", "regret to inform", "decided not to"]):
        classification = "rejection"
    elif any(w in lower_subject for w in ["offer", "compensation", "package", "offer letter"]):
        classification = "offer"
        action_needed = True
    elif any(w in lower_subject for w in ["action required", "next steps", "complete", "assessment", "please submit"]):
        classification = "action_item"
        action_needed = True
    elif any(w in sender_email.lower() for w in ["noreply", "no-reply", "notifications", "mailer"]):
        classification = "job_update"
    elif "@" in sender_email and not any(w in sender_email.lower() for w in ["noreply", "no-reply", "notifications"]):
        # Personal email from someone — likely a conversation
        classification = "conversation"

    return {
        "classification": classification,
        "confidence": 0.3,
        "company_name": None,
        "sender_role": "unknown",
        "key_sentence": subject,
        "summary": f"Email from {sender_email}: {subject}",
        "action_needed": action_needed,
        "is_automated": "noreply" in sender_email.lower() or "no-reply" in sender_email.lower(),
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
