"""Lightweight LLM email classifier using shared AI orchestration.

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

import logging

from backend.services import ai_orchestrator
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

logger = logging.getLogger(__name__)

CLASSIFIER_TASK = ai_orchestrator.get_task("email_classifier")
CLASSIFIER_MODEL = CLASSIFIER_TASK.model
SYSTEM_PROMPT = CLASSIFIER_TASK.system_prompt or ""
VALID_CATEGORIES = {
    "interview_request",
    "rejection",
    "offer",
    "action_item",
    "job_update",
    "conversation",
    "not_relevant",
}
VALID_SENDER_ROLES = {"recruiter", "hiring_manager", "hr", "automated", "unknown"}


async def classify_email(
    subject: str,
    body: str,
    sender: str,
    sender_email: str = "",
    ai_enabled: bool = True,
) -> dict:
    """Classify an email using GPT-4o-mini.

    Args:
        subject: Email subject line
        body: Email body text (plain text, max ~4000 chars sent)
        sender: Sender display name
        sender_email: Sender email address
        ai_enabled: When False, skip LLM and use rule-based fallback only

    Returns:
        Classification dict with category, confidence, metadata
    """
    if not ai_enabled:
        ai_orchestrator.record_fallback(CLASSIFIER_TASK, "disabled_by_consent", {"surface": "email_classifier"})
        return _fallback_classify(subject, body, sender_email, sender=sender)

    # Truncate body to keep token usage low
    truncated_body = body[:4000] if body else ""

    user_prompt = f"""From: {sender} <{sender_email}>
Subject: {subject}

{truncated_body}"""

    try:
        result = await ai_orchestrator.run_json_task(
            CLASSIFIER_TASK,
            user_prompt,
            metadata={"surface": "email_classifier"},
        )

        normalized_result = _normalize_model_result(result, subject, sender_email, sender)
        if normalized_result is None:
            ai_orchestrator.record_fallback(CLASSIFIER_TASK, "invalid_classification", {"surface": "email_classifier"})
            return _fallback_classify(subject, body, sender_email, sender=sender)
        return normalized_result
    except Exception as e:
        logger.error("Classifier unexpected error: %s", e)
        ai_orchestrator.record_fallback(CLASSIFIER_TASK, "task_failure", {"surface": "email_classifier"})

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


def _as_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    return default


def _as_optional_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _clamp_confidence(value: object, *, default: float = 0.5) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = default
    return max(0.0, min(1.0, confidence))


def _normalize_model_result(
    result: dict,
    subject: str,
    sender_email: str,
    sender: str,
) -> dict | None:
    classification = _as_optional_string(result.get("classification"))
    if classification not in VALID_CATEGORIES:
        logger.warning("Classifier returned invalid classification: %r", classification)
        return None

    is_human = is_likely_person_sender(sender, sender_email)
    default_action_needed = classification in {"offer", "action_item"}
    action_needed = _as_bool(result.get("action_needed"), default=default_action_needed)
    if classification == "not_relevant":
        action_needed = False

    sender_role = _as_optional_string(result.get("sender_role"))
    if sender_role not in VALID_SENDER_ROLES:
        sender_role = infer_sender_role(sender, sender_email, is_human)

    return {
        "classification": classification,
        "confidence": _clamp_confidence(result.get("confidence")),
        "company_name": _as_optional_string(result.get("company_name")),
        "sender_role": sender_role,
        "key_sentence": _as_optional_string(result.get("key_sentence")) or subject,
        "summary": _as_optional_string(result.get("summary")) or f"Email from {sender_email}: {subject}",
        "action_needed": action_needed,
        "is_automated": _as_bool(result.get("is_automated"), default=not is_human),
    }


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
