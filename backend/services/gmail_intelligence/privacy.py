"""Privacy minimization helpers for Gmail classifier LLM adjudication."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from backend.services.gmail_intelligence.types import NormalizedEmail, RedactedEmail

URL_RE = re.compile(r"https?://[^\s)>\]\"']+", re.IGNORECASE)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]\d{3}[-.\s]\d{4}\b")
ADDRESS_RE = re.compile(
    r"\b\d{1,6}\s+[A-Z0-9][A-Z0-9.'\- ]{1,80}\s+"
    r"(?:street|st\.?|avenue|ave\.?|road|rd\.?|boulevard|blvd\.?|lane|ln\.?|drive|dr\.?|court|ct\.?|way|parkway|pkwy|circle|cir\.?)"
    r"(?:,\s*[A-Z][A-Z .'\-]{1,60})?(?:,\s*[A-Z]{2}\s*\d{5}(?:-\d{4})?)?",
    re.IGNORECASE,
)
PRIVATE_QUERY_RE = re.compile(
    r"(token|auth|session|jwt|candidate|candidateid|applicationid|profileid|magic|invite)",
    re.IGNORECASE,
)
SCHEDULER_HOST_RE = re.compile(r"(calendly|scheduler|schedule|interview)", re.IGNORECASE)
SIGNATURE_START_RE = re.compile(
    r"(?im)^\s*(?:--\s*|best,?|best regards,?|regards,?|thanks,?|thank you,?|sincerely,?)\s*$"
)
QUOTED_REPLY_RE = re.compile(r"(?im)^\s*(?:on .+ wrote:|from:\s.+|sent:\s.+|subject:\s.+|>\s?.*)$")


def minimize_email_body_for_llm(body: str, *, max_chars: int = 3000) -> str:
    """Keep only classifier-relevant body text before redaction.

    The Gmail classifier needs message intent, not signatures, quoted thread
    history, or long footer text. This is intentionally conservative: if a
    signature/quote boundary is present, everything after that boundary is
    dropped before the prompt is built.
    """
    text = body or ""
    signature_match = SIGNATURE_START_RE.search(text)
    if signature_match:
        text = text[: signature_match.start()]

    lines: list[str] = []
    for line in text.splitlines():
        if QUOTED_REPLY_RE.match(line):
            break
        lines.append(line)

    minimized = "\n".join(lines).strip()
    return minimized[:max_chars]


def _url_placeholder(url: str) -> str:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return "[URL]"
    host = (parsed.hostname or "").lower()
    query = parsed.query or ""
    path = parsed.path or ""
    if PRIVATE_QUERY_RE.search(query) or PRIVATE_QUERY_RE.search(path):
        return "[PRIVATE_APPLICATION_URL]"
    if SCHEDULER_HOST_RE.search(host) or SCHEDULER_HOST_RE.search(path):
        return "[SCHEDULER_URL]"
    if any(provider in host for provider in {"greenhouse.io", "lever.co", "ashbyhq.com", "workdayjobs.com", "myworkdayjobs.com"}):
        return "[PUBLIC_ATS_URL]"
    return "[URL]"


def redact_text_for_llm(text: str) -> tuple[str, dict[str, int], list[str]]:
    counts: dict[str, int] = {}
    reasons: list[str] = []

    def _replace_url(match: re.Match[str]) -> str:
        placeholder = _url_placeholder(match.group(0))
        counts[placeholder.strip("[]").lower()] = counts.get(placeholder.strip("[]").lower(), 0) + 1
        reasons.append(f"redacted_{placeholder.strip('[]').lower()}")
        return placeholder

    redacted = URL_RE.sub(_replace_url, text or "")
    redacted, address_count = ADDRESS_RE.subn("[ADDRESS]", redacted)
    if address_count:
        counts["address"] = counts.get("address", 0) + address_count
        reasons.append("redacted_address")
    redacted, email_count = EMAIL_RE.subn("[EMAIL]", redacted)
    if email_count:
        counts["email"] = counts.get("email", 0) + email_count
        reasons.append("redacted_email")
    redacted, phone_count = PHONE_RE.subn("[PHONE]", redacted)
    if phone_count:
        counts["phone"] = counts.get("phone", 0) + phone_count
        reasons.append("redacted_phone")
    return redacted, counts, sorted(set(reasons))


def redact_email_for_llm(normalized: NormalizedEmail) -> RedactedEmail:
    subject, subject_counts, subject_reasons = redact_text_for_llm(normalized.subject)
    minimized_body = minimize_email_body_for_llm(normalized.body)
    body, body_counts, body_reasons = redact_text_for_llm(minimized_body)
    sender, sender_counts, sender_reasons = redact_text_for_llm(normalized.sender)
    if sender and sender != "[EMAIL]":
        sender = "[SENDER]"
        sender_counts["sender_name"] = sender_counts.get("sender_name", 0) + 1
        sender_reasons.append("redacted_sender_name")
    sender_email, sender_email_counts, sender_email_reasons = redact_text_for_llm(normalized.sender_email)
    counts: dict[str, int] = {}
    for part in [subject_counts, body_counts, sender_counts, sender_email_counts]:
        for key, value in part.items():
            counts[key] = counts.get(key, 0) + value
    reasons = sorted(set(subject_reasons + body_reasons + sender_reasons + sender_email_reasons))
    return RedactedEmail(
        subject=subject,
        body=body,
        sender=sender,
        sender_email=sender_email,
        redaction_counts=counts,
        redaction_reasons=reasons,
    )
