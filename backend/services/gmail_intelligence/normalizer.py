"""Local text normalization for Gmail classifier features."""

from __future__ import annotations

import html
import re

from backend.services.gmail_intelligence.types import EmailCandidate, NormalizedEmail

TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
LINEBREAK_TAG_RE = re.compile(r"(?i)<\s*br\s*/?\s*>|</\s*(?:p|div|li|tr|h[1-6])\s*>")
REPLY_PREFIX_RE = re.compile(r"^\s*(re|fw|fwd)\s*:\s*", re.IGNORECASE)


def strip_html(text: str, *, preserve_lines: bool = False) -> str:
    decoded = html.unescape(text or "")
    if preserve_lines:
        decoded = LINEBREAK_TAG_RE.sub("\n", decoded)
    without_tags = TAG_RE.sub(" ", decoded)
    if preserve_lines:
        lines = [WHITESPACE_RE.sub(" ", line).strip() for line in without_tags.splitlines()]
        return "\n".join(line for line in lines if line).strip()
    return WHITESPACE_RE.sub(" ", without_tags).strip()


def normalize_for_matching(text: str) -> str:
    stripped = strip_html(text)
    stripped = REPLY_PREFIX_RE.sub("", stripped)
    return WHITESPACE_RE.sub(" ", stripped.lower()).strip()


def normalize_email(candidate: EmailCandidate) -> NormalizedEmail:
    subject = strip_html(candidate.subject)
    body = strip_html(candidate.body, preserve_lines=True)
    sender = strip_html(candidate.sender)
    sender_email = (candidate.sender_email or "").strip().lower()
    subject_norm = normalize_for_matching(subject)
    body_norm = normalize_for_matching(body[:5000])
    sender_norm = normalize_for_matching(sender)
    combined_norm = WHITESPACE_RE.sub(" ", f"{subject_norm} {body_norm} {sender_norm} {sender_email}".strip())
    return NormalizedEmail(
        subject=subject,
        body=body,
        sender=sender,
        sender_email=sender_email,
        subject_norm=subject_norm,
        body_norm=body_norm,
        sender_norm=sender_norm,
        combined_norm=combined_norm,
    )
