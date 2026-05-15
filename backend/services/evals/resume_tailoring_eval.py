"""Eval-only evidence-grounded resume tailoring experiment.

This module deliberately avoids production resume tailoring paths. It builds a
local fixture-backed experiment that indexes sanitized project evidence through
the existing UserKnowledgeDocument/DocumentChunk retrieval foundation, compares
prompt-only and evidence-grounded deterministic drafts, and reports privacy and
unsupported-claim checks.
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.models import Base, RetrievalTrace, User
from backend.services.evals.resume_project_ingest import (
    PROJECT_DOC_GRANULARITY_ATOMIC,
    PROJECT_DOC_GRANULARITY_SECTION,
    ProjectDocExtractionResult,
    extract_project_doc_results,
    summarize_project_doc_results,
)
from backend.services.evals.resume_requirement_cleaner import classify_requirement_for_retrieval
from backend.services.evals.resume_support_verifier import (
    SUPPORT_VERIFIER_VERSION,
    SupportVerificationDecision,
    verify_requirement_evidence,
)
from backend.services.retrieval.indexer import index_knowledge_document
from backend.services.retrieval.lexical import RETRIEVER_VERSION, RetrievedChunk, retrieve_document_chunks
from backend.services.search.documents import SearchDocumentInput


DEFAULT_FIXTURE_ROOT = Path("tests/fixtures/resume_tailoring")
DEFAULT_PROJECT_DIR = DEFAULT_FIXTURE_ROOT / "projects"
DEFAULT_PROJECT_DOC_DIR = DEFAULT_FIXTURE_ROOT / "project_docs"
DEFAULT_JD_CASES = DEFAULT_FIXTURE_ROOT / "jd_cases.json"
DEFAULT_RESUME = DEFAULT_FIXTURE_ROOT / "sanitized_resume.md"
DEFAULT_OUTPUT_DIR = Path("docs/ai-artifacts/generated/resume-tailoring-evidence-eval")
PROJECT_EVIDENCE_SOURCE_TYPE = "project_evidence"
DATASET_VERSION = "resume_tailoring_evidence_eval_v1"
PROMPT_ONLY_VERSION = "deterministic_prompt_only_v1"
EVIDENCE_GROUNDED_VERSION = "deterministic_evidence_grounded_v1"
SANITIZER_VERSION = "resume_preflight_sanitizer_v1"
RETRIEVAL_ACCEPTANCE_GATE_VERSION = "resume_lexical_acceptance_gate_v1"
RETRIEVAL_STRATEGY_LEXICAL = "lexical"
RETRIEVAL_STRATEGY_PARENT_CHILD_LEXICAL = "parent_child_lexical"
RETRIEVAL_STRATEGY_OPENAI_EMBEDDING = "openai_embedding"
RETRIEVAL_STRATEGY_OPENAI_HYBRID = "openai_hybrid"
RETRIEVAL_STRATEGIES = {
    RETRIEVAL_STRATEGY_LEXICAL,
    RETRIEVAL_STRATEGY_PARENT_CHILD_LEXICAL,
    RETRIEVAL_STRATEGY_OPENAI_EMBEDDING,
    RETRIEVAL_STRATEGY_OPENAI_HYBRID,
}
OPENAI_EMBEDDING_MODEL_DEFAULT = "text-embedding-3-small"
RESUME_EVAL_USER_ID = uuid.UUID("00000000-0000-0000-0000-00000000a411")
RESUME_EVAL_NAMESPACE = uuid.UUID("00000000-0000-0000-0000-00000000a412")

EDITABLE_SECTION_TITLES = {
    "summary",
    "professional_summary",
    "experience",
    "work_experience",
    "projects",
    "selected_projects",
    "skills",
    "technical_skills",
    "certifications",
}
FROZEN_SECTION_TITLES = {
    "contact_header",
    "contact",
    "header",
    "education",
}
PROTECTED_PLACEHOLDER_RE = re.compile(r"\[(?:NAME|EMAIL|PHONE|URL|LOCATION|FROZEN_SECTION|CONTACT_HEADER)[^\]]*\]")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}")
URL_RE = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
LOCATION_RE = re.compile(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*,\s[A-Z]{2}\b")
EVIDENCE_LINE_RE = re.compile(r"^\s*-\s*\[([A-Z0-9-]+)\]\s*(.+?)\s*$")
EVIDENCE_CITATION_RE = re.compile(r"\[evidence:\s*([A-Z0-9-]+)\]", re.IGNORECASE)
NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?%?\b")
RAW_PLACEHOLDER_RE = re.compile(r"\{\{[^}]+\}\}|\[(?:NAME|EMAIL|PHONE|URL|LOCATION|FROZEN_SECTION)[^\]]*\]")

TECH_TERMS = {
    "ai",
    "api",
    "ci",
    "docker",
    "etl",
    "fastapi",
    "json",
    "llm",
    "opentelemetry",
    "postgresql",
    "python",
    "rag",
    "redis",
    "retrieval",
    "sql",
}
INFLATED_OWNERSHIP_TERMS = {"architected", "directed", "led", "managed", "owned"}
GATE_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+.#/-]*")
GATE_STOPWORDS = {
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
GENERIC_RETRIEVAL_TERMS = {
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
    "discovery",
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
    "point",
    "points",
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
    "through",
    "user",
    "users",
    "value",
}
TOKEN_ALIASES = {
    "apis": {"api"},
    "dashboards": {"dashboard"},
    "docker": {"containerization"},
    "experiments": {"experiment"},
    "forecasting": {"forecast"},
    "forecasts": {"forecast"},
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
DOMAIN_ANCHOR_GROUPS = {
    "bioinformatics": {
        "query_terms": {
            "assay",
            "bioinformatics",
            "bioconductor",
            "biological",
            "cell",
            "clustering",
            "genomics",
            "immunology",
            "multiomic",
            "oncology",
            "rna",
            "scanpy",
            "seq",
            "sequencing",
            "seurat",
            "single",
            "trajectory",
            "translational",
        },
        "evidence_terms": {
            "assay",
            "bioinformatics",
            "bioconductor",
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
            "seurat",
            "single",
            "trajectory",
            "translational",
        },
    },
    "enterprise_sales": {
        "query_terms": {
            "buyer",
            "buyers",
            "commercial",
            "committee",
            "committees",
            "contract",
            "contracts",
            "enterprise",
            "executive",
            "narrative",
            "narratives",
            "pain",
            "quota",
            "quotas",
            "revenue",
            "salesforce",
            "stakeholder",
            "stakeholders",
        },
        "evidence_terms": {
            "buyer",
            "buyers",
            "commercial",
            "contract",
            "contracts",
            "quota",
            "quotas",
            "revenue",
            "salesforce",
        },
    },
    "hospitality_marketing": {
        "query_terms": {
            "activation",
            "activations",
            "banners",
            "brand",
            "campaign",
            "campaigns",
            "cultural",
            "hospitality",
            "lockups",
            "marketing",
            "partner",
            "partners",
            "restaurant",
            "social",
        },
        "evidence_terms": {
            "activation",
            "activations",
            "banners",
            "brand",
            "campaign",
            "campaigns",
            "cultural",
            "hospitality",
            "lockups",
            "marketing",
            "partner",
            "partners",
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
            "fusion",
            "hardware",
            "imu",
            "kalman",
            "lidar",
            "linux",
            "motion",
            "navigation",
            "opencv",
            "perception",
            "planning",
            "pose",
            "radar",
            "robot",
            "robotics",
            "ros",
            "ros2",
            "sensor",
            "sensors",
            "slam",
            "stereo",
            "tensorflow",
        },
        "evidence_terms": {
            "autonomy",
            "camera",
            "cpp",
            "depth",
            "embodied",
            "fusion",
            "hardware",
            "imu",
            "kalman",
            "lidar",
            "linux",
            "motion",
            "navigation",
            "opencv",
            "perception",
            "planning",
            "pose",
            "robot",
            "robotics",
            "ros",
            "ros2",
            "sensor",
            "sensors",
            "slam",
            "stereo",
            "tensorflow",
        },
    },
}


@dataclass(frozen=True)
class ProjectEvidenceRecord:
    project_id: str
    title: str
    evidence_id: str
    text: str
    skills: list[str]
    source_path: str
    project_tags: list[str] = field(default_factory=list)
    source_section: str = ""
    claim_type: str = "manual_project_fact"
    resume_safe: bool = True
    evidence_strength: str = "high"
    preflight_status: str = "pass"
    preflight_reasons: list[str] = field(default_factory=list)
    parent_evidence_id: str | None = None
    granularity: str = PROJECT_DOC_GRANULARITY_SECTION

    @property
    def source_id(self) -> uuid.UUID:
        return uuid.uuid5(RESUME_EVAL_NAMESPACE, self.evidence_id)

    @property
    def evidence_alias_ids(self) -> list[str]:
        aliases = [self.evidence_id]
        if self.parent_evidence_id and self.parent_evidence_id not in aliases:
            aliases.append(self.parent_evidence_id)
        return aliases

    def to_search_document(self, user_id: uuid.UUID) -> SearchDocumentInput:
        return SearchDocumentInput(
            user_id=user_id,
            source_type=PROJECT_EVIDENCE_SOURCE_TYPE,
            source_id=self.source_id,
            title=f"{self.title} {self.evidence_id}",
            subtitle=self.project_id,
            body=self.text,
            keywords=[*self.evidence_alias_ids, self.project_id, *self.skills],
            metadata={
                "project_id": self.project_id,
                "project_title": self.title,
                "evidence_id": self.evidence_id,
                "parent_evidence_id": self.parent_evidence_id,
                "evidence_alias_ids": self.evidence_alias_ids,
                "granularity": self.granularity,
                "skills": self.skills,
                "project_tags": self.project_tags,
                "source_path": self.source_path,
                "source_section": self.source_section,
                "claim_type": self.claim_type,
                "resume_safe": self.resume_safe,
                "evidence_strength": self.evidence_strength,
                "preflight_status": self.preflight_status,
                "preflight_reasons": self.preflight_reasons,
                "source_type": PROJECT_EVIDENCE_SOURCE_TYPE,
            },
            source_updated_at=datetime(2026, 5, 13, tzinfo=timezone.utc),
        )


@dataclass(frozen=True)
class RequirementCase:
    id: str
    query: str
    expected_evidence_ids: list[str]
    expected_parent_evidence_ids: list[str] | None = None
    expected_citation_evidence_ids: list[str] | None = None
    support_label: str = "direct"
    review_notes: str = ""
    control_type: str = "saved_app"

    @property
    def parent_expected_ids(self) -> list[str]:
        return self.expected_parent_evidence_ids if self.expected_parent_evidence_ids is not None else self.expected_evidence_ids

    @property
    def citation_expected_ids(self) -> list[str]:
        return self.expected_citation_evidence_ids if self.expected_citation_evidence_ids is not None else self.expected_evidence_ids


@dataclass(frozen=True)
class JobDescriptionCase:
    id: str
    title: str
    job_description: str
    expected_requirements: list[RequirementCase]
    control_type: str = "saved_app"


@dataclass(frozen=True)
class ResumeSection:
    title: str
    normalized_title: str
    content: str
    classification: str


@dataclass(frozen=True)
class ResumeSanitizationResult:
    sanitized_text: str
    placeholder_counts: dict[str, int]
    sections: list[ResumeSection]
    privacy_checks: dict[str, Any]


@dataclass(frozen=True)
class GeneratedBullet:
    case_id: str
    requirement_id: str
    strategy: str
    section: str
    text: str
    evidence_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvidenceAcceptanceDecision:
    evidence_id: str
    accepted: bool
    reasons: list[str]
    matched_terms: list[str]
    generic_overlap_terms: list[str]
    missing_domain_groups: list[str]
    score: float
    lexical_score: float
    embedding_similarity: float | None = None


@dataclass(frozen=True)
class EmbeddingRetrievalIndex:
    provider: str
    model: str
    records: list[ProjectEvidenceRecord]
    vectors_by_evidence_id: dict[str, list[float]]
    text_count: int
    dimension: int


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_label(value: Any) -> str:
    text = " ".join(str(value or "").split()).lower()
    text = re.sub(r"[\s/-]+", "_", text)
    text = re.sub(r"[^a-z0-9_]", "", text)
    return re.sub(r"_+", "_", text).strip("_")


def _read_frontmatter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    metadata: dict[str, str] = {}
    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[_normalize_label(key)] = value.strip()
    if end_index is None:
        return metadata, text
    return metadata, "\n".join(lines[end_index + 1 :]).strip()


def _metadata_list(metadata: dict[str, str], key: str) -> list[str]:
    value = metadata.get(key, "")
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_project_markdown(path: Path) -> list[ProjectEvidenceRecord]:
    text = path.read_text(encoding="utf-8")
    metadata, body = _read_frontmatter(text)
    project_id = metadata.get("project_id") or _normalize_label(path.stem)
    title = metadata.get("title") or project_id.replace("_", " ").title()
    project_tags = _metadata_list(metadata, "project_tags") or _metadata_list(metadata, "skills")
    default_skills = _metadata_list(metadata, "evidence_skills") or (
        [] if metadata.get("project_tags") else _metadata_list(metadata, "skills")
    )
    records: list[ProjectEvidenceRecord] = []

    pending_id = ""
    pending_text = ""
    pending_skills: list[str] = []

    def flush_pending() -> None:
        nonlocal pending_id, pending_text, pending_skills
        if not pending_id:
            return
        records.append(
            ProjectEvidenceRecord(
                project_id=project_id,
                title=title,
                evidence_id=pending_id,
                text=pending_text.strip(),
                skills=pending_skills or default_skills,
                project_tags=project_tags,
                source_path=str(path),
            )
        )
        pending_id = ""
        pending_text = ""
        pending_skills = []

    for line in body.splitlines():
        match = EVIDENCE_LINE_RE.match(line)
        if match:
            flush_pending()
            pending_id, pending_text = match.groups()
            pending_skills = []
            continue
        stripped = line.strip()
        if pending_id and ":" in stripped:
            key, value = stripped.split(":", 1)
            if _normalize_label(key) in {"evidence_skills", "skills"}:
                pending_skills = [item.strip() for item in re.split(r"[,;]", value) if item.strip()]
    flush_pending()
    return records


def load_project_evidence(project_dir: Path) -> list[ProjectEvidenceRecord]:
    records: list[ProjectEvidenceRecord] = []
    for path in sorted(project_dir.glob("*.md")):
        records.extend(parse_project_markdown(path))
    if not records:
        raise ValueError(f"No project evidence records found under {project_dir}")
    duplicate_ids = [evidence_id for evidence_id, count in _counts([item.evidence_id for item in records]).items() if count > 1]
    if duplicate_ids:
        raise ValueError(f"Duplicate project evidence IDs: {', '.join(sorted(duplicate_ids))}")
    return records


def project_records_from_doc_results(results: list[ProjectDocExtractionResult]) -> list[ProjectEvidenceRecord]:
    records: list[ProjectEvidenceRecord] = []
    for result in results:
        project_id = _normalize_label(result.project_name) or _normalize_label(Path(result.source_file).stem)
        for card in result.evidence_cards:
            if not card.resume_safe:
                continue
            records.append(
                ProjectEvidenceRecord(
                    project_id=project_id,
                    title=card.project_name,
                    evidence_id=card.evidence_id,
                    text=card.claim_text,
                    skills=card.skill_tags,
                    source_path=card.source_file,
                    source_section=card.source_section,
                    claim_type=card.claim_type,
                    resume_safe=card.resume_safe,
                    evidence_strength=card.evidence_strength,
                    preflight_status=card.preflight_status,
                    preflight_reasons=card.preflight_reasons,
                    parent_evidence_id=card.parent_evidence_id,
                    granularity=card.granularity,
                )
            )
    return records


def _validate_unique_evidence_ids(records: list[ProjectEvidenceRecord]) -> None:
    duplicate_ids = [evidence_id for evidence_id, count in _counts([item.evidence_id for item in records]).items() if count > 1]
    if duplicate_ids:
        raise ValueError(f"Duplicate project evidence IDs: {', '.join(sorted(duplicate_ids))}")


def load_jd_cases(path: Path) -> list[JobDescriptionCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases: list[JobDescriptionCase] = []
    for item in payload:
        requirements = [
            RequirementCase(
                id=str(req["id"]),
                query=str(req["query"]),
                expected_evidence_ids=list(req.get("expected_evidence_ids") or []),
                expected_parent_evidence_ids=(
                    list(req.get("expected_parent_evidence_ids") or [])
                    if "expected_parent_evidence_ids" in req
                    else None
                ),
                expected_citation_evidence_ids=(
                    list(req.get("expected_citation_evidence_ids") or [])
                    if "expected_citation_evidence_ids" in req
                    else None
                ),
                support_label=str(req.get("support_label") or ("direct" if req.get("expected_evidence_ids") else "none")),
                review_notes=str(req.get("review_notes") or ""),
                control_type=str(req.get("control_type") or item.get("control_type") or "saved_app"),
            )
            for req in item.get("expected_requirements", [])
        ]
        cases.append(
            JobDescriptionCase(
                id=str(item["id"]),
                title=str(item["title"]),
                job_description=str(item["job_description"]),
                expected_requirements=requirements,
                control_type=str(item.get("control_type") or "saved_app"),
            )
        )
    return cases


async def index_project_evidence_records(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    records: list[ProjectEvidenceRecord],
) -> None:
    for record in records:
        await index_knowledge_document(db, record.to_search_document(user_id), max_chunk_tokens=96, chunk_overlap_tokens=12)
    await db.flush()


def classify_resume_sections(text: str, *, frozen_sections: list[str] | None = None) -> list[ResumeSection]:
    frozen = set(FROZEN_SECTION_TITLES)
    frozen.update(_normalize_label(item) for item in frozen_sections or [])
    sections: list[ResumeSection] = []
    current_title = "Contact/Header"
    current_normalized = "contact_header"
    current_lines: list[str] = []

    def flush() -> None:
        classification = "editable" if current_normalized in EDITABLE_SECTION_TITLES else "frozen"
        if current_normalized in frozen:
            classification = "frozen"
        sections.append(
            ResumeSection(
                title=current_title,
                normalized_title=current_normalized,
                content="\n".join(current_lines).strip(),
                classification=classification,
            )
        )

    for line in text.splitlines():
        stripped = line.strip()
        heading_title = ""
        if stripped.startswith("## "):
            heading_title = stripped[3:].strip()
        elif stripped.endswith(":") and _normalize_label(stripped[:-1]) in EDITABLE_SECTION_TITLES | FROZEN_SECTION_TITLES:
            heading_title = stripped[:-1].strip()
        if heading_title:
            flush()
            current_title = heading_title
            current_normalized = _normalize_label(heading_title)
            current_lines = []
        else:
            current_lines.append(line)
    flush()
    return [section for section in sections if section.content or section.normalized_title != "contact_header"]


def _replace_counted(pattern: re.Pattern[str], text: str, placeholder_prefix: str) -> tuple[str, int]:
    count = 0

    def repl(_: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return f"[{placeholder_prefix}_{count}]"

    return pattern.sub(repl, text), count


def _redact_name(text: str) -> tuple[str, int]:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        lines[index] = line.replace(stripped, "[NAME_1]")
        return "\n".join(lines), 1
    return text, 0


def _redact_protected_fields(text: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    redacted, count = _redact_name(text)
    counts["name"] = count
    for label, pattern in [
        ("url", URL_RE),
        ("email", EMAIL_RE),
        ("phone", PHONE_RE),
        ("location", LOCATION_RE),
    ]:
        redacted, count = _replace_counted(pattern, redacted, label.upper())
        counts[label] = count
    return redacted, counts


def sanitize_resume_for_llm(text: str, *, frozen_sections: list[str] | None = None) -> ResumeSanitizationResult:
    redacted, counts = _redact_protected_fields(text)
    sections = classify_resume_sections(redacted, frozen_sections=frozen_sections)
    rendered: list[str] = []
    for section in sections:
        if section.normalized_title == "contact_header":
            rendered.append("[CONTACT_HEADER_REDACTED]")
            continue
        rendered.append(f"## {section.title}")
        if section.classification == "frozen":
            rendered.append(f"[FROZEN_SECTION:{section.normalized_title}]")
            counts["frozen_section"] = counts.get("frozen_section", 0) + 1
        else:
            rendered.append(section.content)
    sanitized_text = "\n\n".join(part for part in rendered if part.strip()).strip()
    privacy_checks = {
        "raw_email_leaks": bool(EMAIL_RE.search(sanitized_text)),
        "raw_phone_leaks": bool(PHONE_RE.search(sanitized_text)),
        "raw_url_leaks": bool(URL_RE.search(sanitized_text)),
        "protected_placeholder_count": len(PROTECTED_PLACEHOLDER_RE.findall(sanitized_text)),
        "sanitizer_version": SANITIZER_VERSION,
    }
    return ResumeSanitizationResult(
        sanitized_text=sanitized_text,
        placeholder_counts=counts,
        sections=sections,
        privacy_checks=privacy_checks,
    )


def _counts(values: list[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return result


def _extract_skills(text: str) -> set[str]:
    lowered = text.lower()
    return {term for term in TECH_TERMS if re.search(rf"\b{re.escape(term)}\b", lowered)}


def _gate_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    normalized_text = (text or "").lower().replace("c++", " cpp ")
    normalized_text = re.sub(r"\bml\s+ops\b", " mlops ", normalized_text)
    normalized_text = re.sub(r"\bci\s*/\s*cd\b", " cicd ", normalized_text)
    normalized_text = re.sub(r"\bsingle[-\s]cell\b", " single cell ", normalized_text)
    normalized_text = re.sub(r"\brna[-\s]seq\b", " rna seq sequencing ", normalized_text)
    normalized_text = normalized_text.replace("large language models", "llm")
    for raw_token in GATE_TOKEN_RE.findall(normalized_text):
        token = raw_token.strip("-/.+#").lower()
        if not token or token in GATE_STOPWORDS:
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


def _non_generic_terms(terms: set[str]) -> set[str]:
    return {term for term in terms if term not in GENERIC_RETRIEVAL_TERMS and term not in GATE_STOPWORDS}


def _domain_group_failures(query_terms: set[str], evidence_terms: set[str]) -> list[str]:
    missing: list[str] = []
    for group_name, config in DOMAIN_ANCHOR_GROUPS.items():
        query_matches = query_terms & set(config["query_terms"])
        if not query_matches:
            continue
        evidence_matches = evidence_terms & set(config["evidence_terms"])
        if not evidence_matches:
            missing.append(group_name)
    return missing


def _evidence_acceptance_decision(
    requirement: RequirementCase,
    chunk: RetrievedChunk,
    evidence_record: ProjectEvidenceRecord | None,
) -> EvidenceAcceptanceDecision:
    evidence_id = str(chunk.metadata.get("evidence_id", "")).upper()
    evidence_text = " ".join(
        item
        for item in [
            chunk.title,
            evidence_record.text if evidence_record else chunk.snippet,
            " ".join(evidence_record.skills) if evidence_record else "",
        ]
        if item
    )
    query_terms = _gate_tokens(requirement.query)
    evidence_terms = _gate_tokens(evidence_text)
    overlap_terms = sorted(_non_generic_terms(query_terms) & _non_generic_terms(evidence_terms))
    generic_overlap_terms = sorted((query_terms & evidence_terms) & GENERIC_RETRIEVAL_TERMS)
    missing_domain_groups = _domain_group_failures(query_terms, evidence_terms)
    embedding_similarity = chunk.metadata.get("embedding_similarity")
    embedding_similarity_float = float(embedding_similarity) if embedding_similarity is not None else None
    strong_embedding_match = embedding_similarity_float is not None and embedding_similarity_float >= 0.42
    reasons: list[str] = []
    if missing_domain_groups:
        reasons.append("missing_domain_anchor")
    if not overlap_terms and not strong_embedding_match:
        reasons.append("no_non_generic_overlap")
    if chunk.score < 2 and len(overlap_terms) < 2 and not strong_embedding_match:
        reasons.append("weak_lexical_score")
    accepted = not reasons
    embedding_boost = (embedding_similarity_float or 0.0) * 15.0
    acceptance_score = (
        (len(overlap_terms) * 10)
        + min(float(chunk.score), 20.0)
        + embedding_boost
        - (len(generic_overlap_terms) * 0.25)
    )
    return EvidenceAcceptanceDecision(
        evidence_id=evidence_id,
        accepted=accepted,
        reasons=reasons or ["accepted"],
        matched_terms=overlap_terms,
        generic_overlap_terms=generic_overlap_terms,
        missing_domain_groups=missing_domain_groups,
        score=round(acceptance_score, 6),
        lexical_score=round(float(chunk.score), 6),
        embedding_similarity=round(embedding_similarity_float, 6) if embedding_similarity_float is not None else None,
    )


def _apply_evidence_acceptance_gate(
    requirement: RequirementCase,
    chunks: list[RetrievedChunk],
    evidence_by_source_id: dict[str, ProjectEvidenceRecord],
    *,
    k: int,
) -> tuple[list[RetrievedChunk], list[EvidenceAcceptanceDecision]]:
    accepted_candidates: list[tuple[RetrievedChunk, EvidenceAcceptanceDecision, int]] = []
    decisions: list[EvidenceAcceptanceDecision] = []
    seen_evidence_ids: set[str] = set()
    for raw_index, chunk in enumerate(chunks):
        evidence_record = evidence_by_source_id.get(str(chunk.source_id))
        decision = _evidence_acceptance_decision(requirement, chunk, evidence_record)
        decisions.append(decision)
        if not decision.accepted:
            continue
        if not decision.evidence_id or decision.evidence_id in seen_evidence_ids:
            continue
        accepted_candidates.append((chunk, decision, raw_index))
        seen_evidence_ids.add(decision.evidence_id)
    accepted_chunks = [
        chunk
        for chunk, _, _ in sorted(
            accepted_candidates,
            key=lambda item: (item[1].score, -item[2]),
            reverse=True,
        )[:k]
    ]
    return accepted_chunks, decisions


def _apply_support_verifier(
    requirement: RequirementCase,
    chunks: list[RetrievedChunk],
    evidence_by_source_id: dict[str, ProjectEvidenceRecord],
    *,
    k: int,
) -> tuple[list[RetrievedChunk], list[SupportVerificationDecision]]:
    accepted_candidates: list[tuple[RetrievedChunk, SupportVerificationDecision, int]] = []
    decisions: list[SupportVerificationDecision] = []
    seen_evidence_ids: set[str] = set()
    for raw_index, chunk in enumerate(chunks):
        evidence_record = evidence_by_source_id.get(str(chunk.source_id))
        evidence_id = str(chunk.metadata.get("evidence_id", "")).upper()
        embedding_similarity = chunk.metadata.get("embedding_similarity")
        embedding_similarity_float = float(embedding_similarity) if embedding_similarity is not None else None
        decision = verify_requirement_evidence(
            requirement_text=requirement.query,
            evidence_id=evidence_id,
            evidence_text=evidence_record.text if evidence_record else chunk.snippet,
            evidence_skills=evidence_record.skills if evidence_record else list(chunk.metadata.get("skills") or []),
            evidence_claim_type=evidence_record.claim_type if evidence_record else str(chunk.metadata.get("claim_type") or ""),
            evidence_section=evidence_record.source_section if evidence_record else str(chunk.metadata.get("source_section") or ""),
            embedding_similarity=embedding_similarity_float,
        )
        decisions.append(decision)
        if not decision.accepted:
            continue
        if not decision.evidence_id or decision.evidence_id in seen_evidence_ids:
            continue
        accepted_candidates.append((chunk, decision, raw_index))
        seen_evidence_ids.add(decision.evidence_id)
    accepted_chunks = [
        chunk
        for chunk, _, _ in sorted(
            accepted_candidates,
            key=lambda item: (item[1].score, -item[2]),
            reverse=True,
        )[:k]
    ]
    return accepted_chunks, decisions


def _record_to_retrieved_chunk(
    record: ProjectEvidenceRecord,
    *,
    score: float,
    parent_chunk: RetrievedChunk | None = None,
    parent_rank: int | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> RetrievedChunk:
    metadata = {
        "project_id": record.project_id,
        "project_title": record.title,
        "evidence_id": record.evidence_id,
        "parent_evidence_id": record.parent_evidence_id,
        "evidence_alias_ids": record.evidence_alias_ids,
        "granularity": record.granularity,
        "skills": record.skills,
        "project_tags": record.project_tags,
        "source_path": record.source_path,
        "source_section": record.source_section,
        "claim_type": record.claim_type,
        "resume_safe": record.resume_safe,
        "evidence_strength": record.evidence_strength,
        "preflight_status": record.preflight_status,
        "preflight_reasons": record.preflight_reasons,
        "source_type": PROJECT_EVIDENCE_SOURCE_TYPE,
        "chunk_index": 0,
        "token_count": len(record.text.split()),
    }
    if parent_chunk:
        metadata.update(
            {
                "parent_retrieval_evidence_id": str(parent_chunk.metadata.get("evidence_id") or "").upper(),
                "parent_retrieval_score": parent_chunk.score,
                "parent_retrieval_rank": parent_rank,
            }
        )
    metadata.update(extra_metadata or {})
    return RetrievedChunk(
        chunk_id=uuid.uuid5(RESUME_EVAL_NAMESPACE, f"retrieved-child-chunk:{record.evidence_id}"),
        document_id=uuid.uuid5(RESUME_EVAL_NAMESPACE, f"retrieved-child-document:{record.evidence_id}"),
        source_type=PROJECT_EVIDENCE_SOURCE_TYPE,
        source_id=record.source_id,
        chunk_index=0,
        title=f"{record.title} {record.evidence_id}",
        snippet=record.text,
        score=score,
        content_hash=str(uuid.uuid5(RESUME_EVAL_NAMESPACE, f"retrieved-child-content:{record.evidence_id}")),
        metadata=metadata,
    )


def _child_candidate_score(query: str, record: ProjectEvidenceRecord, parent_chunk: RetrievedChunk, parent_rank: int) -> float:
    query_terms = _gate_tokens(query)
    evidence_terms = _gate_tokens(" ".join([record.title, record.text, " ".join(record.skills)]))
    non_generic_overlap = _non_generic_terms(query_terms) & _non_generic_terms(evidence_terms)
    generic_overlap = (query_terms & evidence_terms) & GENERIC_RETRIEVAL_TERMS
    score = (len(non_generic_overlap) * 10.0) + (len(generic_overlap) * 0.75) + min(float(parent_chunk.score), 20.0) * 0.35
    score -= parent_rank * 0.05
    return round(score, 6)


def _parent_to_child_records(records: list[ProjectEvidenceRecord]) -> dict[str, list[ProjectEvidenceRecord]]:
    children: dict[str, list[ProjectEvidenceRecord]] = {}
    for record in records:
        key = (record.parent_evidence_id or record.evidence_id).upper()
        children.setdefault(key, []).append(record)
    for key, values in children.items():
        children[key] = sorted(values, key=lambda record: (record.parent_evidence_id is None, record.evidence_id))
    return children


def _expand_parent_chunks_to_child_chunks(
    *,
    requirement: RequirementCase,
    retrieval_query: str,
    parent_chunks: list[RetrievedChunk],
    parent_to_children: dict[str, list[ProjectEvidenceRecord]],
    candidate_limit: int,
) -> list[RetrievedChunk]:
    candidates: list[tuple[RetrievedChunk, float, int]] = []
    seen_child_ids: set[str] = set()
    for parent_rank, parent_chunk in enumerate(parent_chunks, start=1):
        parent_id = str(parent_chunk.metadata.get("evidence_id") or "").upper()
        if not parent_id:
            continue
        for child in parent_to_children.get(parent_id, []):
            if child.evidence_id in seen_child_ids:
                continue
            seen_child_ids.add(child.evidence_id)
            score = _child_candidate_score(retrieval_query or requirement.query, child, parent_chunk, parent_rank)
            candidates.append(
                (
                    _record_to_retrieved_chunk(
                        child,
                        score=score,
                        parent_chunk=parent_chunk,
                        parent_rank=parent_rank,
                    ),
                    score,
                    parent_rank,
                )
            )
    return [
        chunk
        for chunk, _, _ in sorted(candidates, key=lambda item: (item[1], -item[2], item[0].metadata.get("evidence_id", "")), reverse=True)[
            :candidate_limit
        ]
    ]


def _env_value(name: str) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    env_path = Path(".env")
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        if key.strip() != name:
            continue
        return raw_value.strip().strip("'\"") or None
    return None


def _embedding_text_for_record(record: ProjectEvidenceRecord) -> str:
    return " ".join(
        item
        for item in [
            record.title,
            record.source_section,
            " ".join(record.skills),
            record.claim_type,
            record.text,
        ]
        if item
    )


def _embedding_text_for_requirement(requirement: RequirementCase, *, case_title: str, retrieval_query: str) -> str:
    return " ".join(item for item in [case_title, retrieval_query or requirement.query, requirement.support_label] if item)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = sum(a * a for a in left) ** 0.5
    right_norm = sum(b * b for b in right) ** 0.5
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def _openai_embeddings(texts: list[str], *, model: str) -> list[list[float]]:
    api_key = _env_value("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for OpenAI embedding eval strategies.")
    try:
        from openai import OpenAI
    except Exception as exc:  # pragma: no cover - depends on local env
        raise RuntimeError(f"openai package is required for OpenAI embedding eval strategies: {exc}") from exc

    client = OpenAI(api_key=api_key)
    vectors: list[list[float]] = []
    batch_size = 96
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = client.embeddings.create(model=model, input=batch)
        vectors.extend([list(item.embedding) for item in response.data])
    return vectors


def _build_openai_embedding_index(
    records: list[ProjectEvidenceRecord],
    *,
    model: str,
) -> EmbeddingRetrievalIndex:
    texts = [_embedding_text_for_record(record) for record in records]
    vectors = _openai_embeddings(texts, model=model) if texts else []
    vectors_by_evidence_id = {
        record.evidence_id: vector
        for record, vector in zip(records, vectors)
    }
    dimension = len(vectors[0]) if vectors else 0
    return EmbeddingRetrievalIndex(
        provider="openai",
        model=model,
        records=records,
        vectors_by_evidence_id=vectors_by_evidence_id,
        text_count=len(texts),
        dimension=dimension,
    )


def _retrieve_embedding_chunks(
    *,
    requirement: RequirementCase,
    case_title: str,
    retrieval_query: str,
    embedding_index: EmbeddingRetrievalIndex,
    limit: int,
) -> list[RetrievedChunk]:
    query_text = _embedding_text_for_requirement(requirement, case_title=case_title, retrieval_query=retrieval_query)
    query_vector = _openai_embeddings([query_text], model=embedding_index.model)[0]
    scored: list[tuple[ProjectEvidenceRecord, float]] = []
    for record in embedding_index.records:
        vector = embedding_index.vectors_by_evidence_id.get(record.evidence_id)
        if not vector:
            continue
        similarity = _cosine_similarity(query_vector, vector)
        scored.append((record, similarity))
    return [
        _record_to_retrieved_chunk(
            record,
            score=round(similarity * 100.0, 6),
            extra_metadata={
                "embedding_provider": embedding_index.provider,
                "embedding_model": embedding_index.model,
                "embedding_similarity": round(similarity, 6),
            },
        )
        for record, similarity in sorted(scored, key=lambda item: item[1], reverse=True)[:limit]
    ]


def _merge_lexical_and_embedding_chunks(
    lexical_chunks: list[RetrievedChunk],
    embedding_chunks: list[RetrievedChunk],
    *,
    limit: int,
) -> list[RetrievedChunk]:
    lexical_scores = {str(chunk.metadata.get("evidence_id") or "").upper(): float(chunk.score) for chunk in lexical_chunks}
    embedding_by_id = {str(chunk.metadata.get("evidence_id") or "").upper(): chunk for chunk in embedding_chunks}
    lexical_by_id = {str(chunk.metadata.get("evidence_id") or "").upper(): chunk for chunk in lexical_chunks}
    evidence_ids = [item for item in dict.fromkeys([*embedding_by_id, *lexical_by_id]) if item]
    max_lexical = max(lexical_scores.values(), default=1.0) or 1.0
    merged: list[tuple[RetrievedChunk, float]] = []
    for evidence_id in evidence_ids:
        embedding_chunk = embedding_by_id.get(evidence_id)
        lexical_chunk = lexical_by_id.get(evidence_id)
        base_chunk = embedding_chunk or lexical_chunk
        if not base_chunk:
            continue
        embedding_similarity = float((embedding_chunk or base_chunk).metadata.get("embedding_similarity") or 0.0)
        lexical_norm = min(lexical_scores.get(evidence_id, 0.0) / max_lexical, 1.0)
        hybrid_score = round((embedding_similarity * 70.0) + (lexical_norm * 30.0), 6)
        metadata = {
            **base_chunk.metadata,
            "hybrid_score": hybrid_score,
            "hybrid_embedding_similarity": round(embedding_similarity, 6),
            "hybrid_lexical_score": round(lexical_scores.get(evidence_id, 0.0), 6),
            "embedding_similarity": round(embedding_similarity, 6) if embedding_similarity else base_chunk.metadata.get("embedding_similarity"),
        }
        merged.append(
            (
                RetrievedChunk(
                    chunk_id=base_chunk.chunk_id,
                    document_id=base_chunk.document_id,
                    source_type=base_chunk.source_type,
                    source_id=base_chunk.source_id,
                    chunk_index=base_chunk.chunk_index,
                    title=base_chunk.title,
                    snippet=base_chunk.snippet,
                    score=hybrid_score,
                    content_hash=base_chunk.content_hash,
                    metadata=metadata,
                ),
                hybrid_score,
            )
        )
    return [chunk for chunk, _ in sorted(merged, key=lambda item: item[1], reverse=True)[:limit]]


def _extract_evidence_ids(text: str) -> list[str]:
    return [match.group(1).upper() for match in EVIDENCE_CITATION_RE.finditer(text)]


def _normalize_text(text: str) -> str:
    return " ".join((text or "").split())


def _has_raw_pii(text: str) -> bool:
    return bool(EMAIL_RE.search(text) or PHONE_RE.search(text))


def _has_raw_url(text: str) -> bool:
    return bool(URL_RE.search(text))


def _metric_mean(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return round(mean(present), 6) if present else None


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def build_prompt_only_bullets(case: JobDescriptionCase) -> list[GeneratedBullet]:
    bullets = []
    for requirement in case.expected_requirements[:3]:
        keywords = " ".join(requirement.query.split()[:6])
        bullets.append(
            GeneratedBullet(
                case_id=case.id,
                requirement_id=requirement.id,
                strategy="prompt_only",
                section="projects",
                text=f"Applied {keywords} to deliver role-relevant outcomes.",
                evidence_ids=[],
            )
        )
    return bullets


def build_evidence_grounded_bullets(
    case: JobDescriptionCase,
    retrieval_by_requirement: dict[str, dict[str, Any]],
    evidence_by_id: dict[str, ProjectEvidenceRecord],
) -> list[GeneratedBullet]:
    bullets: list[GeneratedBullet] = []
    for requirement in case.expected_requirements:
        result = retrieval_by_requirement.get(requirement.id, {})
        citation_expected_ids = set(requirement.citation_expected_ids)
        parent_expected_ids = set(requirement.parent_expected_ids)
        matches = result.get("returned_evidence_matches") or []
        selected_id = next(
            (
                str(match.get("evidence_id"))
                for match in matches
                if set(match.get("matched_citation_expected_ids") or []) & citation_expected_ids
                and str(match.get("evidence_id")) in evidence_by_id
            ),
            None,
        )
        if not selected_id:
            selected_id = next(
                (
                    str(match.get("evidence_id"))
                    for match in matches
                    if set(match.get("matched_expected_ids") or []) & parent_expected_ids
                    and str(match.get("evidence_id")) in evidence_by_id
                ),
                None,
            )
        if not selected_id and citation_expected_ids:
            returned_ids = result.get("returned_evidence_ids", [])
            selected_id = next((item for item in returned_ids if item in citation_expected_ids and item in evidence_by_id), None)
        if not selected_id:
            returned_ids = result.get("returned_evidence_ids", [])
            selected_id = next((item for item in returned_ids if item in parent_expected_ids and item in evidence_by_id), None)
        if not selected_id:
            continue
        evidence = evidence_by_id[selected_id]
        bullets.append(
            GeneratedBullet(
                case_id=case.id,
                requirement_id=requirement.id,
                strategy="evidence_grounded",
                section="projects",
                text=f"{evidence.text} [evidence: {evidence.evidence_id}]",
                evidence_ids=[evidence.evidence_id],
            )
        )
    return bullets


def _requirement_has_parent_support(requirement: RequirementCase) -> bool:
    return bool(requirement.parent_expected_ids)


def _requirement_has_citation_support(requirement: RequirementCase) -> bool:
    return bool(requirement.citation_expected_ids)


def _add_grounded_generation_coverage(
    summary: dict[str, Any],
    *,
    cases: list[JobDescriptionCase],
    grounded_bullets: list[GeneratedBullet],
) -> None:
    generated_keys = {(bullet.case_id, bullet.requirement_id) for bullet in grounded_bullets}
    all_requirements = [
        (case.id, requirement.id, _requirement_has_parent_support(requirement))
        for case in cases
        for requirement in case.expected_requirements
    ]
    supported_requirements = [item for item in all_requirements if item[2]]
    unsupported_requirements = [item for item in all_requirements if not item[2]]
    missed_supported = [item for item in supported_requirements if (item[0], item[1]) not in generated_keys]
    correct_abstentions = [item for item in unsupported_requirements if (item[0], item[1]) not in generated_keys]
    unsupported_generations = [item for item in unsupported_requirements if (item[0], item[1]) in generated_keys]
    summary.update(
        {
            "requirement_count": len(all_requirements),
            "supported_requirement_count": len(supported_requirements),
            "generated_requirement_count": len(generated_keys),
            "abstention_count": len(all_requirements) - len(generated_keys),
            "correct_abstention_count": len(correct_abstentions),
            "missed_supported_requirement_count": len(missed_supported),
            "unsupported_requirement_generation_count": len(unsupported_generations),
        }
    )


def _chunk_evidence_id(chunk: RetrievedChunk) -> str | None:
    evidence_id = chunk.metadata.get("evidence_id")
    return str(evidence_id).upper() if evidence_id else None


def _chunk_evidence_aliases(chunk: RetrievedChunk) -> list[str]:
    aliases: list[str] = []
    metadata_aliases = chunk.metadata.get("evidence_alias_ids") or []
    if isinstance(metadata_aliases, str):
        metadata_aliases = [metadata_aliases]
    for value in [_chunk_evidence_id(chunk), chunk.metadata.get("parent_evidence_id"), *metadata_aliases]:
        if not value:
            continue
        normalized = str(value).upper()
        if normalized not in aliases:
            aliases.append(normalized)
    return aliases


def _evidence_matches_for_chunks(
    chunks: list[RetrievedChunk],
    expected: set[str],
    *,
    citation_expected: set[str] | None = None,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    citation_expected = citation_expected or set()
    for chunk in chunks:
        evidence_id = _chunk_evidence_id(chunk)
        if not evidence_id:
            continue
        aliases = _chunk_evidence_aliases(chunk)
        matched_expected = sorted(expected & set(aliases))
        matched_citation_expected = sorted(citation_expected & {evidence_id})
        matches.append(
            {
                "evidence_id": evidence_id,
                "alias_ids": aliases,
                "parent_evidence_id": next((item for item in aliases if item != evidence_id), None),
                "matched_expected_ids": matched_expected,
                "matched_parent_expected_ids": matched_expected,
                "matched_citation_expected_ids": matched_citation_expected,
            }
        )
    return matches


def check_generated_bullets(
    bullets: list[GeneratedBullet],
    *,
    evidence_by_id: dict[str, ProjectEvidenceRecord],
    original_resume_text: str,
    generated_sections: dict[str, str] | None = None,
    original_sections: list[ResumeSection] | None = None,
) -> list[dict[str, Any]]:
    original_skills = _extract_skills(original_resume_text)
    issues: list[dict[str, Any]] = []
    for bullet in bullets:
        evidence_ids = bullet.evidence_ids or _extract_evidence_ids(bullet.text)
        evidence_text = " ".join(evidence_by_id[item].text for item in evidence_ids if item in evidence_by_id)
        evidence_skill_text = " ".join(
            " ".join(evidence_by_id[item].skills) for item in evidence_ids if item in evidence_by_id
        )
        evidence_skills = _extract_skills(f"{evidence_text} {evidence_skill_text}")
        bullet_without_citations = EVIDENCE_CITATION_RE.sub("", bullet.text)
        bullet_skills = _extract_skills(bullet_without_citations)

        if not evidence_ids:
            issues.append(_issue(bullet, "missing_evidence_id"))
        unknown_ids = [item for item in evidence_ids if item not in evidence_by_id]
        if unknown_ids:
            issues.append(_issue(bullet, "unknown_evidence_id", {"evidence_ids": unknown_ids}))
        new_skills = sorted(bullet_skills - original_skills - evidence_skills)
        if new_skills:
            issues.append(_issue(bullet, "new_unverified_skills", {"skills": new_skills}))
        bullet_numbers = NUMBER_RE.findall(bullet.text)
        if bullet_numbers and not all(number in evidence_text for number in bullet_numbers):
            issues.append(_issue(bullet, "fabricated_metrics", {"numbers": bullet_numbers}))
        inflated = sorted(term for term in INFLATED_OWNERSHIP_TERMS if re.search(rf"\b{term}\b", bullet.text.lower()))
        if inflated and not any(term in evidence_text.lower() for term in inflated):
            issues.append(_issue(bullet, "inflated_ownership", {"terms": inflated}))
        if _has_raw_pii(bullet.text):
            issues.append(_issue(bullet, "raw_pii_leak"))
        if _has_raw_url(bullet.text):
            issues.append(_issue(bullet, "raw_url_leak"))
        if RAW_PLACEHOLDER_RE.search(bullet.text):
            issues.append(_issue(bullet, "unresolved_placeholder"))

    if generated_sections and original_sections:
        original_frozen = {
            section.normalized_title: _normalize_text(section.content)
            for section in original_sections
            if section.classification == "frozen"
        }
        for section_name, content in generated_sections.items():
            normalized = _normalize_label(section_name)
            if normalized in original_frozen and _normalize_text(content) != original_frozen[normalized]:
                issues.append(
                    {
                        "strategy": "section_validator",
                        "case_id": None,
                        "requirement_id": None,
                        "issue": "protected_section_mutation",
                        "section": section_name,
                    }
                )
    return issues


def _issue(bullet: GeneratedBullet, issue: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "strategy": bullet.strategy,
        "case_id": bullet.case_id,
        "requirement_id": bullet.requirement_id,
        "issue": issue,
        "section": bullet.section,
        **(extra or {}),
    }


def _summarize_issues(strategy: str, bullets: list[GeneratedBullet], issues: list[dict[str, Any]]) -> dict[str, Any]:
    strategy_issues = [item for item in issues if item.get("strategy") == strategy]
    issue_counts = _counts([item["issue"] for item in strategy_issues])
    bullet_count = len(bullets)
    bullets_with_issues = {
        (item.get("case_id"), item.get("requirement_id"))
        for item in strategy_issues
        if item.get("case_id") and item.get("requirement_id")
    }
    return {
        "bullet_count": bullet_count,
        "unsupported_issue_count": len(strategy_issues),
        "unsupported_issue_per_bullet": round(len(strategy_issues) / bullet_count, 6) if bullet_count else 0,
        "unsupported_bullet_count": len(bullets_with_issues),
        "unsupported_bullet_rate": round(len(bullets_with_issues) / bullet_count, 6) if bullet_count else 0,
        "issue_counts": issue_counts,
        "missing_evidence_id_rate": round(issue_counts.get("missing_evidence_id", 0) / bullet_count, 6) if bullet_count else 0,
        "raw_pii_leak_count": issue_counts.get("raw_pii_leak", 0),
        "raw_url_leak_count": issue_counts.get("raw_url_leak", 0),
        "unresolved_placeholder_count": issue_counts.get("unresolved_placeholder", 0),
        "protected_section_mutation_count": issue_counts.get("protected_section_mutation", 0),
    }

async def _run_retrieval_cases(
    db: AsyncSession,
    *,
    cases: list[JobDescriptionCase],
    evidence_by_source_id: dict[str, ProjectEvidenceRecord],
    k: int,
    acceptance_gate_enabled: bool,
    support_verifier_enabled: bool,
    requirement_cleaner_enabled: bool,
    retrieval_strategy: str,
    parent_to_children: dict[str, list[ProjectEvidenceRecord]] | None = None,
    embedding_index: EmbeddingRetrievalIndex | None = None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, dict[str, Any]]]]:
    requirement_results: list[dict[str, Any]] = []
    by_case_requirement: dict[str, dict[str, dict[str, Any]]] = {}
    for case in cases:
        by_case_requirement[case.id] = {}
        for requirement in case.expected_requirements:
            started = time.perf_counter()
            cleaner_decision = classify_requirement_for_retrieval(requirement.query, case_title=case.title)
            retrieval_query = cleaner_decision.cleaned_query if requirement_cleaner_enabled else requirement.query
            skipped_by_cleaner = requirement_cleaner_enabled and not cleaner_decision.should_retrieve
            candidate_limit = max(k * 8, 25) if (acceptance_gate_enabled or support_verifier_enabled) else k
            parent_chunks: list[RetrievedChunk] = []
            if skipped_by_cleaner:
                raw_chunks = []
                chunks = []
                acceptance_decisions = []
                support_decisions = []
            else:
                if retrieval_strategy == RETRIEVAL_STRATEGY_PARENT_CHILD_LEXICAL:
                    parent_chunks = await retrieve_document_chunks(
                        db,
                        user_id=RESUME_EVAL_USER_ID,
                        query=retrieval_query,
                        limit=candidate_limit,
                        surface="resume_tailoring_parent_eval",
                    )
                    raw_chunks = _expand_parent_chunks_to_child_chunks(
                        requirement=requirement,
                        retrieval_query=retrieval_query,
                        parent_chunks=parent_chunks,
                        parent_to_children=parent_to_children or {},
                        candidate_limit=max(candidate_limit * 4, 100),
                    )
                elif retrieval_strategy == RETRIEVAL_STRATEGY_OPENAI_EMBEDDING:
                    if embedding_index is None:
                        raise RuntimeError("Embedding retrieval strategy requires an embedding index.")
                    raw_chunks = _retrieve_embedding_chunks(
                        requirement=requirement,
                        case_title=case.title,
                        retrieval_query=retrieval_query,
                        embedding_index=embedding_index,
                        limit=candidate_limit,
                    )
                elif retrieval_strategy == RETRIEVAL_STRATEGY_OPENAI_HYBRID:
                    if embedding_index is None:
                        raise RuntimeError("Embedding retrieval strategy requires an embedding index.")
                    lexical_chunks = await retrieve_document_chunks(
                        db,
                        user_id=RESUME_EVAL_USER_ID,
                        query=retrieval_query,
                        limit=candidate_limit,
                        surface="resume_tailoring_eval",
                    )
                    embedding_chunks = _retrieve_embedding_chunks(
                        requirement=requirement,
                        case_title=case.title,
                        retrieval_query=retrieval_query,
                        embedding_index=embedding_index,
                        limit=candidate_limit,
                    )
                    raw_chunks = _merge_lexical_and_embedding_chunks(
                        lexical_chunks,
                        embedding_chunks,
                        limit=candidate_limit,
                    )
                else:
                    raw_chunks = await retrieve_document_chunks(
                        db,
                        user_id=RESUME_EVAL_USER_ID,
                        query=retrieval_query,
                        limit=candidate_limit,
                        surface="resume_tailoring_eval",
                    )
            if acceptance_gate_enabled and not skipped_by_cleaner:
                chunks, acceptance_decisions = _apply_evidence_acceptance_gate(
                    requirement,
                    raw_chunks,
                    evidence_by_source_id,
                    k=k,
                )
            elif not skipped_by_cleaner:
                chunks = raw_chunks[:k]
                acceptance_decisions = []
            if support_verifier_enabled and not skipped_by_cleaner:
                chunks, support_decisions = _apply_support_verifier(
                    requirement,
                    chunks,
                    evidence_by_source_id,
                    k=k,
                )
            elif not skipped_by_cleaner:
                support_decisions = []
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            expected = {str(item).upper() for item in requirement.parent_expected_ids}
            citation_expected = {str(item).upper() for item in requirement.citation_expected_ids}
            citation_label_status = (
                "labeled"
                if citation_expected
                else "unsupported"
                if not expected
                else "unlabeled_parent_only"
            )
            raw_matches = _evidence_matches_for_chunks(raw_chunks[:candidate_limit], expected, citation_expected=citation_expected)
            returned_matches = _evidence_matches_for_chunks(chunks[:k], expected, citation_expected=citation_expected)
            raw_returned_ids = [match["evidence_id"] for match in raw_matches]
            returned = [match["evidence_id"] for match in returned_matches]
            chunk_hits = [match for match in returned_matches if expected & set(match["alias_ids"])]
            citation_chunk_hits = [match for match in returned_matches if citation_expected & {match["evidence_id"]}]
            hit_expected_ids = sorted({item for match in chunk_hits for item in match["matched_expected_ids"]})
            hit_citation_expected_ids = sorted(
                {item for match in citation_chunk_hits for item in match["matched_citation_expected_ids"]}
            )
            first_hit_rank = next(
                (
                    index
                    for index, match in enumerate(returned_matches, start=1)
                    if expected & set(match["alias_ids"])
                ),
                None,
            )
            if expected:
                recall = len(hit_expected_ids) / len(expected)
                precision = len(chunk_hits) / len(returned) if returned else 0.0
                missing = 1 - recall
                mrr = 1 / first_hit_rank if first_hit_rank else 0.0
            else:
                recall = None
                precision = 1.0 if not returned else 0.0
                missing = None
                mrr = None
            first_citation_hit_rank = next(
                (
                    index
                    for index, match in enumerate(returned_matches, start=1)
                    if citation_expected & {match["evidence_id"]}
                ),
                None,
            )
            if citation_expected:
                citation_recall = len(hit_citation_expected_ids) / len(citation_expected)
                citation_precision = len(citation_chunk_hits) / len(returned) if returned else 0.0
                citation_missing = 1 - citation_recall
                citation_mrr = 1 / first_citation_hit_rank if first_citation_hit_rank else 0.0
            elif expected:
                citation_recall = None
                citation_precision = None
                citation_missing = None
                citation_mrr = None
            else:
                citation_recall = None
                citation_precision = 1.0 if not returned else 0.0
                citation_missing = None
                citation_mrr = None
            unrelated = (
                len([match for match in returned_matches if not expected & set(match["alias_ids"])]) / len(returned)
                if returned
                else 0.0
            )
            result = {
                "case_id": case.id,
                "case_title": case.title,
                "case_control_type": case.control_type,
                "requirement_id": requirement.id,
                "query": requirement.query,
                "retrieval_query": retrieval_query,
                "support_label": requirement.support_label,
                "control_type": requirement.control_type,
                "review_notes": requirement.review_notes,
                "expected_evidence_ids": requirement.expected_evidence_ids,
                "expected_parent_evidence_ids": requirement.parent_expected_ids,
                "expected_citation_evidence_ids": requirement.citation_expected_ids,
                "citation_label_status": citation_label_status,
                "requirement_cleaner_enabled": requirement_cleaner_enabled,
                "requirement_cleaner": cleaner_decision.to_dict(),
                "retrieval_skipped_by_cleaner": skipped_by_cleaner,
                "retrieval_strategy": retrieval_strategy,
                "parent_returned_evidence_ids": [
                    str(chunk.metadata.get("evidence_id", "")).upper()
                    for chunk in parent_chunks
                    if chunk.metadata.get("evidence_id")
                ],
                "raw_returned_evidence_ids": raw_returned_ids[:candidate_limit],
                "raw_returned_evidence_matches": raw_matches,
                "returned_evidence_ids": returned,
                "returned_evidence_aliases": [match["alias_ids"] for match in returned_matches],
                "returned_evidence_matches": returned_matches,
                "matched_expected_evidence_ids": hit_expected_ids,
                "matched_parent_expected_evidence_ids": hit_expected_ids,
                "matched_citation_expected_evidence_ids": hit_citation_expected_ids,
                "returned_titles": [chunk.title for chunk in chunks[:k]],
                "acceptance_gate_enabled": acceptance_gate_enabled,
                "acceptance_gate_version": RETRIEVAL_ACCEPTANCE_GATE_VERSION if acceptance_gate_enabled else None,
                "selected_candidate_count": len(returned),
                "accepted_candidate_count": sum(1 for decision in acceptance_decisions if decision.accepted),
                "raw_candidate_count": len(raw_returned_ids[:candidate_limit]),
                "rejected_candidate_count": sum(1 for decision in acceptance_decisions if not decision.accepted),
                "acceptance_decisions": [asdict(decision) for decision in acceptance_decisions],
                "support_verifier_enabled": support_verifier_enabled,
                "support_verifier_version": SUPPORT_VERIFIER_VERSION if support_verifier_enabled else None,
                "support_candidate_count": len(support_decisions),
                "support_accepted_candidate_count": sum(1 for decision in support_decisions if decision.accepted),
                "support_rejected_candidate_count": sum(1 for decision in support_decisions if not decision.accepted),
                "support_decisions": [decision.to_dict() for decision in support_decisions],
                "hit_count": len(hit_expected_ids),
                "parent_hit_count": len(hit_expected_ids),
                "citation_hit_count": len(hit_citation_expected_ids),
                "recall_at_k": recall,
                "precision_at_k": precision,
                "mrr": mrr,
                "missing_evidence_rate": missing,
                "parent_recall_at_k": recall,
                "parent_precision_at_k": precision,
                "parent_mrr": mrr,
                "parent_missing_evidence_rate": missing,
                "citation_recall_at_k": citation_recall,
                "citation_precision_at_k": citation_precision,
                "citation_mrr": citation_mrr,
                "citation_missing_evidence_rate": citation_missing,
                "unrelated_evidence_rate": unrelated,
                "latency_ms": latency_ms,
            }
            requirement_results.append(result)
            by_case_requirement[case.id][requirement.id] = result
    return requirement_results, by_case_requirement


def _aggregate_retrieval_metrics(requirement_results: list[dict[str, Any]], *, k: int) -> dict[str, Any]:
    latency_values = [float(item["latency_ms"]) for item in requirement_results]
    sorted_latency = sorted(latency_values)
    p95_index = min(int(len(sorted_latency) * 0.95), len(sorted_latency) - 1) if sorted_latency else 0
    parent_supported = [item for item in requirement_results if item.get("expected_parent_evidence_ids")]
    citation_labeled = [item for item in requirement_results if item.get("expected_citation_evidence_ids")]
    parent_only_unlabeled = [
        item
        for item in requirement_results
        if item.get("expected_parent_evidence_ids") and not item.get("expected_citation_evidence_ids")
    ]
    return {
        "k": k,
        "requirement_count": len(requirement_results),
        "requirements_with_expected_evidence": sum(1 for item in requirement_results if item["expected_evidence_ids"]),
        "requirements_without_expected_evidence": sum(1 for item in requirement_results if not item["expected_evidence_ids"]),
        "requirements_with_expected_parent_evidence": len(parent_supported),
        "requirements_with_expected_citation_evidence": len(citation_labeled),
        "parent_supported_without_citation_labels": len(parent_only_unlabeled),
        "recall_at_k_mean": _metric_mean([item["recall_at_k"] for item in requirement_results]),
        "precision_at_k_mean": _metric_mean([item["precision_at_k"] for item in requirement_results]),
        "mrr_mean": _metric_mean([item["mrr"] for item in requirement_results]),
        "parent_recall_at_k_mean": _metric_mean([item["parent_recall_at_k"] for item in requirement_results]),
        "parent_precision_at_k_mean": _metric_mean([item["parent_precision_at_k"] for item in requirement_results]),
        "parent_mrr_mean": _metric_mean([item["parent_mrr"] for item in requirement_results]),
        "citation_recall_at_k_mean": _metric_mean([item["citation_recall_at_k"] for item in requirement_results]),
        "citation_precision_at_k_mean": _metric_mean([item["citation_precision_at_k"] for item in requirement_results]),
        "citation_mrr_mean": _metric_mean([item["citation_mrr"] for item in requirement_results]),
        "missing_evidence_rate_mean": _metric_mean([item["missing_evidence_rate"] for item in requirement_results]),
        "parent_missing_evidence_rate_mean": _metric_mean([item["parent_missing_evidence_rate"] for item in requirement_results]),
        "citation_missing_evidence_rate_mean": _metric_mean([item["citation_missing_evidence_rate"] for item in requirement_results]),
        "unrelated_evidence_rate_mean": _metric_mean([item["unrelated_evidence_rate"] for item in requirement_results]),
        "latency_ms_mean": round(mean(latency_values), 3) if latency_values else 0,
        "latency_ms_p95": sorted_latency[p95_index] if sorted_latency else 0,
    }


def _aggregate_subset_metrics(items: list[dict[str, Any]], *, k: int) -> dict[str, Any]:
    metrics = _aggregate_retrieval_metrics(items, k=k) if items else {
        "k": k,
        "requirement_count": 0,
        "requirements_with_expected_evidence": 0,
        "requirements_without_expected_evidence": 0,
        "requirements_with_expected_parent_evidence": 0,
        "requirements_with_expected_citation_evidence": 0,
        "parent_supported_without_citation_labels": 0,
        "recall_at_k_mean": None,
        "precision_at_k_mean": None,
        "mrr_mean": None,
        "parent_recall_at_k_mean": None,
        "parent_precision_at_k_mean": None,
        "parent_mrr_mean": None,
        "citation_recall_at_k_mean": None,
        "citation_precision_at_k_mean": None,
        "citation_mrr_mean": None,
        "missing_evidence_rate_mean": None,
        "parent_missing_evidence_rate_mean": None,
        "citation_missing_evidence_rate_mean": None,
        "unrelated_evidence_rate_mean": None,
        "latency_ms_mean": 0,
        "latency_ms_p95": 0,
    }
    supported = [item for item in items if item["expected_evidence_ids"]]
    unsupported = [item for item in items if not item["expected_evidence_ids"]]
    metrics.update(
        {
            "row_count": len(items),
            "supported_row_count": len(supported),
            "unsupported_row_count": len(unsupported),
            "supported_rows_with_hit_count": sum(1 for item in supported if item["hit_count"] > 0),
            "unsupported_rows_with_returned_evidence_count": sum(1 for item in unsupported if item["returned_evidence_ids"]),
            "unsupported_false_support_rate": round(
                sum(1 for item in unsupported if item["returned_evidence_ids"]) / len(unsupported),
                6,
            )
            if unsupported
            else None,
        }
    )
    return metrics


def _aggregate_retrieval_breakdowns(requirement_results: list[dict[str, Any]], *, k: int) -> dict[str, Any]:
    breakdowns: dict[str, Any] = {}
    for field in ["support_label", "control_type"]:
        values = sorted({str(item.get(field) or "unknown") for item in requirement_results})
        breakdowns[field] = {
            value: _aggregate_subset_metrics(
                [item for item in requirement_results if str(item.get(field) or "unknown") == value],
                k=k,
            )
            for value in values
        }
    direct_or_partial = [item for item in requirement_results if item.get("support_label") in {"direct", "partial"}]
    unsupported = [item for item in requirement_results if item.get("support_label") == "none"]
    near_miss = [item for item in requirement_results if item.get("control_type") == "near_miss_control"]
    true_negative = [item for item in requirement_results if item.get("control_type") == "negative_control"]
    breakdowns["eval_slices"] = {
        "direct_or_partial": _aggregate_subset_metrics(direct_or_partial, k=k),
        "unsupported": _aggregate_subset_metrics(unsupported, k=k),
        "near_miss_control": _aggregate_subset_metrics(near_miss, k=k),
        "true_negative_control": _aggregate_subset_metrics(true_negative, k=k),
    }
    return breakdowns


def _aggregate_acceptance_gate_metrics(requirement_results: list[dict[str, Any]]) -> dict[str, Any]:
    rejection_reason_counts: dict[str, int] = {}
    missing_domain_group_counts: dict[str, int] = {}
    accepted_rows = 0
    raw_unsupported_rows_with_returns = 0
    accepted_unsupported_rows_with_returns = 0
    raw_candidate_count = 0
    accepted_candidate_count = 0
    rejected_candidate_count = 0
    for row in requirement_results:
        raw_candidate_count += int(row.get("raw_candidate_count") or 0)
        accepted_candidate_count += int(row.get("accepted_candidate_count") or 0)
        rejected_candidate_count += int(row.get("rejected_candidate_count") or 0)
        if row.get("returned_evidence_ids"):
            accepted_rows += 1
        if not row.get("expected_evidence_ids") and row.get("raw_returned_evidence_ids"):
            raw_unsupported_rows_with_returns += 1
        if not row.get("expected_evidence_ids") and row.get("returned_evidence_ids"):
            accepted_unsupported_rows_with_returns += 1
        for decision in row.get("acceptance_decisions") or []:
            if decision.get("accepted"):
                continue
            for reason in decision.get("reasons") or []:
                rejection_reason_counts[reason] = rejection_reason_counts.get(reason, 0) + 1
            for group in decision.get("missing_domain_groups") or []:
                missing_domain_group_counts[group] = missing_domain_group_counts.get(group, 0) + 1
    requirement_count = len(requirement_results)
    unsupported_count = sum(1 for row in requirement_results if not row.get("expected_evidence_ids"))
    return {
        "version": RETRIEVAL_ACCEPTANCE_GATE_VERSION,
        "enabled": bool(requirement_results and requirement_results[0].get("acceptance_gate_enabled")),
        "requirement_count": requirement_count,
        "raw_candidate_count": raw_candidate_count,
        "accepted_candidate_count": accepted_candidate_count,
        "rejected_candidate_count": rejected_candidate_count,
        "accepted_requirement_count": accepted_rows,
        "accepted_requirement_rate": round(accepted_rows / requirement_count, 6) if requirement_count else 0,
        "raw_unsupported_rows_with_returns": raw_unsupported_rows_with_returns,
        "accepted_unsupported_rows_with_returns": accepted_unsupported_rows_with_returns,
        "raw_unsupported_false_support_rate": round(raw_unsupported_rows_with_returns / unsupported_count, 6)
        if unsupported_count
        else None,
        "accepted_unsupported_false_support_rate": round(accepted_unsupported_rows_with_returns / unsupported_count, 6)
        if unsupported_count
        else None,
        "rejection_reason_counts": dict(sorted(rejection_reason_counts.items())),
        "missing_domain_group_counts": dict(sorted(missing_domain_group_counts.items())),
    }


def _aggregate_support_verifier_metrics(requirement_results: list[dict[str, Any]]) -> dict[str, Any]:
    label_counts: dict[str, int] = {}
    rejection_reason_counts: dict[str, int] = {}
    missing_domain_group_counts: dict[str, int] = {}
    candidate_count = 0
    accepted_candidate_count = 0
    rejected_candidate_count = 0
    supported_rows_rejected_to_zero = 0
    unsupported_rows_with_returns = 0
    for row in requirement_results:
        candidate_count += int(row.get("support_candidate_count") or 0)
        accepted_candidate_count += int(row.get("support_accepted_candidate_count") or 0)
        rejected_candidate_count += int(row.get("support_rejected_candidate_count") or 0)
        if row.get("expected_evidence_ids") and row.get("support_candidate_count") and not row.get("returned_evidence_ids"):
            supported_rows_rejected_to_zero += 1
        if not row.get("expected_evidence_ids") and row.get("returned_evidence_ids"):
            unsupported_rows_with_returns += 1
        for decision in row.get("support_decisions") or []:
            label = str(decision.get("label") or "unknown")
            label_counts[label] = label_counts.get(label, 0) + 1
            if decision.get("accepted"):
                continue
            for reason in decision.get("reasons") or []:
                rejection_reason_counts[reason] = rejection_reason_counts.get(reason, 0) + 1
            for group in decision.get("missing_domain_groups") or []:
                missing_domain_group_counts[group] = missing_domain_group_counts.get(group, 0) + 1
    supported_count = sum(1 for row in requirement_results if row.get("expected_evidence_ids"))
    unsupported_count = sum(1 for row in requirement_results if not row.get("expected_evidence_ids"))
    return {
        "version": SUPPORT_VERIFIER_VERSION,
        "enabled": bool(requirement_results and requirement_results[0].get("support_verifier_enabled")),
        "requirement_count": len(requirement_results),
        "candidate_count": candidate_count,
        "accepted_candidate_count": accepted_candidate_count,
        "rejected_candidate_count": rejected_candidate_count,
        "accepted_candidate_rate": round(accepted_candidate_count / candidate_count, 6) if candidate_count else None,
        "supported_rows_rejected_to_zero": supported_rows_rejected_to_zero,
        "supported_rows_rejected_to_zero_rate": round(supported_rows_rejected_to_zero / supported_count, 6)
        if supported_count
        else None,
        "unsupported_rows_with_returns": unsupported_rows_with_returns,
        "unsupported_false_support_rate": round(unsupported_rows_with_returns / unsupported_count, 6)
        if unsupported_count
        else None,
        "label_counts": dict(sorted(label_counts.items())),
        "rejection_reason_counts": dict(sorted(rejection_reason_counts.items())),
        "missing_domain_group_counts": dict(sorted(missing_domain_group_counts.items())),
    }


def _aggregate_requirement_cleaner_metrics(requirement_results: list[dict[str, Any]]) -> dict[str, Any]:
    category_counts: dict[str, int] = {}
    policy_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    skipped_supported = 0
    skipped_unsupported = 0
    for row in requirement_results:
        decision = row.get("requirement_cleaner") or {}
        category = str(decision.get("category") or "unknown")
        policy = str(decision.get("retrieval_policy") or "unknown")
        category_counts[category] = category_counts.get(category, 0) + 1
        policy_counts[policy] = policy_counts.get(policy, 0) + 1
        for reason in decision.get("reasons") or []:
            reason_text = str(reason)
            reason_counts[reason_text] = reason_counts.get(reason_text, 0) + 1
        if row.get("retrieval_skipped_by_cleaner"):
            if row.get("expected_evidence_ids"):
                skipped_supported += 1
            else:
                skipped_unsupported += 1
    requirement_count = len(requirement_results)
    skipped_count = sum(1 for row in requirement_results if row.get("retrieval_skipped_by_cleaner"))
    return {
        "enabled": bool(requirement_results and requirement_results[0].get("requirement_cleaner_enabled")),
        "requirement_count": requirement_count,
        "skipped_requirement_count": skipped_count,
        "retrieved_requirement_count": requirement_count - skipped_count,
        "skipped_supported_requirement_count": skipped_supported,
        "skipped_unsupported_requirement_count": skipped_unsupported,
        "category_counts": dict(sorted(category_counts.items())),
        "retrieval_policy_counts": dict(sorted(policy_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
    }


def _artifact_report(artifact: dict[str, Any]) -> str:
    metrics = artifact["retrieval_metrics"]
    prompt = artifact["generation_quality"]["prompt_only"]
    grounded = artifact["generation_quality"]["evidence_grounded"]
    privacy = artifact["privacy_and_format_checks"]
    project_docs = artifact["project_doc_ingest"]
    recommendation = artifact["recommendation"]
    breakdowns = artifact.get("retrieval_breakdowns", {})
    support_breakdown = breakdowns.get("support_label", {})
    control_breakdown = breakdowns.get("control_type", {})
    gate = artifact.get("acceptance_gate", {})
    support_verifier = artifact.get("support_verifier", {})
    cleaner = artifact.get("requirement_cleaner", {})
    embedding = artifact.get("embedding_retrieval", {})
    return "\n".join(
        [
            "# Resume Tailoring Evidence Eval",
            "",
            "This is an offline eval artifact. Production resume tailoring behavior is unchanged.",
            "",
            "## Dataset",
            "",
            f"- Dataset version: `{artifact['dataset_version']}`",
            f"- Project evidence records: `{artifact['project_evidence_count']}`",
            f"- Indexed retrieval records: `{artifact.get('indexed_project_evidence_count', artifact['project_evidence_count'])}`",
            f"- Manual fixture evidence records: `{artifact['manual_project_evidence_count']}`",
            f"- Extracted resume-safe project-doc cards: `{artifact['extracted_resume_safe_evidence_count']}`",
            f"- JD cases: `{artifact['jd_case_count']}`",
            f"- Retriever: `{artifact['retriever_version']}`",
            f"- Retrieval strategy: `{artifact['metadata'].get('retrieval_strategy', RETRIEVAL_STRATEGY_LEXICAL)}`",
            f"- Embedding retrieval: `{embedding.get('enabled', False)}`",
            f"- Embedding model: `{embedding.get('model')}`",
            f"- Model calls: `{artifact['model_calls']['count']}`",
            "",
            "## Project Doc Ingest",
            "",
            f"- Project docs scanned: `{project_docs['summary']['project_doc_count']}`",
            f"- Preflight statuses: `{project_docs['summary']['preflight_status_counts']}`",
            f"- Preflight reasons: `{project_docs['summary']['preflight_reason_counts']}`",
            f"- Extracted evidence cards: `{project_docs['summary']['evidence_card_count']}`",
            f"- Resume-safe evidence cards: `{project_docs['summary']['resume_safe_card_count']}`",
            f"- Excluded/noise sections: `{project_docs['summary']['excluded_section_count']}`",
            f"- Excluded reasons: `{project_docs['summary']['excluded_reason_counts']}`",
            "",
            "## Retrieval Metrics",
            "",
            f"- Recall@{metrics['k']}: `{_percent(metrics['recall_at_k_mean'])}`",
            f"- Precision@{metrics['k']}: `{_percent(metrics['precision_at_k_mean'])}`",
            f"- MRR: `{metrics['mrr_mean']}`",
            f"- Parent recall@{metrics['k']}: `{_percent(metrics.get('parent_recall_at_k_mean'))}`",
            f"- Parent precision@{metrics['k']}: `{_percent(metrics.get('parent_precision_at_k_mean'))}`",
            f"- Citation-labeled requirements: `{metrics.get('requirements_with_expected_citation_evidence', 0)}`",
            f"- Citation recall@{metrics['k']}: `{_percent(metrics.get('citation_recall_at_k_mean'))}`",
            f"- Citation precision@{metrics['k']}: `{_percent(metrics.get('citation_precision_at_k_mean'))}`",
            f"- Missing evidence rate: `{_percent(metrics['missing_evidence_rate_mean'])}`",
            f"- Unrelated evidence rate: `{_percent(metrics['unrelated_evidence_rate_mean'])}`",
            f"- Mean latency: `{metrics['latency_ms_mean']} ms`",
            "",
            "## Acceptance Gate",
            "",
            f"- Gate enabled: `{gate.get('enabled')}`",
            f"- Gate version: `{gate.get('version')}`",
            f"- Raw candidates: `{gate.get('raw_candidate_count', 0)}`",
            f"- Accepted candidates: `{gate.get('accepted_candidate_count', 0)}`",
            f"- Rejected candidates: `{gate.get('rejected_candidate_count', 0)}`",
            f"- Raw unsupported false-support rate: `{_percent(gate.get('raw_unsupported_false_support_rate'))}`",
            f"- Accepted unsupported false-support rate: `{_percent(gate.get('accepted_unsupported_false_support_rate'))}`",
            f"- Rejection reasons: `{gate.get('rejection_reason_counts', {})}`",
            f"- Missing domain groups: `{gate.get('missing_domain_group_counts', {})}`",
            "",
            "## Pairwise Support Verifier",
            "",
            f"- Verifier enabled: `{support_verifier.get('enabled')}`",
            f"- Verifier version: `{support_verifier.get('version')}`",
            f"- Candidates checked: `{support_verifier.get('candidate_count', 0)}`",
            f"- Accepted candidates: `{support_verifier.get('accepted_candidate_count', 0)}`",
            f"- Rejected candidates: `{support_verifier.get('rejected_candidate_count', 0)}`",
            f"- Unsupported false-support rate after verifier: `{_percent(support_verifier.get('unsupported_false_support_rate'))}`",
            f"- Supported rows rejected to zero: `{support_verifier.get('supported_rows_rejected_to_zero', 0)}`",
            f"- Label counts: `{support_verifier.get('label_counts', {})}`",
            f"- Rejection reasons: `{support_verifier.get('rejection_reason_counts', {})}`",
            "",
            "## Requirement Cleaner",
            "",
            f"- Cleaner enabled: `{cleaner.get('enabled')}`",
            f"- Skipped requirements: `{cleaner.get('skipped_requirement_count', 0)}`",
            f"- Skipped supported requirements: `{cleaner.get('skipped_supported_requirement_count', 0)}`",
            f"- Skipped unsupported requirements: `{cleaner.get('skipped_unsupported_requirement_count', 0)}`",
            f"- Category counts: `{cleaner.get('category_counts', {})}`",
            f"- Reason counts: `{cleaner.get('reason_counts', {})}`",
            "",
            "## Retrieval Breakdown",
            "",
            "| Slice | Rows | Recall | Precision | Unsupported false support | Unrelated evidence |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
            *[
                _report_breakdown_row(f"support:{label}", values)
                for label, values in support_breakdown.items()
            ],
            *[
                _report_breakdown_row(f"control:{label}", values)
                for label, values in control_breakdown.items()
            ],
            "",
            "## Generation Quality",
            "",
            f"- Prompt-only unsupported bullet rate: `{_percent(prompt['unsupported_bullet_rate'])}`",
            f"- Evidence-grounded unsupported bullet rate: `{_percent(grounded['unsupported_bullet_rate'])}`",
            f"- Prompt-only unsupported issues per bullet: `{prompt['unsupported_issue_per_bullet']}`",
            f"- Evidence-grounded unsupported issues per bullet: `{grounded['unsupported_issue_per_bullet']}`",
            f"- Prompt-only missing evidence ID rate: `{_percent(prompt['missing_evidence_id_rate'])}`",
            f"- Evidence-grounded missing evidence ID rate: `{_percent(grounded['missing_evidence_id_rate'])}`",
            f"- Evidence-grounded generated requirements: `{grounded.get('generated_requirement_count', grounded['bullet_count'])}`",
            f"- Evidence-grounded abstentions: `{grounded.get('abstention_count', 0)}`",
            f"- Evidence-grounded correct abstentions: `{grounded.get('correct_abstention_count', 0)}`",
            f"- Evidence-grounded unsupported requirement generations: `{grounded.get('unsupported_requirement_generation_count', 0)}`",
            "",
            "## Privacy And Format",
            "",
            f"- Raw email leaks after sanitization: `{privacy['sanitizer']['raw_email_leaks']}`",
            f"- Raw phone leaks after sanitization: `{privacy['sanitizer']['raw_phone_leaks']}`",
            f"- Raw URL leaks after sanitization: `{privacy['sanitizer']['raw_url_leaks']}`",
            f"- Protected placeholders inserted: `{privacy['sanitizer']['protected_placeholder_count']}`",
            "",
            "## Recommendation",
            "",
            recommendation,
            "",
            "## Limitations",
            "",
            *[f"- {item}" for item in artifact["limitations"]],
            "",
        ]
    )


def _report_breakdown_row(label: str, values: dict[str, Any]) -> str:
    return (
        f"| `{label}` | {values.get('row_count', 0)} | "
        f"{_percent(values.get('recall_at_k_mean'))} | "
        f"{_percent(values.get('precision_at_k_mean'))} | "
        f"{_percent(values.get('unsupported_false_support_rate'))} | "
        f"{_percent(values.get('unrelated_evidence_rate_mean'))} |"
    )


def _write_artifacts(output_dir: Path, artifact: dict[str, Any], bullets: list[GeneratedBullet], records: list[ProjectEvidenceRecord]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metadata.json").write_text(json.dumps(artifact["metadata"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "metrics.json").write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "report.md").write_text(_artifact_report(artifact), encoding="utf-8")
    with (output_dir / "generated_bullets.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["case_id", "requirement_id", "strategy", "section", "text", "evidence_ids"])
        writer.writeheader()
        for bullet in bullets:
            row = asdict(bullet)
            row["evidence_ids"] = ",".join(bullet.evidence_ids)
            writer.writerow(row)
    with (output_dir / "evidence_cards.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "evidence_id",
                "parent_evidence_id",
                "granularity",
                "project_id",
                "title",
                "source_path",
                "source_section",
                "claim_text",
                "skills",
                "project_tags",
                "claim_type",
                "resume_safe",
                "evidence_strength",
                "preflight_status",
                "preflight_reasons",
            ],
        )
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "evidence_id": record.evidence_id,
                    "parent_evidence_id": record.parent_evidence_id or "",
                    "granularity": record.granularity,
                    "project_id": record.project_id,
                    "title": record.title,
                    "source_path": record.source_path,
                    "source_section": record.source_section,
                    "claim_text": record.text,
                    "skills": ",".join(record.skills),
                    "project_tags": ",".join(record.project_tags),
                    "claim_type": record.claim_type,
                    "resume_safe": str(record.resume_safe).lower(),
                    "evidence_strength": record.evidence_strength,
                    "preflight_status": record.preflight_status,
                    "preflight_reasons": ",".join(record.preflight_reasons),
                }
            )
    return output_dir


async def build_resume_tailoring_evidence_eval_artifact(
    *,
    project_dir: Path = DEFAULT_PROJECT_DIR,
    project_doc_dirs: list[Path] | None = None,
    jd_cases_path: Path = DEFAULT_JD_CASES,
    resume_path: Path = DEFAULT_RESUME,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    k: int = 3,
    include_manual_project_fixtures: bool = True,
    acceptance_gate_enabled: bool = True,
    support_verifier_enabled: bool = False,
    requirement_cleaner_enabled: bool = False,
    project_doc_granularity: str = PROJECT_DOC_GRANULARITY_SECTION,
    retrieval_strategy: str = RETRIEVAL_STRATEGY_LEXICAL,
    embedding_model: str = OPENAI_EMBEDDING_MODEL_DEFAULT,
) -> dict[str, Any]:
    if retrieval_strategy not in RETRIEVAL_STRATEGIES:
        raise ValueError(f"Unsupported retrieval strategy: {retrieval_strategy}")
    manual_project_records = load_project_evidence(project_dir) if include_manual_project_fixtures else []
    if retrieval_strategy == RETRIEVAL_STRATEGY_PARENT_CHILD_LEXICAL:
        project_doc_results = extract_project_doc_results(project_doc_dirs, granularity=PROJECT_DOC_GRANULARITY_SECTION)
        child_project_doc_results = extract_project_doc_results(project_doc_dirs, granularity=PROJECT_DOC_GRANULARITY_ATOMIC)
        indexed_project_doc_records = project_records_from_doc_results(project_doc_results)
        project_doc_records = project_records_from_doc_results(child_project_doc_results)
        indexed_project_records = [*manual_project_records, *indexed_project_doc_records]
        project_records = [*manual_project_records, *project_doc_records]
    else:
        project_doc_results = extract_project_doc_results(project_doc_dirs, granularity=project_doc_granularity)
        child_project_doc_results = []
        project_doc_records = project_records_from_doc_results(project_doc_results)
        indexed_project_records = [*manual_project_records, *project_doc_records]
        project_records = indexed_project_records
    _validate_unique_evidence_ids(project_records)
    _validate_unique_evidence_ids(indexed_project_records)
    project_doc_summary = summarize_project_doc_results(project_doc_results)
    child_project_doc_summary = summarize_project_doc_results(child_project_doc_results) if child_project_doc_results else None
    evidence_by_id = {record.evidence_id: record for record in project_records}
    evidence_by_source_id = {str(record.source_id): record for record in project_records}
    parent_to_children = _parent_to_child_records(project_records)
    embedding_index = (
        _build_openai_embedding_index(indexed_project_records, model=embedding_model)
        if retrieval_strategy in {RETRIEVAL_STRATEGY_OPENAI_EMBEDDING, RETRIEVAL_STRATEGY_OPENAI_HYBRID}
        else None
    )
    cases = load_jd_cases(jd_cases_path)
    original_resume = resume_path.read_text(encoding="utf-8")
    sanitizer = sanitize_resume_for_llm(original_resume)

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as db:
            db.add(User(id=RESUME_EVAL_USER_ID, google_id="resume-eval", email="resume-eval@apptrail.test", name="Resume Eval"))
            await db.flush()
            await index_project_evidence_records(db, user_id=RESUME_EVAL_USER_ID, records=indexed_project_records)
            await db.commit()

            requirement_results, retrieval_by_case = await _run_retrieval_cases(
                db,
                cases=cases,
                evidence_by_source_id=evidence_by_source_id,
                k=k,
                acceptance_gate_enabled=acceptance_gate_enabled,
                support_verifier_enabled=support_verifier_enabled,
                requirement_cleaner_enabled=requirement_cleaner_enabled,
                retrieval_strategy=retrieval_strategy,
                parent_to_children=parent_to_children,
                embedding_index=embedding_index,
            )
            traces = list((await db.execute(select(RetrievalTrace))).scalars().all())
    finally:
        await engine.dispose()

    prompt_bullets: list[GeneratedBullet] = []
    grounded_bullets: list[GeneratedBullet] = []
    for case in cases:
        prompt_bullets.extend(build_prompt_only_bullets(case))
        grounded_bullets.extend(build_evidence_grounded_bullets(case, retrieval_by_case[case.id], evidence_by_id))
    bullets = [*prompt_bullets, *grounded_bullets]
    issues = check_generated_bullets(
        bullets,
        evidence_by_id=evidence_by_id,
        original_resume_text=original_resume,
        original_sections=classify_resume_sections(original_resume),
    )

    retrieval_metrics = _aggregate_retrieval_metrics(requirement_results, k=k)
    retrieval_breakdowns = _aggregate_retrieval_breakdowns(requirement_results, k=k)
    acceptance_gate_metrics = _aggregate_acceptance_gate_metrics(requirement_results)
    support_verifier_metrics = _aggregate_support_verifier_metrics(requirement_results)
    requirement_cleaner_metrics = _aggregate_requirement_cleaner_metrics(requirement_results)
    embedding_query_text_count = (
        sum(1 for row in requirement_results if not row.get("retrieval_skipped_by_cleaner"))
        if embedding_index
        else 0
    )
    prompt_summary = _summarize_issues("prompt_only", prompt_bullets, issues)
    grounded_summary = _summarize_issues("evidence_grounded", grounded_bullets, issues)
    _add_grounded_generation_coverage(
        grounded_summary,
        cases=cases,
        grounded_bullets=grounded_bullets,
    )
    artifact = {
        "artifact": "resume_tailoring_evidence_eval",
        "dataset_version": DATASET_VERSION,
        "generated_at": _utcnow(),
        "project_evidence_count": len(project_records),
        "indexed_project_evidence_count": len(indexed_project_records),
        "manual_project_evidence_count": len(manual_project_records),
        "extracted_resume_safe_evidence_count": len(project_doc_records),
        "jd_case_count": len(cases),
        "retriever_version": RETRIEVER_VERSION,
        "acceptance_gate": acceptance_gate_metrics,
        "support_verifier": support_verifier_metrics,
        "requirement_cleaner": requirement_cleaner_metrics,
        "metadata": {
            "dataset_version": DATASET_VERSION,
            "generated_at": _utcnow(),
            "project_dir": str(project_dir),
            "include_manual_project_fixtures": include_manual_project_fixtures,
            "acceptance_gate_enabled": acceptance_gate_enabled,
            "acceptance_gate_version": RETRIEVAL_ACCEPTANCE_GATE_VERSION if acceptance_gate_enabled else None,
            "support_verifier_enabled": support_verifier_enabled,
            "support_verifier_version": SUPPORT_VERIFIER_VERSION if support_verifier_enabled else None,
            "requirement_cleaner_enabled": requirement_cleaner_enabled,
            "project_doc_granularity": project_doc_granularity,
            "retrieval_strategy": retrieval_strategy,
            "embedding_model": embedding_model if embedding_index else None,
            "project_doc_dirs": [str(path) for path in project_doc_dirs or []],
            "jd_cases_path": str(jd_cases_path),
            "resume_path": str(resume_path),
            "output_dir": str(output_dir),
            "private_project_support": "Pass --project-doc-dir with a local ignored directory containing markdown project docs.",
        },
        "project_doc_ingest": {
            "summary": project_doc_summary,
            "child_summary": child_project_doc_summary,
            "results": [result.to_dict() for result in project_doc_results],
            "child_results": [result.to_dict() for result in child_project_doc_results],
        },
        "embedding_retrieval": {
            "enabled": embedding_index is not None,
            "provider": embedding_index.provider if embedding_index else None,
            "model": embedding_index.model if embedding_index else None,
            "indexed_text_count": embedding_index.text_count if embedding_index else 0,
            "query_text_count": embedding_query_text_count,
            "total_embedded_text_count": (embedding_index.text_count + embedding_query_text_count) if embedding_index else 0,
            "dimension": embedding_index.dimension if embedding_index else 0,
        },
        "retrieval_metrics": retrieval_metrics,
        "retrieval_breakdowns": retrieval_breakdowns,
        "requirement_results": requirement_results,
        "generation_quality": {
            "prompt_only": prompt_summary,
            "evidence_grounded": grounded_summary,
            "issues": issues,
            "prompt_only_version": PROMPT_ONLY_VERSION,
            "evidence_grounded_version": EVIDENCE_GROUNDED_VERSION,
        },
        "privacy_and_format_checks": {
            "sanitizer": sanitizer.privacy_checks,
            "placeholder_counts": sanitizer.placeholder_counts,
            "section_classification": [asdict(section) for section in sanitizer.sections],
            "protected_sections_default": sorted(FROZEN_SECTION_TITLES),
            "editable_sections_default": sorted(EDITABLE_SECTION_TITLES),
        },
        "model_calls": {
            "count": 0,
            "cost_usd": 0,
            "latency_ms": 0,
            "note": "This eval run used deterministic local draft generation only.",
        },
        "trace_summary": {
            "trace_count": len(traces),
            "surfaces": sorted({trace.surface for trace in traces}),
            "statuses": _counts([trace.status for trace in traces]),
        },
        "recommendation": _recommendation(retrieval_metrics, prompt_summary, grounded_summary),
        "limitations": [
            (
                "Uses locally supplied private project markdown docs; generated artifacts are ignored and should be reviewed before sharing."
                if project_doc_dirs
                else "Uses sanitized committed fixtures, not a real resume or private project corpus."
            ),
            "Project-doc extraction is deterministic and heuristic-based; it will miss nuanced claims and may over-extract noisy bullets.",
            (
                "Uses OpenAI embeddings only in this explicit eval run; there is still no production vector index, reranker, or OpenSearch path."
                if embedding_index
                else "Uses lexical retrieval only; no embeddings, reranking, or OpenSearch."
            ),
            "Deterministic drafts are eval probes, not user-facing writing quality evidence.",
            "Evidence-grounded improvement should be read as reduced unsupported-claim flags in this fixture, not as a production quality claim.",
            "Private project markdown support is local-only and should stay under ignored paths unless sanitized.",
        ],
    }
    _write_artifacts(output_dir, artifact, bullets, project_records)
    return artifact


def _recommendation(
    retrieval_metrics: dict[str, Any],
    prompt_summary: dict[str, Any],
    grounded_summary: dict[str, Any],
) -> str:
    recall = retrieval_metrics.get("recall_at_k_mean") or 0
    grounded_missing_ids = grounded_summary.get("missing_evidence_id_rate", 1)
    prompt_missing_ids = prompt_summary.get("missing_evidence_id_rate", 0)
    grounded_unsupported = grounded_summary.get("unsupported_bullet_rate", 1)
    prompt_unsupported = prompt_summary.get("unsupported_bullet_rate", 0)
    if recall >= 0.8 and grounded_missing_ids < prompt_missing_ids and grounded_unsupported < prompt_unsupported:
        return (
            "Evidence-grounded tailoring is promising for continued offline work because it reduces missing evidence IDs "
            "on sanitized fixtures. Do not promote until real private project evidence and human-reviewed JD cases confirm the result."
        )
    return (
        "Evidence-grounded tailoring is not ready for promotion. Improve evidence coverage and rerun with human-reviewed "
        "private fixtures before considering embeddings or production UX changes."
    )


def build_resume_tailoring_evidence_eval_artifact_sync(**kwargs: Any) -> dict[str, Any]:
    return asyncio.run(build_resume_tailoring_evidence_eval_artifact(**kwargs))
