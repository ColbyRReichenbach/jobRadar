"""Deterministic JD requirement cleaning for resume-tailoring evals.

The cleaner is intentionally conservative and eval-only. It is not trying to
understand every job description perfectly. Its job is to keep obvious
boilerplate, legal text, sales/marketing controls, and domain-only rows from
entering retrieval as if they were resume-tailoring requirements.
"""

from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass
from typing import Any


REQUIREMENT_CLEANER_VERSION = "resume_jd_requirement_cleaner_v1"

HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")

LEGAL_COMPENSATION_PATTERNS = (
    "all benefits are subject",
    "applicants will not be discriminated",
    "background check",
    "benefits are subject",
    "compensation",
    "dental",
    "disabled veterans",
    "equal opportunity",
    "equal-opportunity",
    "eeo",
    "medical condition",
    "pay range",
    "privacy policy",
    "protected by law",
    "reasonable accommodations",
    "salary",
    "sponsorship",
    "u.s. applicants",
    "veteran status",
    "visa sponsorship",
    "work authorization",
)

COMPANY_BOILERPLATE_PATTERNS = (
    "about the company",
    "about us",
    "backed by",
    "blog",
    "compliance report",
    "created by",
    "founded",
    "founder",
    "funding",
    "is an equal-opportunity",
    "mission is",
    "our mission",
    "our vision",
    "raised",
    "series ",
    "the future of work is here",
    "we are a team",
    "we are an ai research",
    "we believe",
    "we're a team",
    "why ",
)

SALES_MARKETING_PATTERNS = (
    "account executive",
    "brand marketing",
    "buyer committee",
    "buyer committees",
    "campaign",
    "campaigns",
    "commercial account",
    "enterprise account",
    "go-to-market",
    "gtm",
    "hospitality",
    "lockups",
    "marketing",
    "pipeline generation",
    "prospect",
    "quota",
    "restaurant",
    "restaurants",
    "salesforce",
    "social campaign",
)

DOMAIN_ONLY_PATTERNS = {
    "biology": {
        "biohub",
        "biological",
        "biology",
        "cell",
        "genomic",
        "genomics",
        "lab",
        "molecular",
        "sequencing",
        "single-cell",
    },
    "robotics": {
        "autonomy",
        "camera",
        "lidar",
        "perception",
        "robot",
        "robotics",
        "ros",
        "sensor",
        "slam",
    },
    "ads_revenue": {
        "ads",
        "advertising",
        "monetization",
        "revenue",
    },
}

TRANSFERABLE_TECHNICAL_TERMS = {
    "ab test",
    "agentic",
    "ai",
    "analysis",
    "analytics",
    "api",
    "automate",
    "automation",
    "benchmark",
    "bi",
    "business intelligence",
    "coding",
    "confluence",
    "data",
    "dashboard",
    "deploy",
    "deploying",
    "deployment",
    "engineering",
    "evaluation",
    "experimentation",
    "experiment",
    "experiments",
    "feature",
    "github",
    "grounding",
    "heuristic",
    "heuristics",
    "infrastructure",
    "insight",
    "insights",
    "integration",
    "integrations",
    "interpretable",
    "llm",
    "llms",
    "machine learning",
    "methodologies",
    "metrics",
    "model",
    "models",
    "monitoring",
    "outcome",
    "outcomes",
    "pipeline",
    "pipelines",
    "product",
    "products",
    "python",
    "rag",
    "ranking",
    "retrieval",
    "rubric",
    "rubrics",
    "search",
    "security",
    "semantic",
    "slack",
    "sql",
    "system",
    "testing",
    "visualization",
    "vision",
    "workflow",
}

ACTION_TERMS = {
    "analyze",
    "automate",
    "build",
    "collaborate",
    "create",
    "define",
    "deploy",
    "design",
    "develop",
    "drive",
    "evaluate",
    "implement",
    "improve",
    "lead",
    "leverage",
    "maintain",
    "measure",
    "monitor",
    "optimize",
    "own",
    "partner",
    "prototype",
    "ship",
    "support",
    "train",
    "translate",
    "uncover",
}


@dataclass(frozen=True)
class RequirementCleanerDecision:
    version: str
    category: str
    retrieval_policy: str
    reasons: list[str]
    original_query: str
    cleaned_query: str

    @property
    def should_retrieve(self) -> bool:
        return self.retrieval_policy == "retrieve"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def clean_requirement_text(value: str) -> str:
    """Remove HTML and whitespace noise while preserving normal wording."""

    text = html.unescape(value or "")
    text = text.replace("\u00a0", " ")
    text = HTML_TAG_RE.sub(" ", text)
    text = re.sub(r"https?://\S+|www\.\S+", " ", text, flags=re.IGNORECASE)
    text = WHITESPACE_RE.sub(" ", text).strip(" -•\t\r\n")
    return text


