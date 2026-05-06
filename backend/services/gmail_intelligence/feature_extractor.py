"""Feature extraction for hybrid Gmail classification."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from backend.services.email_filter import (
    ATS_DOMAINS,
    AUTOMATED_LOCAL_PART_HINTS,
    NON_JOB_NOTIFICATION_DOMAINS,
    PROMOTIONAL_OR_SYSTEM_HINTS,
    RECRUITING_HINTS,
    extract_domain,
    extract_local_part,
    has_job_signal,
    has_recruiting_sender_signal,
)
from backend.services.gmail_intelligence.types import EmailCandidate, EmailFeatures, NormalizedEmail

URL_RE = re.compile(r"https?://[^\s)>\]\"']+", re.IGNORECASE)

CONVERSATION_PHRASES = {
    "great speaking with you",
    "great talking with you",
    "following up",
    "continue the conversation",
    "can you chat",
    "can you send availability",
    "thanks for speaking",
    "nice speaking with you",
    "touch base",
}

REJECTION_PHRASES = {
    "unfortunately",
    "not moving forward",
    "not be moving forward",
    "will not be moving forward",
    "regret to inform",
    "other candidates",
    "another candidate",
    "pursue other candidates",
    "decided not to proceed",
    "decided not to move forward",
    "not selected",
    "have not been selected",
    "not accepted",
    "position has been filled",
    "role has been filled",
    "no longer under consideration",
    "unable to offer",
    "will not be advancing",
    "your application was unsuccessful",
}

INTERVIEW_PHRASES = {
    "interview",
    "phone screen",
    "screening call",
    "onsite",
    "virtual onsite",
    "panel interview",
    "technical interview",
    "final round",
    "final interview",
    "select a time",
    "choose a time",
    "schedule time",
    "meet with",
    "interview loop",
    "hiring manager chat",
}

OFFER_PHRASES = {
    "offer letter",
    "extend an offer",
    "pleased to offer",
    "excited to offer",
    "written offer",
    "compensation package",
    "offer package",
    "base salary",
    "equity grant",
    "benefits package",
    "sign your offer",
}

ACTION_REQUIRED_PHRASES = {
    "action required",
    "complete assessment",
    "complete your assessment",
    "coding assessment",
    "coding challenge",
    "take-home",
    "take home",
    "submit references",
    "background check",
    "complete the form",
    "please submit",
    "confirm availability",
    "pick a time",
    "schedule here",
    "book time",
    "complete your application",
    "next steps",
    "next step",
    "finish your application",
}

JOB_UPDATE_PHRASES = {
    "application received",
    "thank you for applying",
    "under review",
    "reviewing your application",
    "application update",
    "status update",
    "moving to the next stage",
    "move to the next stage",
    "next stage",
    "next round",
    "we received your application",
    "application status",
    "candidate portal",
    "thank you for your interest",
    "decision has been made",
}

NON_PERSON_SENDER_HINTS = {
    "team",
    "support",
    "help",
    "community",
    "events",
    "newsletter",
    "notifications",
    "notification",
    "noreply",
    "no-reply",
    "mailer",
    "info",
    "careers",
    "jobs",
    "accounts",
    "security",
    "billing",
    "alerts",
    "talent team",
    "recruiting team",
    "hiring team",
    "customer success",
}

SCHEDULER_PHRASES = {
    "calendly",
    "book time",
    "pick a time",
    "select a time",
    "choose a time",
    "schedule here",
}

PRIVATE_URL_TOKENS = {
    "token",
    "auth",
    "session",
    "jwt",
    "candidate",
    "candidateid",
    "applicationid",
    "profileid",
    "magic",
    "invite",
}


def _is_likely_person_sender(sender: str, sender_email: str, sender_domain: str, sender_local: str) -> bool:
    sender_name = (sender or "").strip().lower()
    if not sender_email:
        return False
    if _domain_matches(sender_domain, NON_JOB_NOTIFICATION_DOMAINS):
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


def _domain_matches(domain: str, candidates: set[str]) -> bool:
    domain = (domain or "").lower()
    return any(domain == item or domain.endswith(f".{item}") for item in candidates)


def _phrase_hits(text: str, phrases: set[str]) -> list[str]:
    return sorted(phrase for phrase in phrases if phrase in text)


def _extract_url_feature_types(urls: list[str]) -> list[str]:
    features: set[str] = set()
    for raw_url in urls:
        try:
            parsed = urlsplit(raw_url)
        except ValueError:
            features.add("invalid_url")
            continue
        host = (parsed.hostname or "").lower()
        path = (parsed.path or "").lower()
        query = (parsed.query or "").lower()
        if _domain_matches(host, ATS_DOMAINS) or any(provider in host for provider in {"greenhouse.io", "lever.co", "ashbyhq.com", "workdayjobs.com", "myworkdayjobs.com"}):
            features.add("ats_url")
        if any(token in host or token in path for token in {"calendly", "scheduler", "schedule", "interview"}):
            features.add("scheduler_url")
        if any(token in query or token in path for token in PRIVATE_URL_TOKENS):
            features.add("private_application_url")
    return sorted(features)


def extract_email_features(candidate: EmailCandidate, normalized: NormalizedEmail) -> EmailFeatures:
    sender_domain = extract_domain(normalized.sender_email)
    sender_local = extract_local_part(normalized.sender_email)
    urls = URL_RE.findall(" ".join([normalized.subject, normalized.body, *candidate.raw_candidate_urls]))
    url_feature_types = _extract_url_feature_types(urls)
    combined = normalized.combined_norm
    category_hits: dict[str, list[str]] = {
        "rejection": _phrase_hits(combined, REJECTION_PHRASES),
        "offer": _phrase_hits(combined, OFFER_PHRASES),
        "interview_request": _phrase_hits(combined, INTERVIEW_PHRASES | SCHEDULER_PHRASES),
        "action_item": _phrase_hits(combined, ACTION_REQUIRED_PHRASES | {"assessment", "complete your assessment", "next step"}),
        "job_update": _phrase_hits(combined, JOB_UPDATE_PHRASES),
        "conversation": _phrase_hits(combined, CONVERSATION_PHRASES),
        "not_relevant": _phrase_hits(combined, PROMOTIONAL_OR_SYSTEM_HINTS),
    }

    is_ats = _domain_matches(sender_domain, ATS_DOMAINS)
    is_noise_domain = _domain_matches(sender_domain, NON_JOB_NOTIFICATION_DOMAINS)
    is_known_company = sender_domain in candidate.user_company_domains
    is_person = _is_likely_person_sender(normalized.sender, normalized.sender_email, sender_domain, sender_local)
    recruiting_sender = has_recruiting_sender_signal(normalized.sender, normalized.sender_email)
    job_signal = has_job_signal(combined) or bool(url_feature_types and "ats_url" in url_feature_types)
    has_scheduler_url = "scheduler_url" in url_feature_types
    has_private_url_signal = "private_application_url" in url_feature_types

    matched_features: list[str] = []
    if is_ats:
        matched_features.append("sender_domain_is_ats")
    if is_known_company:
        matched_features.append("sender_domain_matches_user_company")
    if is_noise_domain:
        matched_features.append("sender_domain_is_noise")
    if any(hint in sender_local for hint in AUTOMATED_LOCAL_PART_HINTS):
        matched_features.append("sender_local_part_is_automated")
    if is_person:
        matched_features.append("sender_looks_like_person")
    if recruiting_sender:
        matched_features.append("sender_has_recruiting_signal")
    if job_signal:
        matched_features.append("text_has_job_signal")
    if has_scheduler_url:
        matched_features.append("url_has_scheduler_signal")
    if has_private_url_signal:
        matched_features.append("url_has_private_application_signal")
    for category, hits in category_hits.items():
        if hits:
            matched_features.append(f"{category}_phrase:{hits[0]}")

    return EmailFeatures(
        sender_domain=sender_domain,
        sender_local_part=sender_local,
        is_ats_domain=is_ats,
        is_known_company_domain=is_known_company,
        is_noise_domain=is_noise_domain,
        is_likely_person=is_person,
        has_recruiting_sender_signal=recruiting_sender,
        has_job_signal=job_signal,
        has_scheduler_url=has_scheduler_url,
        has_private_url_signal=has_private_url_signal,
        matched_features=matched_features,
        category_feature_hits=category_hits,
        url_feature_types=url_feature_types,
    )
