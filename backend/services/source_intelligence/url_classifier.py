from __future__ import annotations

import base64
import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qsl, unquote, urlparse, urlunparse


PRIVATE_QUERY_KEYS = {
    "token",
    "auth",
    "authorization",
    "session",
    "sessionid",
    "jwt",
    "candidate",
    "candidateid",
    "application",
    "applicationid",
    "profileid",
    "magic",
    "invite",
    "interview",
    "schedule",
}

TRACKING_REDIRECT_PARAMS = {"url", "u", "target", "redirect", "q"}
TRACKING_REDIRECT_HOST_HINTS = (
    "click.",
    "links.",
    "link.",
    "email.",
    "mail.",
    "trk.",
)


@dataclass(frozen=True)
class ClassifiedUrl:
    raw_url: str
    normalized_url: str | None
    hostname: str | None
    link_type: str
    provider_type: str | None
    provider_key: str | None
    contains_private_token: bool
    safe_to_share: bool
    rejection_reason: str | None
    rule_ids: list[str]


class _HrefExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key and key.lower() == "href" and value:
                self.hrefs.append(html.unescape(value))


def _normalize_url(raw_url: str) -> str | None:
    value = html.unescape(raw_url or "").strip()
    value = value.strip(" \t\r\n<>\"'()[]{}")
    value = value.rstrip(".,;:")
    if not value:
        return None
    if value.startswith("//"):
        value = f"https:{value}"
    if not re.match(r"^[a-z][a-z0-9+.-]*://", value, flags=re.I):
        return None

    parsed = urlparse(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.username or parsed.password:
        return None

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]

    path = parsed.path or "/"
    return urlunparse((scheme, netloc, path, "", parsed.query, parsed.fragment))


def _token_like(value: str) -> bool:
    if len(value) < 24:
        return False
    compact = re.sub(r"[-_=:.]", "", value)
    if len(compact) < 24:
        return False
    unique_chars = len(set(compact))
    return unique_chars >= 10 and bool(re.search(r"[A-Za-z]", compact)) and bool(re.search(r"\d", compact))


def _contains_private_query(parsed) -> tuple[bool, list[str]]:
    rule_ids: list[str] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        key_l = key.lower()
        value_l = value.lower()
        if key_l in PRIVATE_QUERY_KEYS or any(indicator in key_l for indicator in PRIVATE_QUERY_KEYS):
            rule_ids.append(f"private_query_param:{key_l}")
        elif _token_like(value):
            rule_ids.append(f"token_like_query_value:{key_l}")
        elif any(indicator in value_l for indicator in ("jwt", "magic-login", "candidateid", "applicationid")):
            rule_ids.append(f"private_query_value:{key_l}")
    fragment_l = (parsed.fragment or "").lower()
    if fragment_l and any(indicator in fragment_l for indicator in PRIVATE_QUERY_KEYS):
        rule_ids.append("private_fragment")
    return bool(rule_ids), rule_ids


def _provider_from_host_path(hostname: str, path: str) -> tuple[str | None, str | None, list[str]]:
    host = hostname.lower()
    parts = [part for part in path.split("/") if part]
    rules: list[str] = []

    if host in {"boards.greenhouse.io", "job-boards.greenhouse.io"} and parts:
        rules.append("provider:greenhouse_board")
        return "greenhouse", parts[0], rules
    if host == "boards-api.greenhouse.io" and len(parts) >= 4 and parts[:3] == ["v1", "boards", parts[2]]:
        rules.append("provider:greenhouse_api")
        return "greenhouse", parts[2], rules
    if host == "jobs.lever.co" and parts:
        rules.append("provider:lever")
        return "lever", parts[0], rules
    if host == "api.lever.co" and len(parts) >= 3 and parts[:2] == ["v0", "postings"]:
        rules.append("provider:lever_api")
        return "lever", parts[2], rules
    if host == "jobs.ashbyhq.com" and parts:
        rules.append("provider:ashby")
        return "ashby", parts[0], rules
    if host == "api.ashbyhq.com" and len(parts) >= 4 and parts[:3] == ["posting-api", "job-board", parts[2]]:
        rules.append("provider:ashby_api")
        return "ashby", parts[2], rules
    if host.endswith(".workable.com") and host not in {"www.workable.com", "apply.workable.com"}:
        rules.append("provider:workable_subdomain")
        return "workable", host.removesuffix(".workable.com"), rules
    if host == "apply.workable.com" and parts:
        rules.append("provider:workable_apply")
        return "workable", parts[0], rules
    if host == "www.workable.com" and len(parts) >= 3 and parts[:2] == ["api", "accounts"]:
        rules.append("provider:workable_api")
        return "workable", parts[2], rules
    if host == "careers.smartrecruiters.com" and parts:
        rules.append("provider:smartrecruiters")
        return "smartrecruiters", parts[0], rules
    if host == "api.smartrecruiters.com" and len(parts) >= 4 and parts[:2] == ["v1", "companies"]:
        rules.append("provider:smartrecruiters_api")
        return "smartrecruiters", parts[2], rules
    if host.endswith(".icims.com") or host == "jobs.icims.com":
        rules.append("provider:icims")
        return "icims", host.split(".")[0], rules
    if re.search(r"\.wd\d+\.myworkdayjobs\.com$", host):
        tenant = host.split(".")[0]
        rules.append("provider:workday")
        return "workday", tenant, rules
    if host == "jobs.myworkdaysite.com" and len(parts) >= 3 and parts[0] == "recruiting":
        rules.append("provider:workday_site")
        return "workday", parts[1], rules

    return None, None, rules