def _contains_any(text: str, patterns: tuple[str, ...] | set[str]) -> bool:
    for pattern in patterns:
        normalized = pattern.strip()
        if not normalized:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", text):
            return True
    return False


def _sales_marketing_match(text: str) -> bool:
    strong_terms = {
        "account executive",
        "brand marketing",
        "campaign",
        "campaigns",
        "enterprise account",
        "go-to-market",
        "gtm",
        "hospitality",
        "marketing",
        "pipeline generation",
        "quota",
        "restaurant",
        "restaurants",
    }
    weak_terms = {
        "buyer committee",
        "buyer committees",
        "commercial account",
        "prospect",
        "salesforce",
    }
    return _contains_any(text, strong_terms) or len([term for term in weak_terms if _contains_any(text, {term})]) >= 2


def _has_action_signal(text: str) -> bool:
    return bool(re.search(r"\b(" + "|".join(re.escape(term) for term in sorted(ACTION_TERMS)) + r")\b", text))


def _has_transferable_signal(text: str) -> bool:
    return _contains_any(text, TRANSFERABLE_TECHNICAL_TERMS)


def classify_requirement_for_retrieval(query: str, *, case_title: str = "") -> RequirementCleanerDecision:
    cleaned = clean_requirement_text(query)
    lowered = cleaned.lower()
    title_lower = case_title.lower()
    reasons: list[str] = []

    if not cleaned:
        return RequirementCleanerDecision(
            version=REQUIREMENT_CLEANER_VERSION,
            category="empty",
            retrieval_policy="skip",
            reasons=["empty_after_cleaning"],
            original_query=query,
            cleaned_query=cleaned,
        )

    if _contains_any(lowered, LEGAL_COMPENSATION_PATTERNS):
        return RequirementCleanerDecision(
            version=REQUIREMENT_CLEANER_VERSION,
            category="legal_compensation",
            retrieval_policy="skip",
            reasons=["legal_or_compensation_boilerplate"],
            original_query=query,
            cleaned_query=cleaned,
        )

    title_is_sales_marketing = _contains_any(title_lower, SALES_MARKETING_PATTERNS)
    if title_is_sales_marketing or _sales_marketing_match(lowered):
        return RequirementCleanerDecision(
            version=REQUIREMENT_CLEANER_VERSION,
            category="sales_marketing_role",
            retrieval_policy="skip",
            reasons=["sales_or_marketing_role_context"],
            original_query=query,
            cleaned_query=cleaned,
        )

    if _contains_any(lowered, COMPANY_BOILERPLATE_PATTERNS):
        # Product-context rows often contain company wording plus real technical
        # context. Keep them only if they include action or transferable signals.
        if not (_has_action_signal(lowered) and _has_transferable_signal(lowered)):
            return RequirementCleanerDecision(
                version=REQUIREMENT_CLEANER_VERSION,
                category="company_boilerplate",
                retrieval_policy="skip",
                reasons=["company_or_funding_boilerplate"],
                original_query=query,
                cleaned_query=cleaned,
            )
        reasons.append("contains_company_context")

    matched_domain_groups = [
        group_name for group_name, terms in DOMAIN_ONLY_PATTERNS.items() if _contains_any(lowered, terms)
    ]
    if matched_domain_groups and not _has_transferable_signal(lowered):
        return RequirementCleanerDecision(
            version=REQUIREMENT_CLEANER_VERSION,
            category="domain_only",
            retrieval_policy="skip",
            reasons=[f"domain_only:{group}" for group in matched_domain_groups],
            original_query=query,
            cleaned_query=cleaned,
        )
    if matched_domain_groups:
        reasons.extend(f"domain_transferable:{group}" for group in matched_domain_groups)

    if _has_action_signal(lowered) and _has_transferable_signal(lowered):
        return RequirementCleanerDecision(
            version=REQUIREMENT_CLEANER_VERSION,
            category="actual_requirement",
            retrieval_policy="retrieve",
            reasons=reasons or ["action_and_transferable_signal"],
            original_query=query,
            cleaned_query=cleaned,
        )

    if _has_transferable_signal(lowered):
        return RequirementCleanerDecision(
            version=REQUIREMENT_CLEANER_VERSION,
            category="product_context",
            retrieval_policy="retrieve",
            reasons=reasons or ["transferable_product_context"],
            original_query=query,
            cleaned_query=cleaned,
        )

    return RequirementCleanerDecision(
        version=REQUIREMENT_CLEANER_VERSION,
        category="company_boilerplate",
        retrieval_policy="skip",
        reasons=["no_action_or_transferable_signal"],
        original_query=query,
        cleaned_query=cleaned,
    )
