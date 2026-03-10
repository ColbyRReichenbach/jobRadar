import re

ATS_DOMAINS = {
    "myworkday.com", "greenhouse.io", "lever.co", "ashbyhq.com",
    "icims.com", "jobvite.com", "smartrecruiters.com", "taleo.net",
}

JOB_KEYWORDS = {
    "application", "position", "role", "candidate", "interview",
    "offer", "moving forward", "unfortunately", "thank you for your interest",
    "next steps", "assessment", "decision",
}


def extract_domain(email_address: str) -> str:
    """Extract domain from email address like 'user@domain.com'."""
    match = re.search(r"@([\w.-]+)", email_address or "")
    return match.group(1).lower() if match else ""


def should_classify(email: dict, company_domains: set[str]) -> bool:
    """Determine if an email should be sent to Claude for classification.

    Returns True if:
    - Sender domain matches a known ATS platform, OR
    - Sender domain matches a company domain AND subject contains a job keyword
    """
    sender_domain = extract_domain(email.get("sender", ""))

    if sender_domain in ATS_DOMAINS:
        return True

    if sender_domain in company_domains:
        subject_lower = (email.get("subject", "")).lower()
        if any(kw in subject_lower for kw in JOB_KEYWORDS):
            return True

    return False