def _looks_like_tracking_redirect(hostname: str, path: str, query: str) -> bool:
    host = hostname.lower()
    if any(host.startswith(prefix) for prefix in TRACKING_REDIRECT_HOST_HINTS):
        return True
    if any(word in host for word in ("sendgrid", "mailgun", "mandrill", "sparkpost", "mailchimp")):
        return True
    if any(word in path.lower() for word in ("click", "redirect", "track")):
        params = {key.lower() for key, _ in parse_qsl(query, keep_blank_values=True)}
        return bool(params & TRACKING_REDIRECT_PARAMS)
    return False


def classify_url(raw_url: str) -> ClassifiedUrl:
    normalized = _normalize_url(raw_url)
    if not normalized:
        return ClassifiedUrl(
            raw_url=raw_url,
            normalized_url=None,
            hostname=None,
            link_type="unknown",
            provider_type=None,
            provider_key=None,
            contains_private_token=False,
            safe_to_share=False,
            rejection_reason="invalid_url",
            rule_ids=["invalid_url"],
        )

    parsed = urlparse(normalized)
    hostname = (parsed.hostname or "").lower()
    path_l = unquote(parsed.path or "").lower()
    provider_type, provider_key, provider_rules = _provider_from_host_path(hostname, parsed.path or "")
    contains_private_token, private_rules = _contains_private_query(parsed)
    rule_ids = [*provider_rules, *private_rules]

    link_type = "unknown"
    rejection_reason = None
    safe_to_share = False

    if parsed.scheme != "https":
        rejection_reason = "non_https"
        rule_ids.append("non_https")
    if _looks_like_tracking_redirect(hostname, parsed.path or "", parsed.query):
        link_type = "tracking_redirect"
        rejection_reason = "tracking_redirect_needs_offline_unwrap"
        rule_ids.append("tracking_redirect")
    elif any(vendor in hostname for vendor in ("hackerrank", "codility", "codesignal")) or re.search(r"/(?:assessment|assessments|test|challenge)(?:/|$)", path_l):
        link_type = "assessment"
        rejection_reason = "assessment_link"
        rule_ids.append("private_assessment_path")
    elif "calendly.com" in hostname or re.search(r"/(?:schedule|scheduling|interview|calendar|book)(?:/|$)", path_l):
        link_type = "interview_scheduler"
        rejection_reason = "scheduler_link"
        rule_ids.append("private_scheduler_path")
    elif "magic" in path_l or "magic" in parsed.query.lower():
        link_type = "magic_login"
        rejection_reason = "magic_login"
        contains_private_token = True
        rule_ids.append("private_magic_login")
    elif "candidate-home" in path_l or re.search(r"/candidate(?:/|$)", path_l):
        link_type = "candidate_home"
        rejection_reason = "candidate_home"
        contains_private_token = True
        rule_ids.append("private_candidate_home")
    elif "greenhouse.io/application" in f"{hostname}{path_l}" or re.search(r"/applications?(?:/|$)", path_l):
        link_type = "application_status"
        rejection_reason = "application_status"
        contains_private_token = True
        rule_ids.append("private_application_path")
    elif contains_private_token:
        link_type = "unknown"
        rejection_reason = "private_token"
    elif provider_type and _is_public_provider_path(provider_type, hostname, path_l):
        link_type = _provider_public_link_type(provider_type, path_l)
        safe_to_share = parsed.scheme == "https"
        if safe_to_share:
            rule_ids.append("safe_public_provider_url")
    elif re.search(r"/(?:careers?|jobs?|positions?|openings?)(?:/|$)", path_l) or re.search(r"(?:^|\.)careers?\.|(?:^|\.)jobs?\.", hostname):
        link_type = "company_career_page"
        safe_to_share = parsed.scheme == "https"
        if safe_to_share:
            rule_ids.append("safe_public_career_url")

    if safe_to_share and contains_private_token:
        safe_to_share = False
        rejection_reason = rejection_reason or "private_token"

    return ClassifiedUrl(
        raw_url=raw_url,
        normalized_url=normalized,
        hostname=hostname,
        link_type=link_type,
        provider_type=provider_type,
        provider_key=provider_key,
        contains_private_token=contains_private_token,
        safe_to_share=safe_to_share,
        rejection_reason=None if safe_to_share else rejection_reason,
        rule_ids=rule_ids or ["classified_unknown"],
    )


