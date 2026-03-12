import re

ATS_DOMAINS = {
    "myworkday.com", "greenhouse.io", "lever.co", "ashbyhq.com",
    "icims.com", "jobvite.com", "smartrecruiters.com", "taleo.net",
}

NON_JOB_NOTIFICATION_DOMAINS = {
    "github.com",
    "notifications.github.com",
    "noreply.github.com",
    "railway.app",
    "railway.com",
    "vercel.com",
    "mailer.vercel.com",
    "linear.app",
}

AUTOMATED_LOCAL_PART_HINTS = {
    "noreply", "no-reply", "no_reply", "notifications", "notification",
    "mailer", "mailers", "updates", "update", "hello", "support", "info",
    "news", "newsletter", "digest", "community", "events", "accounts",
    "security", "billing", "receipts", "alerts", "team", "careers", "jobs",
}

RECRUITING_HINTS = {
    "application", "applying", "applied", "candidate", "candidacy",
    "hiring", "interview", "interviewer", "recruiter",
    "recruiting", "talent", "onsite", "phone screen", "screening call",
    "assessment", "take-home", "take home", "coding challenge", "offer",
    "offer letter", "compensation", "availability", "background check",
    "references", "position", "role", "job opportunity", "opening",
    "under review", "application update", "next steps", "not moving forward",
    "not selected", "position has been filled", "we received your application",
}

PROMOTIONAL_OR_SYSTEM_HINTS = {
    "build failed", "deployment", "release notes", "changelog", "newsletter",
    "weekly digest", "digest", "receipt", "invoice", "billing", "security alert",
    "verify your email", "product update", "coming soon", "unlocks", "rewards",
    "spring break", "sale", "discount", "webinar", "community event",
    "follow", "commented", "pull request", "repository", "issue assigned",
    "failed production deployment", "first-year standard .com pricing",
    "practical guide is coming soon", "take control of your career in the ai age",
    "your new fico", "welcome to railway", "view build logs",
}


def extract_domain(email_address: str) -> str:
    """Extract domain from email address like 'user@domain.com'."""
    match = re.search(r"@([\w.-]+)", email_address or "")
    return match.group(1).lower() if match else ""


def extract_local_part(email_address: str) -> str:
    match = re.search(r"([^@]+)@", email_address or "")
    return match.group(1).lower() if match else ""


def _normalize_text(*parts: str) -> str:
    return " ".join((part or "").strip().lower() for part in parts if part)


def has_job_signal(text: str) -> bool:
    normalized = (text or "").lower()
    return any(keyword in normalized for keyword in RECRUITING_HINTS)


def has_recruiting_sender_signal(sender_name: str, sender_email: str) -> bool:
    normalized = _normalize_text(sender_name, sender_email)
    return any(keyword in normalized for keyword in {"recruiter", "recruiting", "talent", "hiring", "sourcer"})


def is_obvious_noise_email(email: dict) -> bool:
    sender_email = email.get("sender_email") or email.get("sender") or ""
    sender_name = email.get("sender_name") or email.get("sender_display") or ""
    sender_domain = extract_domain(sender_email)
    sender_local = extract_local_part(sender_email)
    combined = _normalize_text(email.get("subject", ""), email.get("body", ""), sender_name)

    if sender_domain in ATS_DOMAINS:
        return False

    if sender_domain in NON_JOB_NOTIFICATION_DOMAINS:
        return True

    if has_job_signal(combined):
        return False

    if any(hint in sender_local for hint in AUTOMATED_LOCAL_PART_HINTS):
        return True

    if any(hint in combined for hint in PROMOTIONAL_OR_SYSTEM_HINTS):
        return True

    return False


def should_classify(email: dict, company_domains: set[str]) -> bool:
    """Determine if an email merits downstream job-related classification."""
    sender_email = email.get("sender_email") or email.get("sender") or ""
    sender_name = email.get("sender_name") or email.get("sender_display") or ""
    sender_domain = extract_domain(sender_email)
    combined = _normalize_text(email.get("subject", ""), email.get("body", ""), sender_name)

    if sender_domain in ATS_DOMAINS:
        return True

    if is_obvious_noise_email(email):
        return False

    if sender_domain in company_domains:
        return True

    if has_job_signal(combined):
        return True

    if has_recruiting_sender_signal(sender_name, sender_email):
        return True

    return False
