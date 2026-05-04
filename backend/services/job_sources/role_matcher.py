from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.services.job_sources.base import NormalizedJobPosting


ROLE_ALIASES = {
    "analyst": {
        "data analyst",
        "business analyst",
        "bi analyst",
        "reporting analyst",
        "product analyst",
        "analytics engineer",
        "risk analyst",
        "financial analyst",
        "operations analyst",
        "cloud data analyst",
    },
    "data": {"data scientist", "data engineer", "data analyst", "analytics engineer", "machine learning engineer"},
    "engineer": {"software engineer", "backend engineer", "frontend engineer", "platform engineer", "data engineer"},
    "ml": {"machine learning engineer", "ml engineer", "ai engineer", "applied scientist"},
    "ai": {"ai engineer", "machine learning engineer", "applied ai engineer", "ai product manager"},
}


@dataclass(frozen=True)
class RoleMatch:
    posting: NormalizedJobPosting
    score: int
    reasons: list[str] = field(default_factory=list)


def normalize_title(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def expand_role_query(query: str, *, domain: str | None = None) -> set[str]:
    normalized = normalize_title(query)
    terms = {normalized} if normalized else set()
    for key, aliases in ROLE_ALIASES.items():
        if key in normalized.split() or normalized == key:
            terms.update(aliases)
    if "analyst" in terms or normalized == "analyst":
        if domain and domain.lower() in {"finance", "banking", "risk"}:
            terms.add("investment analyst")
        else:
            terms.discard("investment analyst")
    return {term for term in terms if term}


def score_posting(posting: NormalizedJobPosting, query: str, *, location: str = "", domain: str | None = None) -> RoleMatch:
    title = normalize_title(posting.title)
    query_norm = normalize_title(query)
    expansions = expand_role_query(query, domain=domain)
    score = 0
    reasons: list[str] = []

    if query_norm and query_norm in title:
        score += 55
        reasons.append("title_similarity")
    elif any(alias and alias in title for alias in expansions):
        score += 45
        reasons.append("role_family_match")

    if location and normalize_title(location) and normalize_title(location) in normalize_title(posting.location_text):
        score += 15
        reasons.append("location_match")

    if posting.source_confidence:
        score += min(20, round(posting.source_confidence * 20))
        reasons.append("source_confidence")

    if posting.date_posted:
        score += 5
        reasons.append("freshness")

    return RoleMatch(posting=posting, score=min(score, 100), reasons=reasons)


def rank_postings(postings: list[NormalizedJobPosting], query: str, *, location: str = "", domain: str | None = None) -> list[RoleMatch]:
    matches = [score_posting(posting, query, location=location, domain=domain) for posting in postings]
    return sorted(matches, key=lambda item: item.score, reverse=True)
