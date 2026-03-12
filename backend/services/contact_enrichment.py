import re
from typing import Iterable

from backend.models import EmailEvent
from backend.services.company_identity import domain_to_company_name, extract_domain

LINKEDIN_URL_RE = re.compile(r"https?://(?:www\.)?linkedin\.com/[^\s)>\"']+", re.IGNORECASE)
TITLE_LINE_RE = re.compile(
    r"\b(?:senior|sr\.?|staff|principal|lead|head|director|vp|vice president|manager|coordinator|specialist|partner|associate|recruiter|recruiting|sourcer|talent|engineer|designer|product manager|program manager|hr|human resources)\b",
    re.IGNORECASE,
)
AT_TITLE_RE = re.compile(
    r"\b(?P<title>[A-Z][A-Za-z/&,\- ]{2,80}?)\s+(?:at|@)\s+(?P<company>[A-Z][A-Za-z0-9&.\- ]{1,80})\b"
)


def _clean_text(value: str | None) -> str:
    return " ".join((value or "").split()).strip()


def _fallback_name_from_email(email: str) -> str | None:
    if "@" not in email:
        return None
    local = email.split("@", 1)[0]
    local = re.sub(r"[._-]+", " ", local).strip()
    words = [part.capitalize() for part in local.split() if part and not part.isdigit()]
    if len(words) >= 2:
        return " ".join(words[:3])
    return None


def infer_contact_name(display_name: str | None, sender_email: str | None) -> str | None:
    cleaned = _clean_text(display_name)
    if cleaned and "@" not in cleaned and len(cleaned.split()) >= 2:
        return cleaned
    if cleaned and cleaned.lower() not in {"talent team", "recruiting team", "hiring team", "team"}:
        return cleaned
    if sender_email:
        return _fallback_name_from_email(sender_email)
    return None


def infer_linkedin_url(*texts: str | None) -> str | None:
    for text in texts:
        if not text:
            continue
        match = LINKEDIN_URL_RE.search(text)
        if match:
            return match.group(0).rstrip(").,")
    return None


def infer_title(*texts: str | None) -> str | None:
    for text in texts:
        if not text:
            continue
        for raw_line in text.splitlines():
            line = _clean_text(raw_line)
            if not line or len(line) > 120:
                continue
            if TITLE_LINE_RE.search(line) and "http" not in line.lower():
                if any(token in line.lower() for token in {"unsubscribe", "linkedin.com", "www."}):
                    continue
                return line
    return None


def infer_company(sender_email: str | None, explicit_company: str | None, *texts: str | None) -> str | None:
    cleaned_company = _clean_text(explicit_company)
    if cleaned_company:
        return cleaned_company

    for text in texts:
        if not text:
            continue
        match = AT_TITLE_RE.search(text)
        if match:
            company = _clean_text(match.group("company"))
            if company:
                return company

    domain = extract_domain(sender_email or "")
    if domain:
        company_name = domain_to_company_name(domain)
        if company_name:
            return company_name
    return None


def build_inferred_contact(
    sender_name: str | None,
    sender_email: str | None,
    explicit_company: str | None = None,
    texts: Iterable[str | None] = (),
) -> dict:
    text_list = [text for text in texts if text]
    return {
        "name": infer_contact_name(sender_name, sender_email),
        "email": sender_email,
        "title": infer_title(*text_list),
        "linkedin_url": infer_linkedin_url(*text_list),
        "company": infer_company(sender_email, explicit_company, *text_list),
    }


def build_inferred_contact_from_email_event(email: EmailEvent) -> dict:
    return build_inferred_contact(
        sender_name=email.sender,
        sender_email=email.sender_email,
        explicit_company=email.company_name,
        texts=(email.summary, email.key_sentence, email.body, email.snippet, email.subject),
    )
