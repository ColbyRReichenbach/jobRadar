"""Deterministic pairwise support verifier for resume-tailoring evals.

This module is intentionally local and auditable. It answers a narrower
question than retrieval: given one JD requirement and one evidence card, is the
evidence safe to cite for that requirement?
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


SUPPORT_VERIFIER_VERSION = "resume_pairwise_support_verifier_v1"
SUPPORTS = "supports"
PARTIAL_SUPPORT = "partial_support"
NOT_ENOUGH_INFO = "not_enough_info"

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+.#/-]*")

STOPWORDS = {
    "a",
    "ability",
    "about",
    "across",
    "and",
    "are",
    "as",
    "at",
    "before",
    "by",
    "can",
    "for",
    "from",
    "has",
    "have",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "plus",
    "such",
    "that",
    "the",
    "their",
    "this",
    "to",
    "using",
    "with",
    "work",
    "working",
    "you",
    "your",
}

GENERIC_TERMS = {
    "analysis",
    "analytics",
    "artifact",
    "artifacts",
    "build",
    "building",
    "business",
    "code",
    "communicate",
    "create",
    "customer",
    "data",
    "deliver",
    "develop",
    "development",
    "feature",
    "features",
    "implementation",
    "implement",
    "insight",
    "insights",
    "manage",
    "model",
    "models",
    "modeling",
    "performance",
    "pipeline",
    "platform",
    "product",
    "provide",
    "relationship",
    "relationships",
    "report",
    "reporting",
    "solution",
    "solutions",
    "support",
    "supports",
    "system",
    "systems",
    "tool",
    "tools",
    "user",
    "users",
    "value",
}

WEAK_SUPPORT_TERMS = {
    "api",
    "apis",
    "automated",
    "challenge",
    "core",
    "dashboard",
    "dashboards",
    "daily",
    "evaluation",
    "including",
    "intelligence",
    "metrics",
    "research",
    "team",
    "testing",
}

TOKEN_ALIASES = {
    "apis": {"api"},
    "dashboards": {"dashboard"},
    "docker": {"containerization"},
    "experiments": {"experiment"},
    "forecasts": {"forecast"},
    "forecasting": {"forecast"},
    "frameworks": {"framework"},
    "kubernetes": {"containerization"},
    "large": {"llm"},
    "llms": {"llm"},
    "machine": {"ml"},
    "mlops": {"ml", "ops"},
    "postgresql": {"postgres", "sql"},
    "recommender": {"recommendation"},
    "recommendations": {"recommendation"},
    "retrieval": {"search"},
    "statistics": {"statistical"},
    "tests": {"testing"},
    "visualizations": {"visualization"},
}

TECH_TERMS = {
    "ai",
    "airflow",
    "alembic",
    "api",
    "bigquery",
    "celery",
    "ci",
    "docker",
    "etl",
    "fastapi",
    "github",
    "h3",
    "json",
    "langgraph",
    "lightgbm",
    "llm",
    "ml",
    "mlops",
    "openai",
    "postgres",
    "postgresql",
    "python",
    "rag",
    "react",
    "redis",
    "retrieval",
    "search",
    "sklearn",
    "snowflake",
    "sql",
    "zod",
}

CATEGORY_PATTERNS = {
    "ai_engineering": re.compile(r"\b(ai|llm|rag|agent|openai|langgraph|prompt|copilot)\b", re.IGNORECASE),
    "analytics": re.compile(r"\b(analytics?|dashboard|metrics?|insights?|visuali[sz]ation|reporting)\b", re.IGNORECASE),
    "api": re.compile(r"\b(api|apis|fastapi|backend|service|services)\b", re.IGNORECASE),
    "data_engineering": re.compile(r"\b(data|pipeline|etl|ingest|warehouse|postgres|sql|snowflake|bigquery|airflow|dbt)\b", re.IGNORECASE),
    "evals": re.compile(r"\b(eval|evaluation|benchmark|quality|red.?team|simulation|testing|test|reliability)\b", re.IGNORECASE),
    "frontend": re.compile(r"\b(frontend|react|ui|dashboard|vite|next)\b", re.IGNORECASE),
    "geospatial": re.compile(r"\b(geospatial|h3|map|property|valuation|nyc|parcel)\b", re.IGNORECASE),
    "ml": re.compile(r"\b(machine learning|ml|model|models|modeling|forecast|lightgbm|xgboost|sklearn|optuna)\b", re.IGNORECASE),
    "privacy_safety": re.compile(r"\b(privacy|pii|redact|sanitize|preflight|safety|policy|governance)\b", re.IGNORECASE),
    "retrieval": re.compile(r"\b(retrieval|search|ranking|rank|semantic|citation|evidence)\b", re.IGNORECASE),
    "security": re.compile(r"\b(security|auth|audit|compliance|governance|risk)\b", re.IGNORECASE),
}

DOMAIN_ANCHOR_GROUPS = {
    "bioinformatics": {
        "query_terms": {
            "assay",
            "bioinformatics",
            "biological",
            "cell",
            "genomics",
            "immunology",
            "multiomic",
            "oncology",
            "rna",
            "scanpy",
            "seq",
            "sequencing",
            "single",
            "trajectory",
        },
        "evidence_terms": {
            "assay",
            "bioinformatics",
            "biological",
            "cell",
            "genomics",
            "immunology",
            "multiomic",
            "oncology",
            "rna",
            "scanpy",
            "seq",
            "sequencing",
            "single",
            "trajectory",
        },
    },
    "enterprise_sales": {
        "query_terms": {
            "buyer",
            "commercial",
            "contract",
            "enterprise",
            "executive",
            "narrative",
            "quota",
            "revenue",
            "salesforce",
            "stakeholder",
        },
        "evidence_terms": {"buyer", "commercial", "contract", "enterprise", "quota", "revenue", "salesforce"},
    },
    "hospitality_marketing": {
        "query_terms": {
            "activation",
            "brand",
            "campaign",
            "cultural",
            "hospitality",
            "lockups",
            "marketing",
            "partner",
            "restaurant",
            "social",
        },
        "evidence_terms": {
            "activation",
            "brand",
            "campaign",
            "cultural",
            "hospitality",
            "lockups",
            "marketing",
            "partner",
            "restaurant",
            "social",
        },
    },
    "robotics": {
        "query_terms": {
            "autonomy",
            "camera",
            "cpp",
            "depth",
            "embodied",
            "hardware",
            "imu",
            "lidar",
            "navigation",
            "opencv",
            "perception",
            "planning",
            "robot",
            "robotics",
            "ros",
            "ros2",
            "sensor",
            "slam",
        },
        "evidence_terms": {
            "autonomy",
            "camera",
            "cpp",
            "depth",
            "embodied",
            "hardware",
            "imu",
            "lidar",
            "navigation",
            "opencv",
            "perception",
            "planning",
            "robot",
            "robotics",
            "ros",
            "ros2",
            "sensor",
            "slam",
        },
    },
}


@dataclass(frozen=True)
class SupportVerificationDecision:
    evidence_id: str
    label: str
    accepted: bool
    score: float
    reasons: list[str]
    matched_terms: list[str]
    weak_matched_terms: list[str]
    category_overlap: list[str]
    missing_domain_groups: list[str]
    embedding_similarity: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _tokens(text: str) -> set[str]:
    normalized = (text or "").lower().replace("c++", " cpp ")
    normalized = re.sub(r"\bml\s+ops\b", " mlops ", normalized)
    normalized = re.sub(r"\bci\s*/\s*cd\b", " cicd ", normalized)
    normalized = re.sub(r"\bsingle[-\s]cell\b", " single cell ", normalized)
    normalized = re.sub(r"\brna[-\s]seq\b", " rna seq sequencing ", normalized)
    normalized = normalized.replace("large language models", "llm")
    tokens: set[str] = set()
    for raw_token in TOKEN_RE.findall(normalized):
        token = raw_token.strip("-/.+#").lower()
        if not token or token in STOPWORDS:
            continue
        if len(token) < 3 and token not in {"ai", "ci", "ml", "r"}:
            continue
        tokens.add(token)
        if token.endswith("ies") and len(token) > 4:
            tokens.add(f"{token[:-3]}y")
        if token.endswith("ing") and len(token) > 5:
            tokens.add(token[:-3])
        if token.endswith("ed") and len(token) > 4:
            tokens.add(token[:-2])
        if token.endswith("s") and not token.endswith("ss") and len(token) > 3:
            tokens.add(token[:-1])
        tokens.update(TOKEN_ALIASES.get(token, set()))
    return tokens


def _categories(text: str, skills: list[str]) -> set[str]:
    categories = set(skills)
    for category, pattern in CATEGORY_PATTERNS.items():
        if pattern.search(text or ""):
            categories.add(category)
    return categories


def _domain_group_failures(query_terms: set[str], evidence_terms: set[str]) -> list[str]:
    missing: list[str] = []
    for group_name, config in DOMAIN_ANCHOR_GROUPS.items():
        if not query_terms & set(config["query_terms"]):
            continue
        if not evidence_terms & set(config["evidence_terms"]):
            missing.append(group_name)
    return missing


def _is_broad_inventory(evidence_text: str, source_section: str) -> bool:
    lowered_section = (source_section or "").lower()
    if "tools, skills" in lowered_section or "technologies demonstrated" in lowered_section:
        return True
    return evidence_text.count(",") >= 10 and len(evidence_text.split()) >= 35


def verify_requirement_evidence(
    *,
    requirement_text: str,
    evidence_id: str,
    evidence_text: str,
    evidence_skills: list[str] | None = None,
    evidence_claim_type: str = "",
    evidence_section: str = "",
    embedding_similarity: float | None = None,
) -> SupportVerificationDecision:
    skills = evidence_skills or []
    combined_evidence = " ".join([evidence_text, " ".join(skills), evidence_claim_type, evidence_section])
    query_terms = _tokens(requirement_text)
    evidence_terms = _tokens(combined_evidence)
    query_categories = _categories(requirement_text, [])
    evidence_categories = _categories(combined_evidence, skills)
    category_overlap = sorted(query_categories & evidence_categories)
    matched_terms = sorted(
        term
        for term in (query_terms & evidence_terms)
        if term not in GENERIC_TERMS and term not in WEAK_SUPPORT_TERMS
    )
    weak_terms = sorted(
        term
        for term in (query_terms & evidence_terms)
        if term in WEAK_SUPPORT_TERMS or term in GENERIC_TERMS
    )
    tech_overlap = sorted((query_terms & evidence_terms) & TECH_TERMS)
    missing_domain_groups = _domain_group_failures(query_terms, evidence_terms)
    reasons: list[str] = []

    if missing_domain_groups:
        reasons.append("missing_domain_anchor")
    if _is_broad_inventory(evidence_text, evidence_section) and not tech_overlap and len(matched_terms) < 2:
        reasons.append("broad_inventory_without_exact_skill")
    if not category_overlap and len(matched_terms) < 2 and (embedding_similarity or 0.0) < 0.55:
        reasons.append("no_category_or_specific_overlap")
    if not matched_terms and len(weak_terms) < 2 and (embedding_similarity or 0.0) < 0.55:
        reasons.append("generic_or_no_overlap")

    score = (
        len(matched_terms) * 12.0
        + len(category_overlap) * 8.0
        + len(tech_overlap) * 5.0
        + len(weak_terms) * 1.0
        + ((embedding_similarity or 0.0) * 10.0)
        - (len(missing_domain_groups) * 20.0)
    )

    if reasons:
        label = NOT_ENOUGH_INFO
    elif len(category_overlap) >= 2 and (len(matched_terms) >= 2 or tech_overlap):
        label = SUPPORTS
    elif len(matched_terms) >= 3 and (category_overlap or tech_overlap):
        label = SUPPORTS
    elif category_overlap and (matched_terms or len(weak_terms) >= 2 or (embedding_similarity or 0.0) >= 0.52):
        label = PARTIAL_SUPPORT
    elif len(matched_terms) >= 2 and (embedding_similarity or 0.0) >= 0.48:
        label = PARTIAL_SUPPORT
    else:
        label = NOT_ENOUGH_INFO
        reasons.append("insufficient_pairwise_support")

    accepted = label in {SUPPORTS, PARTIAL_SUPPORT}
    if accepted and label == PARTIAL_SUPPORT:
        reasons.append("transferable_partial_support")
    if accepted and label == SUPPORTS:
        reasons.append("direct_support")

    return SupportVerificationDecision(
        evidence_id=evidence_id,
        label=label,
        accepted=accepted,
        score=round(score, 6),
        reasons=reasons,
        matched_terms=matched_terms,
        weak_matched_terms=weak_terms,
        category_overlap=category_overlap,
        missing_domain_groups=missing_domain_groups,
        embedding_similarity=round(float(embedding_similarity), 6) if embedding_similarity is not None else None,
    )
