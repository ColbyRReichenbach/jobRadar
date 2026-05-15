"""Deterministic project markdown preflight and evidence extraction.

The functions here are local/offline helpers for resume-tailoring evals. They
do not call models or external services.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


PASS = "pass"
WARN = "warn"
BLOCK = "block"
PROJECT_DOC_GRANULARITY_SECTION = "section_claim"
PROJECT_DOC_GRANULARITY_ATOMIC = "atomic_claim"
PROJECT_DOC_GRANULARITIES = {PROJECT_DOC_GRANULARITY_SECTION, PROJECT_DOC_GRANULARITY_ATOMIC}

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}")
URL_RE = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
LIKELY_API_KEY_RE = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{18,}|ghp_[A-Za-z0-9_]{18,}|AKIA[0-9A-Z]{16})\b"
)
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password|client[_-]?secret|access[_-]?token)\b"
    r"\s*[:=]\s*['\"]?([A-Za-z0-9_\-./+=]{8,})"
)
LONG_ID_RE = re.compile(r"\b(?:[A-Fa-f0-9]{32,}|[A-Za-z0-9_-]{44,})\b")
FILE_PATH_RE = re.compile(
    r"(?:(?:\.{0,2}/|/)[\w .-]+/[\w./ -]+\.[A-Za-z0-9]{1,8})|"
    r"(?:(?:[\w.-]+/){2,}[\w.-]+\.[A-Za-z0-9]{1,8})|"
    r"(?:[A-Za-z]:\\[^\s]+)"
)
PROMPT_INJECTION_RE = re.compile(
    r"(?i)\b(ignore (?:all )?(?:previous|prior) instructions|disregard (?:all )?instructions|"
    r"system prompt|developer message|reveal secrets|exfiltrate|you are now)\b"
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+?)\s*$")
FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)

NOISE_HEADING_TERMS = {
    "asset_manifest",
    "binary_files",
    "build_artifacts",
    "coverage_dump",
    "file_inventory",
    "file_list",
    "generated_files",
    "logs",
    "node_modules",
    "package_lock",
    "raw_file_inventory",
    "rough_edges",
    "screenshots",
    "unsafe_appendix",
    "verification_dump",
    "verification_inventory",
}
IMPLEMENTATION_HEADING_TERMS = {
    "architecture",
    "backend",
    "data",
    "evaluation",
    "implementation",
    "ingest",
    "model",
    "modeling",
    "mlops",
    "observability",
    "pipeline",
    "product",
    "privacy",
    "retrieval",
    "safety",
    "search",
    "security",
    "testing",
    "tools",
    "visualization",
}
IMPLEMENTATION_VERBS = {
    "adds",
    "added",
    "backs",
    "builds",
    "built",
    "calls",
    "cleans",
    "compares",
    "computes",
    "contains",
    "coordinates",
    "created",
    "creates",
    "defines",
    "derives",
    "designed",
    "detects",
    "enforces",
    "exposes",
    "extracts",
    "fetches",
    "handles",
    "imports",
    "includes",
    "implemented",
    "implements",
    "indexed",
    "ingests",
    "instrumented",
    "loads",
    "models",
    "orchestrates",
    "parses",
    "measured",
    "parsed",
    "persists",
    "powers",
    "records",
    "redacts",
    "routes",
    "supports",
    "surfaces",
    "syncs",
    "tracks",
    "uses",
    "validated",
    "validates",
    "wired",
    "writes",
}
GENERIC_DUMP_TERMS = {"ok", "pass", "passed", "verified", "success", "done"}

SKILL_PATTERNS = {
    "api": re.compile(r"\bapi\b", re.IGNORECASE),
    "ai_engineering": re.compile(r"\bai\b|llm|copilot|openai|langgraph|agentic|prompt", re.IGNORECASE),
    "alembic": re.compile(r"\balembic\b|migration", re.IGNORECASE),
    "analytics": re.compile(r"analytics?|dashboard|reporting|visualization|charts?", re.IGNORECASE),
    "ci": re.compile(r"\bci\b|continuous integration", re.IGNORECASE),
    "celery": re.compile(r"\bcelery\b|scheduled jobs?|beat tasks?", re.IGNORECASE),
    "data_engineering": re.compile(r"etl|ingest|pipeline|warehouse|normalization|data source|schema", re.IGNORECASE),
    "docker": re.compile(r"\bdocker\b", re.IGNORECASE),
    "evals": re.compile(r"\bevals?\b|evaluation|metrics?", re.IGNORECASE),
    "fastapi": re.compile(r"\bfastapi\b", re.IGNORECASE),
    "frontend": re.compile(r"\bfrontend\b|react|next\\.js|nextjs|vite|typescript|ui|dashboard", re.IGNORECASE),
    "geospatial": re.compile(r"\bh3\b|geospatial|nearby|borough|property", re.IGNORECASE),
    "gmail": re.compile(r"\bgmail\b|google oauth|email classification", re.IGNORECASE),
    "json": re.compile(r"\bjson\b|schema", re.IGNORECASE),
    "markdown": re.compile(r"\bmarkdown\b", re.IGNORECASE),
    "ml": re.compile(r"machine learning|\\bml\\b|xgboost|scikit-learn|sklearn|shap|optuna|mlflow|model artifact", re.IGNORECASE),
    "mlops": re.compile(r"mlops|model monitoring|drift|retrain|release gate|champion|challenger", re.IGNORECASE),
    "node": re.compile(r"\bnode\b|playwright|esm", re.IGNORECASE),
    "opentelemetry": re.compile(r"\bopentelemetry\b|traces?", re.IGNORECASE),
    "pii_safety": re.compile(r"\bpii\b|privacy|redact|sanitize|preflight", re.IGNORECASE),
    "postgresql": re.compile(r"\bpostgres(?:ql)?\b|sqlalchemy", re.IGNORECASE),
    "python": re.compile(r"\bpython\b|pytest", re.IGNORECASE),
    "rag": re.compile(r"\brag\b", re.IGNORECASE),
    "redis": re.compile(r"\bredis\b|queue", re.IGNORECASE),
    "retrieval": re.compile(r"\bretrieval\b|search|chunk|citation", re.IGNORECASE),
    "security": re.compile(r"auth|jwt|csrf|rate[- ]limit|safety|security|governance|audit", re.IGNORECASE),
    "sql": re.compile(r"\bsql\b", re.IGNORECASE),
    "streamlit": re.compile(r"\bstreamlit\b", re.IGNORECASE),
    "zod": re.compile(r"\bzod\b|contract validation", re.IGNORECASE),
}


@dataclass(frozen=True)
class PreflightFinding:
    kind: str
    status: str
    message: str
    line_number: int
    sample: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProjectDocPreflightResult:
    source_file: str
    status: str
    reasons: list[str]
    findings: list[PreflightFinding]
    counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "status": self.status,
            "reasons": self.reasons,
            "findings": [finding.to_dict() for finding in self.findings],
            "counts": self.counts,
        }


@dataclass(frozen=True)
class MarkdownSection:
    title: str
    heading_path: str
    normalized_title: str
    level: int
    content: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class ExcludedSection:
    source_file: str
    heading_path: str
    reason: str
    line_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceCard:
    evidence_id: str
    project_name: str
    source_file: str
    source_section: str
    claim_text: str
    skill_tags: list[str]
    claim_type: str
    resume_safe: bool
    evidence_strength: str
    preflight_status: str
    preflight_reasons: list[str] = field(default_factory=list)
    parent_evidence_id: str | None = None
    granularity: str = PROJECT_DOC_GRANULARITY_SECTION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProjectDocExtractionResult:
    source_file: str
    project_name: str
    preflight: ProjectDocPreflightResult
    evidence_cards: list[EvidenceCard]
    excluded_sections: list[ExcludedSection]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "project_name": self.project_name,
            "preflight": self.preflight.to_dict(),
            "evidence_cards": [card.to_dict() for card in self.evidence_cards],
            "excluded_sections": [section.to_dict() for section in self.excluded_sections],
        }


def _normalize_label(value: Any) -> str:
    text = " ".join(str(value or "").split()).lower()
    text = re.sub(r"[\s/-]+", "_", text)
    text = re.sub(r"[^a-z0-9_]", "", text)
    return re.sub(r"_+", "_", text).strip("_")


def _safe_sample(line: str) -> str:
    sample = line.strip()[:220]
    sample = EMAIL_RE.sub("[EMAIL]", sample)
    sample = PHONE_RE.sub("[PHONE]", sample)
    sample = URL_RE.sub("[URL]", sample)
    sample = LIKELY_API_KEY_RE.sub("[API_KEY]", sample)
    sample = SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}=[SECRET]", sample)
    sample = LONG_ID_RE.sub("[LONG_ID]", sample)
    return sample


def _looks_sanitized_or_example(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in ["redacted", "example", "test", "fake", "dummy", "placeholder"])


def _add_finding(
    findings: list[PreflightFinding],
    *,
    kind: str,
    status: str,
    message: str,
    line_number: int,
    line: str,
) -> None:
    findings.append(
        PreflightFinding(
            kind=kind,
            status=status,
            message=message,
            line_number=line_number,
            sample=_safe_sample(line),
        )
    )


def preflight_markdown_text(text: str, *, source_file: str = "<memory>") -> ProjectDocPreflightResult:
    findings: list[PreflightFinding] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if EMAIL_RE.search(line):
            _add_finding(
                findings,
                kind="raw_email",
                status=WARN,
                message="Raw email address detected.",
                line_number=line_number,
                line=line,
            )
        if PHONE_RE.search(line):
            _add_finding(
                findings,
                kind="raw_phone",
                status=WARN,
                message="Raw phone number detected.",
                line_number=line_number,
                line=line,
            )
        if URL_RE.search(line):
            _add_finding(
                findings,
                kind="raw_url",
                status=WARN,
                message="Raw URL detected.",
                line_number=line_number,
                line=line,
            )
        if FILE_PATH_RE.search(line):
            _add_finding(
                findings,
                kind="file_path",
                status=WARN,
                message="Local or repository file path detected.",
                line_number=line_number,
                line=line,
            )
        if PROMPT_INJECTION_RE.search(line):
            _add_finding(
                findings,
                kind="prompt_injection",
                status=WARN,
                message="Suspicious prompt-injection text detected.",
                line_number=line_number,
                line=line,
            )
        if LIKELY_API_KEY_RE.search(line):
            status = WARN if _looks_sanitized_or_example(line) else BLOCK
            _add_finding(
                findings,
                kind="likely_api_key",
                status=status,
                message="Likely API key or provider token detected.",
                line_number=line_number,
                line=line,
            )
        secret_match = SECRET_ASSIGNMENT_RE.search(line)
        if secret_match:
            status = WARN if _looks_sanitized_or_example(line) else BLOCK
            _add_finding(
                findings,
                kind="secret_assignment",
                status=status,
                message="Secret-like assignment detected.",
                line_number=line_number,
                line=line,
            )
        long_id_match = LONG_ID_RE.search(line)
        if long_id_match and not LIKELY_API_KEY_RE.search(line):
            _add_finding(
                findings,
                kind="long_id",
                status=WARN,
                message="Long token or identifier detected.",
                line_number=line_number,
                line=line,
            )
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.kind] = counts.get(finding.kind, 0) + 1
    if any(finding.status == BLOCK for finding in findings):
        status = BLOCK
    elif findings:
        status = WARN
    else:
        status = PASS
    return ProjectDocPreflightResult(
        source_file=source_file,
        status=status,
        reasons=sorted(counts),
        findings=findings,
        counts=dict(sorted(counts.items())),
    )


def preflight_markdown_file(path: Path) -> ProjectDocPreflightResult:
    return preflight_markdown_text(path.read_text(encoding="utf-8"), source_file=str(path))


def _strip_frontmatter(text: str) -> str:
    return FRONTMATTER_RE.sub("", text, count=1)


def _parse_project_name(path: Path, text: str) -> str:
    frontmatter = FRONTMATTER_RE.match(text)
    if frontmatter:
        for line in frontmatter.group(0).splitlines():
            if line.lower().startswith("title:"):
                return line.split(":", 1)[1].strip()
            if line.lower().startswith("project:"):
                return line.split(":", 1)[1].strip()
    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match and len(match.group(1)) == 1:
            return match.group(2).strip()
    return path.stem.replace("_", " ").replace("-", " ").title()


def parse_markdown_sections(path: Path) -> tuple[str, list[MarkdownSection]]:
    text = path.read_text(encoding="utf-8")
    project_name = _parse_project_name(path, text)
    text = _strip_frontmatter(text)
    sections: list[MarkdownSection] = []
    heading_stack: list[tuple[int, str]] = []
    current_title = "Document"
    current_level = 0
    current_start = 1
    current_lines: list[str] = []

    def heading_path_for(title: str, level: int) -> str:
        stack = [(stack_level, stack_title) for stack_level, stack_title in heading_stack if stack_level < level]
        return " > ".join([item[1] for item in stack] + [title])

    def flush(end_line: int) -> None:
        content = "\n".join(current_lines).strip()
        if not content:
            return
        heading_path = heading_path_for(current_title, current_level)
        sections.append(
            MarkdownSection(
                title=current_title,
                heading_path=heading_path,
                normalized_title=_normalize_label(current_title),
                level=current_level,
                content=content,
                start_line=current_start,
                end_line=end_line,
            )
        )

    for line_number, line in enumerate(text.splitlines(), start=1):
        heading = HEADING_RE.match(line)
        if heading:
            flush(line_number - 1)
            current_level = len(heading.group(1))
            current_title = heading.group(2).strip()
            heading_stack[:] = [(level, title) for level, title in heading_stack if level < current_level]
            heading_stack.append((current_level, current_title))
            current_start = line_number + 1
            current_lines = []
        else:
            current_lines.append(line)
    flush(len(text.splitlines()))
    return project_name, sections


def _is_path_like_line(line: str) -> bool:
    return bool(FILE_PATH_RE.search(line)) or bool(re.match(r"^\s*[-*]?\s*[\w./-]+\.(png|jpg|gif|lock|map|svg|bin|zip)\b", line))


def _section_noise_reason(section: MarkdownSection) -> str | None:
    normalized_path = _normalize_label(section.heading_path)
    if any(term in normalized_path for term in NOISE_HEADING_TERMS):
        return "noise_heading"
    lines = [line for line in section.content.splitlines() if line.strip()]
    if not lines:
        return "empty_section"
    path_like = sum(1 for line in lines if _is_path_like_line(line))
    if len(lines) >= 8 and path_like / len(lines) >= 0.45:
        return "file_inventory"
    generic = sum(1 for line in lines if _normalize_label(line) in GENERIC_DUMP_TERMS or _normalize_label(line).startswith("pass_"))
    if len(lines) >= 6 and generic / len(lines) >= 0.6:
        return "verification_dump"
    return None


def _implementation_heavy(section: MarkdownSection) -> bool:
    normalized_path = _normalize_label(section.heading_path)
    if any(term in normalized_path for term in IMPLEMENTATION_HEADING_TERMS):
        return True
    lowered = section.content.lower()
    return sum(1 for verb in IMPLEMENTATION_VERBS if re.search(rf"\b{verb}\b", lowered)) >= 2


def _strip_markdown_links(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return re.sub(r"`([^`]+)`", r"\1", text)


def _claim_candidates(section: MarkdownSection) -> list[str]:
    candidates: list[str] = []
    in_code = False
    for line in section.content.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        match = BULLET_RE.match(line)
        if match:
            candidates.append(_strip_markdown_links(match.group(1)).strip())
    if candidates:
        return candidates
    paragraph = " ".join(line.strip() for line in section.content.splitlines() if line.strip())
    return [item.strip() for item in re.split(r"(?<=[.!?])\s+", paragraph) if item.strip()]


def _candidate_is_useful(text: str) -> bool:
    normalized = _normalize_label(text)
    lowered = text.lower()
    if len(text.split()) < 8:
        return False
    if normalized in GENERIC_DUMP_TERMS:
        return False
    if _is_path_like_line(text):
        return False
        return False
    if any(
        phrase in lowered
        for phrase in [
            "a caveat is",
            "archive contains no",
            "caveat",
            "cannot be verified",
            "client-side injection of secrets",
            "critical code-verified detail",
            "did not find",
            "did not run",
            "does not implement",
            "does not prove",
            "evidence boundary",
            "i did not",
            "important caveat",
            "maintenance risk",
            "not a backend",
            "not implemented",
            "not production",
            "not semantically analyzed",
            "one caution",
            "rough edge",
            "security tradeoff",
            "should not be claimed",
            "was not deserialized",
        ]
    ):
        return False
    if not any(re.search(rf"\b{re.escape(verb)}\b", lowered) for verb in IMPLEMENTATION_VERBS):
        return False
    return True


def _split_list_items(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip(" .")
    if not text:
        return []
    text = re.sub(r",?\s+and\s+", ", ", text)
    parts = [part.strip(" .") for part in text.split(",")]
    return [part for part in parts if len(part.split()) >= 2]


def _atomic_candidate_is_useful(text: str) -> bool:
    lowered = text.lower()
    if len(text.split()) < 5:
        return False
    if _is_path_like_line(text):
        return False
    has_skill = bool(infer_skill_tags(text))
    has_action = any(re.search(rf"\b{re.escape(verb)}\b", lowered) for verb in IMPLEMENTATION_VERBS)
    return has_skill or has_action


def split_claim_into_atomic_claims(claim_text: str) -> list[str]:
    """Split broad project-summary claims into smaller searchable evidence claims.

    This is intentionally conservative. It targets the common report pattern
    "the project supports/includes/exposes A, B, C" and leaves prose alone when
    the split would remove too much context.
    """

    normalized_claim = " ".join(claim_text.split())
    sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", normalized_claim) if item.strip()]
    atomic_claims: list[str] = []
    list_verb_pattern = re.compile(
        r"(?P<prefix>^.{0,180}?\b(?:supports|includes|exposes|creates|defines|provides|implements|uses|integrates|ships|"
        r"orchestrates|indexes|retrieves|evaluates|tracks|stores|validates|redacts|sanitizes)\b)\s+(?P<items>.+)$",
        re.IGNORECASE,
    )

    for sentence in sentences or [normalized_claim]:
        sentence = sentence.strip()
        match = list_verb_pattern.match(sentence)
        if not match or sentence.count(",") < 2:
            if _atomic_candidate_is_useful(sentence):
                atomic_claims.append(sentence)
            continue
        prefix = match.group("prefix").strip(" .")
        items = _split_list_items(match.group("items"))
        if len(items) < 3:
            if _atomic_candidate_is_useful(sentence):
                atomic_claims.append(sentence)
            continue
        for item in items:
            claim = f"{prefix} {item.strip()}.".replace(" ,", ",")
            if _atomic_candidate_is_useful(claim):
                atomic_claims.append(claim)

    deduped: list[str] = []
    seen: set[str] = set()
    for claim in atomic_claims:
        key = _normalize_label(claim)
        if key and key not in seen:
            seen.add(key)
            deduped.append(claim)
    return deduped or [normalized_claim]


def infer_skill_tags(text: str) -> list[str]:
    return sorted(tag for tag, pattern in SKILL_PATTERNS.items() if pattern.search(text))


def infer_claim_type(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ["privacy", "pii", "secret", "token", "sanitize", "preflight"]):
        return "privacy_safety"
    if any(term in lowered for term in ["eval", "metric", "recall", "precision", "mrr", "test", "artifact"]):
        return "evaluation"
    if any(term in lowered for term in ["retrieval", "search", "chunk", "citation", "evidence"]):
        return "retrieval"
    if any(term in lowered for term in ["trace", "logging", "latency", "ci", "dashboard"]):
        return "operations"
    return "implementation"


def infer_evidence_strength(text: str, skill_tags: list[str]) -> str:
    lowered = text.lower()
    has_action = any(re.search(rf"\b{verb}\b", lowered) for verb in IMPLEMENTATION_VERBS)
    has_validation = any(term in lowered for term in ["metric", "test", "eval", "ci", "artifact", "validated", "measured"])
    if has_action and skill_tags and has_validation:
        return "high"
    if has_action and skill_tags:
        return "medium"
    return "low"


def _stable_evidence_id(project_name: str, source_file: str, section_path: str, claim_text: str) -> str:
    project_slug = _normalize_label(project_name).upper()[:18] or "PROJECT"
    digest = hashlib.sha1(f"{source_file}|{section_path}|{claim_text}".encode("utf-8")).hexdigest()[:10].upper()
    return f"EV-{project_slug}-{digest}"


def _build_evidence_card(
    *,
    project_name: str,
    path: Path,
    section: MarkdownSection,
    claim_text: str,
    document_blocked: bool,
    preflight: ProjectDocPreflightResult,
    evidence_id: str,
    parent_evidence_id: str | None,
    granularity: str,
) -> EvidenceCard:
    claim_preflight = preflight_markdown_text(claim_text, source_file=str(path))
    skill_tags = infer_skill_tags(claim_text)
    strength = infer_evidence_strength(claim_text, skill_tags)
    resume_safe = not document_blocked and claim_preflight.status == PASS and strength in {"medium", "high"}
    card_preflight_status = BLOCK if document_blocked else claim_preflight.status
    card_preflight_reasons = preflight.reasons if document_blocked else claim_preflight.reasons
    return EvidenceCard(
        evidence_id=evidence_id,
        project_name=project_name,
        source_file=str(path),
        source_section=section.heading_path,
        claim_text=claim_text,
        skill_tags=skill_tags,
        claim_type=infer_claim_type(claim_text),
        resume_safe=resume_safe,
        evidence_strength=strength,
        preflight_status=card_preflight_status,
        preflight_reasons=card_preflight_reasons,
        parent_evidence_id=parent_evidence_id,
        granularity=granularity,
    )


def extract_evidence_cards_from_markdown(
    path: Path,
    *,
    granularity: str = PROJECT_DOC_GRANULARITY_SECTION,
) -> ProjectDocExtractionResult:
    if granularity not in PROJECT_DOC_GRANULARITIES:
        raise ValueError(f"Unsupported project doc granularity: {granularity}")
    raw_text = path.read_text(encoding="utf-8")
    preflight = preflight_markdown_text(raw_text, source_file=str(path))
    project_name, sections = parse_markdown_sections(path)
    cards: list[EvidenceCard] = []
    excluded: list[ExcludedSection] = []
    seen_claims: set[str] = set()
    document_blocked = preflight.status == BLOCK

    for section in sections:
        noise_reason = _section_noise_reason(section)
        if noise_reason:
            excluded.append(
                ExcludedSection(
                    source_file=str(path),
                    heading_path=section.heading_path,
                    reason=noise_reason,
                    line_count=len(section.content.splitlines()),
                )
            )
            continue
        if not _implementation_heavy(section):
            excluded.append(
                ExcludedSection(
                    source_file=str(path),
                    heading_path=section.heading_path,
                    reason="not_implementation_heavy",
                    line_count=len(section.content.splitlines()),
                )
            )
            continue
        for candidate in _claim_candidates(section):
            claim_text = " ".join(candidate.split())
            if not _candidate_is_useful(claim_text):
                continue
            claim_key = _normalize_label(claim_text)
            if claim_key in seen_claims:
                continue
            seen_claims.add(claim_key)
            parent_id = _stable_evidence_id(project_name, str(path), section.heading_path, claim_text)
            if granularity == PROJECT_DOC_GRANULARITY_SECTION:
                cards.append(
                    _build_evidence_card(
                        project_name=project_name,
                        path=path,
                        section=section,
                        claim_text=claim_text,
                        document_blocked=document_blocked,
                        preflight=preflight,
                        evidence_id=parent_id,
                        parent_evidence_id=None,
                        granularity=PROJECT_DOC_GRANULARITY_SECTION,
                    )
                )
                continue

            atomic_claims = split_claim_into_atomic_claims(claim_text)
            if len(atomic_claims) == 1 and _normalize_label(atomic_claims[0]) == claim_key:
                cards.append(
                    _build_evidence_card(
                        project_name=project_name,
                        path=path,
                        section=section,
                        claim_text=claim_text,
                        document_blocked=document_blocked,
                        preflight=preflight,
                        evidence_id=parent_id,
                        parent_evidence_id=None,
                        granularity=PROJECT_DOC_GRANULARITY_ATOMIC,
                    )
                )
                continue
            for index, atomic_claim in enumerate(atomic_claims, start=1):
                cards.append(
                    _build_evidence_card(
                        project_name=project_name,
                        path=path,
                        section=section,
                        claim_text=atomic_claim,
                        document_blocked=document_blocked,
                        preflight=preflight,
                        evidence_id=f"{parent_id}-A{index:02d}",
                        parent_evidence_id=parent_id,
                        granularity=PROJECT_DOC_GRANULARITY_ATOMIC,
                    )
                )
    return ProjectDocExtractionResult(
        source_file=str(path),
        project_name=project_name,
        preflight=preflight,
        evidence_cards=cards,
        excluded_sections=excluded,
    )


def markdown_files_from_dirs(project_doc_dirs: list[Path] | None) -> list[Path]:
    paths: list[Path] = []
    for directory in project_doc_dirs or []:
        if directory.is_file() and directory.suffix.lower() == ".md":
            paths.append(directory)
            continue
        if not directory.exists():
            continue
        paths.extend(sorted(path for path in directory.rglob("*.md") if path.is_file()))
    return sorted(set(paths))


def extract_project_doc_results(
    project_doc_dirs: list[Path] | None,
    *,
    granularity: str = PROJECT_DOC_GRANULARITY_SECTION,
) -> list[ProjectDocExtractionResult]:
    return [
        extract_evidence_cards_from_markdown(path, granularity=granularity)
        for path in markdown_files_from_dirs(project_doc_dirs)
    ]


def summarize_project_doc_results(results: list[ProjectDocExtractionResult]) -> dict[str, Any]:
    preflight_status_counts: dict[str, int] = {}
    preflight_reason_counts: dict[str, int] = {}
    excluded_reason_counts: dict[str, int] = {}
    for result in results:
        preflight_status_counts[result.preflight.status] = preflight_status_counts.get(result.preflight.status, 0) + 1
        for reason in result.preflight.reasons:
            preflight_reason_counts[reason] = preflight_reason_counts.get(reason, 0) + 1
        for section in result.excluded_sections:
            excluded_reason_counts[section.reason] = excluded_reason_counts.get(section.reason, 0) + 1
    cards = [card for result in results for card in result.evidence_cards]
    safe_cards = [card for card in cards if card.resume_safe]
    return {
        "project_doc_count": len(results),
        "preflight_status_counts": dict(sorted(preflight_status_counts.items())),
        "preflight_reason_counts": dict(sorted(preflight_reason_counts.items())),
        "evidence_card_count": len(cards),
        "resume_safe_card_count": len(safe_cards),
        "excluded_section_count": sum(len(result.excluded_sections) for result in results),
        "excluded_reason_counts": dict(sorted(excluded_reason_counts.items())),
        "claim_type_counts": dict(sorted(_count_values(card.claim_type for card in cards).items())),
        "evidence_strength_counts": dict(sorted(_count_values(card.evidence_strength for card in cards).items())),
        "granularity_counts": dict(sorted(_count_values(card.granularity for card in cards).items())),
        "child_card_count": sum(1 for card in cards if card.parent_evidence_id),
    }


def _count_values(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return counts