def _is_public_provider_path(provider_type: str, hostname: str, path_l: str) -> bool:
    if provider_type == "greenhouse":
        return "/jobs/" in path_l or hostname in {"boards.greenhouse.io", "job-boards.greenhouse.io", "boards-api.greenhouse.io"}
    if provider_type == "lever":
        return hostname in {"jobs.lever.co", "api.lever.co"}
    if provider_type == "ashby":
        return hostname in {"jobs.ashbyhq.com", "api.ashbyhq.com"}
    if provider_type == "workable":
        return "/jobs/" in path_l or re.search(r"/j/[A-Za-z0-9_-]+", path_l, flags=re.I) or "/api/accounts/" in path_l
    if provider_type == "smartrecruiters":
        return hostname in {"careers.smartrecruiters.com", "api.smartrecruiters.com"}
    if provider_type == "workday":
        return "/job/" in path_l or "/jobs" in path_l or "/recruiting/" in path_l
    if provider_type == "icims":
        return "/jobs/" in path_l
    return False


def _provider_public_link_type(provider_type: str, path_l: str) -> str:
    parts = [part for part in path_l.split("/") if part]
    if provider_type in {"lever", "ashby"} and len(parts) >= 2:
        return "public_job_posting"
    if provider_type == "workable" and ("/jobs/" in path_l or (len(parts) >= 3 and parts[1] == "j")):
        return "public_job_posting"
    if provider_type in {"greenhouse", "lever", "ashby", "workday", "workable", "smartrecruiters", "icims"}:
        if "/jobs/" in path_l or "/job/" in path_l or re.search(r"/j/[A-Za-z0-9_-]+", path_l, flags=re.I):
            return "public_job_posting"
        return "ats_job_board"
    return "company_career_page"


def extract_urls_from_text(text: str | None) -> list[str]:
    if not text:
        return []
    decoded = html.unescape(text)
    matches = re.findall(r"https?://[^\s<>\"']+", decoded)
    return [_clean_extracted_url(match) for match in matches if _clean_extracted_url(match)]


def extract_href_urls_from_html(html_text: str | None) -> list[str]:
    if not html_text:
        return []
    parser = _HrefExtractor()
    try:
        parser.feed(html_text)
    except Exception:
        return []
    return [_clean_extracted_url(item) for item in parser.hrefs if _clean_extracted_url(item)]


def _clean_extracted_url(value: str) -> str:
    return html.unescape(value).strip().strip("<>\"'()[]{}").rstrip(".,;:")


def extract_urls_from_gmail_payload(payload: dict) -> list[str]:
    urls: list[str] = []
    plain_text, html_text = _extract_raw_body_parts(payload)
    urls.extend(extract_href_urls_from_html(html_text))
    urls.extend(extract_urls_from_text(html_text))
    urls.extend(extract_urls_from_text(plain_text))
    return _dedupe_preserve_order(urls)


def _extract_raw_body_parts(payload: dict) -> tuple[str, str]:
    plain_text = ""
    html_text = ""
    mime_type = payload.get("mimeType", "")
    parts = payload.get("parts", [])
    if parts:
        for part in parts:
            pt, ht = _extract_raw_body_parts(part)
            if pt and not plain_text:
                plain_text = pt
            if ht and not html_text:
                html_text = ht
        return plain_text, html_text

    data = payload.get("body", {}).get("data", "")
    if not data:
        return plain_text, html_text
    try:
        decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    except Exception:
        return plain_text, html_text
    if mime_type == "text/plain":
        plain_text = decoded
    elif mime_type == "text/html":
        html_text = decoded
    return plain_text, html_text


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
