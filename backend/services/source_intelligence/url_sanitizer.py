from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

from backend.services.source_intelligence.url_classifier import (
    ClassifiedUrl,
    TRACKING_REDIRECT_PARAMS,
    classify_url,
)


TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_PARAMS = {
    "campaign",
    "email",
    "gh_jid",
    "gh_src",
    "gh_src_id",
    "li_fat_id",
    "li_medium",
    "li_source",
    "mc_cid",
    "mc_eid",
    "ref",
    "referrer",
    "source",
    "trk",
}
TOKEN_QUERY_PARAMS = {
    "application",
    "applicationid",
    "auth",
    "authorization",
    "candidate",
    "candidateid",
    "invite",
    "jwt",
    "magic",
    "profileid",
    "session",
    "sessionid",
    "token",
}


@dataclass(frozen=True)
class SanitizedUrl:
    raw_url: str
    canonical_public_url: str | None
    canonical_public_url_hash: str | None
    canonical_public_url_hash_version: str | None
    classification: ClassifiedUrl
    sanitization_status: str
    rejection_reason: str | None
    rule_ids: list[str]


def source_link_hash(value: str, *, key: str | None = None, version: str | None = None) -> tuple[str, str]:
    hash_key = key or os.getenv("SOURCE_LINK_HASH_KEY")
    hash_version = version or os.getenv("SOURCE_LINK_HASH_KEY_VERSION", "v1")
    if not hash_key:
        if os.getenv("TESTING") == "1":
            hash_key = "test-source-link-hash-key"
        else:
            raise RuntimeError("SOURCE_LINK_HASH_KEY is required for source-link hashing")
    digest = hmac.new(hash_key.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest, hash_version


def sanitize_url(raw_url: str | ClassifiedUrl) -> SanitizedUrl:
    classification = raw_url if isinstance(raw_url, ClassifiedUrl) else classify_url(raw_url)
    rule_ids = list(classification.rule_ids)

    if classification.link_type == "tracking_redirect":
        unwrapped = _offline_unwrap_redirect(classification)
        if unwrapped:
            sanitized = sanitize_url(unwrapped)
            if sanitized.canonical_public_url:
                return SanitizedUrl(
                    raw_url=classification.raw_url,
                    canonical_public_url=sanitized.canonical_public_url,
                    canonical_public_url_hash=sanitized.canonical_public_url_hash,
                    canonical_public_url_hash_version=sanitized.canonical_public_url_hash_version,
                    classification=classification,
                    sanitization_status=sanitized.sanitization_status,
                    rejection_reason=sanitized.rejection_reason,
                    rule_ids=[*rule_ids, "offline_unwrapped_redirect", *sanitized.rule_ids],
                )
        return _private_only(classification, "tracking_redirect_unresolved", [*rule_ids, "tracking_redirect_unresolved"])

    if not classification.safe_to_share or classification.contains_private_token or not classification.normalized_url:
        return _private_only(
            classification,
            classification.rejection_reason or "not_safe_to_share",
            rule_ids,
        )

    parsed = urlparse(classification.normalized_url)
    filtered_query: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        key_l = key.lower()
        if key_l.startswith(TRACKING_QUERY_PREFIXES) or key_l in TRACKING_QUERY_PARAMS:
            rule_ids.append(f"removed_tracking_param:{key_l}")
            continue
        if key_l in TOKEN_QUERY_PARAMS or any(token in key_l for token in TOKEN_QUERY_PARAMS):
            return _private_only(classification, f"private_query_param:{key_l}", [*rule_ids, f"private_query_param:{key_l}"])
        filtered_query.append((key, value))

    path = quote(parsed.path or "/", safe="/:@")
    if path != "/":
        path = path.rstrip("/") or "/"
    canonical = urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        path,
        "",
        urlencode(filtered_query, doseq=True),
        "",
    ))
    try:
        digest, version = source_link_hash(canonical)
    except RuntimeError:
        digest, version = None, None
    return SanitizedUrl(
        raw_url=classification.raw_url,
        canonical_public_url=canonical,
        canonical_public_url_hash=digest,
        canonical_public_url_hash_version=version,
        classification=classification,
        sanitization_status="safe_public",
        rejection_reason=None,
        rule_ids=rule_ids,
    )


def sanitize_public_job_url(raw_url: str | None) -> str | None:
    if not raw_url:
        return None
    sanitized = sanitize_url(raw_url)
    if sanitized.sanitization_status != "safe_public":
        return None
    return sanitized.canonical_public_url


def _private_only(classification: ClassifiedUrl, reason: str, rule_ids: list[str]) -> SanitizedUrl:
    return SanitizedUrl(
        raw_url=classification.raw_url,
        canonical_public_url=None,
        canonical_public_url_hash=None,
        canonical_public_url_hash_version=None,
        classification=classification,
        sanitization_status="private_user_only" if reason != "invalid_url" else "rejected",
        rejection_reason=reason,
        rule_ids=rule_ids,
    )


def _offline_unwrap_redirect(classification: ClassifiedUrl) -> str | None:
    if not classification.normalized_url:
        return None
    parsed = urlparse(classification.normalized_url)
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower() not in TRACKING_REDIRECT_PARAMS:
            continue
        candidate = value.strip()
        if candidate.startswith("http://") or candidate.startswith("https://"):
            nested = classify_url(candidate)
            if nested.normalized_url and nested.safe_to_share and not nested.contains_private_token:
                return candidate
    return None
