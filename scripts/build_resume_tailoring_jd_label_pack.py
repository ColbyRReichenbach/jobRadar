from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.database_url import normalize_asyncpg_database_url
from backend.services.evals.resume_project_ingest import extract_project_doc_results, summarize_project_doc_results
from backend.services.evals.resume_requirement_cleaner import classify_requirement_for_retrieval
from backend.services.evals.resume_tailoring_eval import ProjectEvidenceRecord, project_records_from_doc_results


DEFAULT_LOCAL_DATABASE_URL = "postgresql+asyncpg://apptrail:apptrail@localhost:5432/apptrail"
DEFAULT_OUTPUT_DIR = Path("docs/ai-artifacts/generated/resume-tailoring-jd-label-pack")

STOPWORDS = {
    "about",
    "across",
    "also",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
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
    "our",
    "that",
    "the",
    "their",
    "this",
    "to",
    "using",
    "with",
    "will",
    "you",
    "your",
}
REQUIREMENT_TERMS = {
    "ab testing",
    "agentic",
    "ai",
    "airflow",
    "analytics",
    "api",
    "bigquery",
    "ci/cd",
    "classification",
    "cloud",
    "c++",
    "campaign",
    "dashboard",
    "data analysis",
    "data science",
    "databricks",
    "deep learning",
    "docker",
    "evaluation",
    "experiment",
    "forecast",
    "generative ai",
    "genomics",
    "hypothesis",
    "insights",
    "large datasets",
    "lidar",
    "llm",
    "machine learning",
    "marketing",
    "metrics",
    "model",
    "monitoring",
    "nlp",
    "pipeline",
    "perception",
    "product",
    "python",
    "ranking",
    "recommendation",
    "regression",
    "reporting",
    "robotics",
    "ros",
    "sales",
    "salesforce",
    "search",
    "sensor fusion",
    "sequencing",
    "single-cell",
    "slam",
    "snowflake",
    "spark",
    "sql",
    "statistics",
    "tableau",
    "xgboost",
}
REQUIREMENT_SPLIT_PHRASES = [
    "Analyze",
    "Automate",
    "Build",
    "Collaborate",
    "Conduct",
    "Create",
    "Define",
    "Design",
    "Develop",
    "Devise",
    "Drive",
    "Evaluate",
    "Experience in",
    "Experience with",
    "Familiarity with",
    "Hands-on experience",
    "Help",
    "Implement",
    "Knowledge of",
    "Lead",
    "Leverage",
    "Maintain",
    "Monitor",
    "Partner",
    "Plan",
    "Proficiency with",
    "Provide",
    "Strong experience",
    "Strong technical",
    "Support",
    "Translate",
]
JD_HEADING_PREFIX_RE = re.compile(
    r"^(?:"
    r"about us|"
    r"basic qualifications|"
    r"job description|"
    r"preferred qualifications|"
    r"qualifications|"
    r"responsibilities|"
    r"the crown is yours|"
    r"what you.ll bring|"
    r"what you.ll do(?: as [^:]+)?|"
    r"what you.ll need"
    r")[:\s-]*",
    flags=re.IGNORECASE,
)
JD_HEADING_INLINE_RE = re.compile(
    r"\b(?:"
    r"Basic Qualifications|"
    r"Preferred Qualifications|"
    r"Qualifications|"
    r"Responsibilities|"
    r"What you.ll bring|"
    r"What you.ll do(?: as [^\\n:.]+)?|"
    r"What you.ll need"
    r")[:\s-]*",
    flags=re.IGNORECASE,
)
EXCLUDED_REQUIREMENT_TERMS = {
    "background check",
    "bachelor's degree",
    "bachelors degree",
    "dental",
    "eeo employer",
    "equal employment opportunity",
    "equal opportunity",
    "legal authorization",
    "masters, mba, jd, md",
    "master's degree",
    "medical, dental",
    "privacy policy",
    "salary range",
    "travel requirements",
    "u.s. applicants only",
    "visa sponsorship",
    "work authorization",
    "work hours",
}
LOW_SIGNAL_REQUIREMENT_PREFIXES = (
    "at ",
    "about ",
    "as part of ",
    "every scientist ",
    "join ",
    "progress starts ",
)
LOW_SIGNAL_REQUIREMENT_PHRASES = {
    "a role with",
    "active follow foundational",
    "challenged to harness",
    "constant learner mentality",
    "contribute to data sciences",
    " is seeking ",
    "modeling the culture",
    "target's culture",
    "team is building",
    "team partners across",
    "the chance to help",
    "your work will drive",
}
HIGH_SIGNAL_REQUIREMENT_PHRASES = {
    "a/b testing",
    "automated tools",
    "bigquery",
    "ci/cd",
    "containerization",
    "data acquisition",
    "data infrastructure",
    "data exploration",
    "data science solutions",
    "deploying end to end ml models",
    "docker",
    "experiment",
    "feature engineering",
    "hypothesis testing",
    "information retrieval",
    "lidar",
    "machine learning models",
    "market activation",
    "model development",
    "model evaluation",
    "monitoring model",
    "perception",
    "pipeline management",
    "python",
    "quota",
    "querying large databases",
    "reporting frameworks",
    "robotics",
    "salesforce",
    "scRNA-seq",
    "search indexing",
    "sensor fusion",
    "single-cell",
    "sql",
    "tableau dashboards",
}


@dataclass(frozen=True)
class SavedJob:
    id: str
    email: str
    company: str
    role_title: str
    location: str
    status: str
    salary: str
    job_url: str
    description_text: str

    @property
    def case_id(self) -> str:
        return _normalize_id(f"{self.company}_{self.role_title}")[:72]


@dataclass(frozen=True)
class RequirementCandidate:
    case_id: str
    requirement_id: str
    company: str
    role_title: str
    query: str
    cleaned_query: str
    requirement_category: str
    retrieval_policy: str
    cleaner_reasons: list[str]
    suggested_evidence_ids: list[str]
    suggested_evidence_titles: list[str]
    suggested_claims: list[str]


def _normalize_id(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower())
    return re.sub(r"_+", "_", text).strip("_") or "item"


def _tokenize(value: str) -> set[str]:
    tokens = {
        token.lower()
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9+.#/-]{1,}", value)
        if token.lower() not in STOPWORDS and len(token) > 2
    }
    if "machine" in tokens and "learning" in tokens:
        tokens.add("machine learning")
    if "generative" in tokens and "ai" in tokens:
        tokens.add("generative ai")
    if "data" in tokens and "science" in tokens:
        tokens.add("data science")
    if "data" in tokens and "analysis" in tokens:
        tokens.add("data analysis")
    return tokens


def _clean_sentence(value: str) -> str:
    text = re.sub(r"\s+", " ", value).strip(" -•\t\r\n")
    text = JD_HEADING_PREFIX_RE.sub("", text)
    text = re.sub(r"(?i)^as (?:a|an) [^,.]{0,140},\s*(?:you.ll\s+)?", "", text)
    text = re.sub(r"(?i)^as a key member of [^,.]{0,140},\s*(?:you will\s+)?", "", text)
    text = re.sub(r"(?i)^whether you [^,.]{0,180},\s*(?:you.ll be challenged to\s+)?", "", text)
    text = re.sub(r"(?i)^you will get the opportunity to\s+", "", text)
    text = re.sub(r"(?i)^through your [^,.]{0,180},\s*(?:you will\s+)?", "", text)
    text = re.sub(r"(?i)^(?:you.ll|you will)\s+", "", text)
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text.strip()


def _split_compound_requirement(text: str) -> list[str]:
    text = JD_HEADING_INLINE_RE.sub(". ", text)
    phrase_pattern = "|".join(re.escape(phrase) for phrase in sorted(REQUIREMENT_SPLIT_PHRASES, key=len, reverse=True))
    text = re.sub(rf"\s+(?=({phrase_pattern})\b)", ". ", text)
    return [item.strip(" .") for item in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text) if item.strip(" .")]


def _is_useful_requirement_text(text: str) -> bool:
    lowered = text.lower()
    words = text.split()
    if not 8 <= len(words) <= 42:
        return False
    if lowered.startswith(LOW_SIGNAL_REQUIREMENT_PREFIXES):
        return False
    if any(term in lowered for term in EXCLUDED_REQUIREMENT_TERMS):
        return False
    if any(phrase in lowered for phrase in LOW_SIGNAL_REQUIREMENT_PHRASES):
        return False
    if re.search(r"\b(?:masters?|mba|jd|md|bachelors?|phd)\b", lowered) and not any(
        term in lowered for term in ["machine learning", "data science", "analytics", "python", "sql", "llm", "ai/ml"]
    ):
        return False
    return any(term in lowered for term in REQUIREMENT_TERMS)


def _split_requirement_sentences(description: str) -> list[str]:
    normalized = description.replace("\u00a0", " ")
    raw_items: list[str] = []
    for line in normalized.splitlines():
        line = _clean_sentence(line)
        if not line:
            continue
        raw_items.extend(_split_compound_requirement(line))

    candidates: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = _clean_sentence(item)
        if not _is_useful_requirement_text(text):
            continue
        key = _normalize_id(text)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(text)
    return candidates


def _rank_requirement_sentences(sentences: list[str], role_title: str) -> list[str]:
    role_tokens = _tokenize(role_title)

    def score(sentence: str) -> tuple[int, int]:
        lowered = sentence.lower()
        term_hits = sum(1 for term in REQUIREMENT_TERMS if term in lowered)
        role_hits = len(_tokenize(sentence) & role_tokens)
        action_bonus = 2 if any(
            word in lowered
            for word in [
                "analyze",
                "automate",
                "build",
                "develop",
                "design",
                "evaluate",
                "implement",
                "model",
                "monitor",
                "own",
                "transform",
                "translate",
                "uncover",
            ]
        ) else 0
        high_signal_bonus = sum(1 for phrase in HIGH_SIGNAL_REQUIREMENT_PHRASES if phrase in lowered)
        overview_penalty = 2 if any(phrase in lowered for phrase in [" is seeking ", " team is building ", " ideal for someone "]) else 0
        low_signal_penalty = 4 if any(phrase in lowered for phrase in LOW_SIGNAL_REQUIREMENT_PHRASES) else 0
        return (term_hits + role_hits + action_bonus + high_signal_bonus - overview_penalty - low_signal_penalty, -len(sentence))

    return sorted(sentences, key=score, reverse=True)


def _evidence_search_text(record: ProjectEvidenceRecord) -> str:
    return " ".join(
        [
            record.title,
            record.project_id,
            record.text,
            record.source_section,
            record.claim_type,
            record.evidence_strength,
            " ".join(record.skills),
        ]
    )


def _suggest_evidence(query: str, records: list[ProjectEvidenceRecord], *, limit: int) -> list[ProjectEvidenceRecord]:
    query_tokens = _tokenize(query)
    query_lower = query.lower()

    def score(record: ProjectEvidenceRecord) -> tuple[float, str]:
        evidence_text = _evidence_search_text(record)
        evidence_tokens = _tokenize(evidence_text)
        overlap = len(query_tokens & evidence_tokens)
        phrase_hits = sum(2 for token in query_tokens if " " in token and token in evidence_text.lower())
        strength_bonus = {"high": 1.5, "medium": 0.75, "low": 0.0}.get(record.evidence_strength, 0.0)
        claim_bonus = 0.5 if record.claim_type in {"evaluation", "retrieval", "operations", "privacy_safety"} else 0.0
        if "frontend" in evidence_tokens and not any(term in query_lower for term in ["frontend", "react", "ui", "dashboard"]):
            claim_bonus -= 0.75
        return (overlap + phrase_hits + strength_bonus + claim_bonus, record.evidence_id)

    ranked = sorted(records, key=score, reverse=True)
    return [record for record in ranked if score(record)[0] > 0][:limit]


async def _load_saved_jobs(database_url: str, *, user_email: str | None, limit: int) -> list[SavedJob]:
    db_url, connect_args = normalize_asyncpg_database_url(database_url)
    engine = create_async_engine(db_url, connect_args=connect_args)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        """
                        select
                            a.id::text as id,
                            coalesce(u.email, '') as email,
                            coalesce(a.company, '') as company,
                            coalesce(a.role_title, '') as role_title,
                            coalesce(a.location, '') as location,
                            coalesce(a.status, '') as status,
                            coalesce(a.salary, '') as salary,
                            coalesce(a.job_url, '') as job_url,
                            coalesce(a.description_text, '') as description_text
                        from applications a
                        left join users u on u.id = a.user_id
                        where length(coalesce(a.description_text, '')) > 0
                          and (cast(:user_email as text) is null or u.email = cast(:user_email as text))
                        order by length(coalesce(a.description_text, '')) desc, a.applied_at desc
                        limit :limit
                        """
                    ),
                    {"user_email": user_email, "limit": limit},
                )
            ).mappings().all()
    finally:
        await engine.dispose()
    return [SavedJob(**dict(row)) for row in rows]


def _load_saved_jobs_json(path: Path, *, user_email: str | None, limit: int) -> list[SavedJob]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected saved JDs JSON list at {path}")
    jobs: list[SavedJob] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        email = str(item.get("email") or "")
        description = str(item.get("description_text") or "")
        if user_email and email != user_email:
            continue
        if not description.strip():
            continue
        jobs.append(
            SavedJob(
                id=str(item.get("id") or ""),
                email=email,
                company=str(item.get("company") or ""),
                role_title=str(item.get("role_title") or ""),
                location=str(item.get("location") or ""),
                status=str(item.get("status") or ""),
                salary=str(item.get("salary") or ""),
                job_url=str(item.get("job_url") or ""),
                description_text=description,
            )
        )
    return jobs[:limit]


def _load_extra_jobs_json(path: Path) -> list[SavedJob]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected extra JDs JSON list at {path}")
    jobs: list[SavedJob] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        description = str(item.get("description_text") or "")
        if not description.strip():
            continue
        jobs.append(
            SavedJob(
                id=str(item.get("id") or ""),
                email=str(item.get("email") or "external_control@local"),
                company=str(item.get("company") or ""),
                role_title=str(item.get("role_title") or ""),
                location=str(item.get("location") or ""),
                status=str(item.get("status") or "external_control"),
                salary=str(item.get("salary") or ""),
                job_url=str(item.get("job_url") or ""),
                description_text=description,
            )
        )
    return jobs


def _build_requirement_candidates(
    jobs: list[SavedJob],
    records: list[ProjectEvidenceRecord],
    *,
    requirements_per_job: int,
    evidence_suggestions: int,
) -> list[RequirementCandidate]:
    candidates: list[RequirementCandidate] = []
    for job in jobs:
        sentences = _rank_requirement_sentences(_split_requirement_sentences(job.description_text), job.role_title)
        for index, query in enumerate(sentences[:requirements_per_job], start=1):
            cleaner_decision = classify_requirement_for_retrieval(query, case_title=f"{job.company} - {job.role_title}")
            suggested = (
                _suggest_evidence(cleaner_decision.cleaned_query, records, limit=evidence_suggestions)
                if cleaner_decision.should_retrieve
                else []
            )
            candidates.append(
                RequirementCandidate(
                    case_id=job.case_id,
                    requirement_id=f"req_{index:02d}",
                    company=job.company,
                    role_title=job.role_title,
                    query=query,
                    cleaned_query=cleaner_decision.cleaned_query,
                    requirement_category=cleaner_decision.category,
                    retrieval_policy=cleaner_decision.retrieval_policy,
                    cleaner_reasons=cleaner_decision.reasons,
                    suggested_evidence_ids=[record.evidence_id for record in suggested],
                    suggested_evidence_titles=[record.title for record in suggested],
                    suggested_claims=[record.text for record in suggested],
                )
            )
    return candidates


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_evidence_cards(path: Path, records: list[ProjectEvidenceRecord]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "evidence_id",
                "project_id",
                "title",
                "source_path",
                "source_section",
                "claim_text",
                "skills",
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
                    "project_id": record.project_id,
                    "title": record.title,
                    "source_path": record.source_path,
                    "source_section": record.source_section,
                    "claim_text": record.text,
                    "skills": ", ".join(record.skills),
                    "claim_type": record.claim_type,
                    "resume_safe": str(record.resume_safe).lower(),
                    "evidence_strength": record.evidence_strength,
                    "preflight_status": record.preflight_status,
                    "preflight_reasons": ", ".join(record.preflight_reasons),
                }
            )


def _write_evidence_cards_compact(path: Path, records: list[ProjectEvidenceRecord]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "evidence_id",
                "project",
                "claim",
                "skills",
                "claim_type",
                "strength",
            ],
        )
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "evidence_id": record.evidence_id,
                    "project": record.title,
                    "claim": record.text,
                    "skills": ", ".join(record.skills),
                    "claim_type": record.claim_type,
                    "strength": record.evidence_strength,
                }
            )


def _candidate_label_key(item: RequirementCandidate) -> tuple[str, str, str]:
    return (f"{item.company} - {item.role_title}", "", item.query)


def _load_existing_compact_labels(path: Path) -> dict[tuple[str, str, str], dict[str, str]]:
    if not path.exists():
        return {}
    labels: dict[tuple[str, str, str], dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = (row.get("job", ""), row.get("requirement_id", ""), row.get("requirement", ""))
            if not all(key):
                continue
            labels[key] = {
                "expected_evidence_ids": row.get("expected_evidence_ids", ""),
                "support_label": row.get("support_label", ""),
                "review_notes": row.get("review_notes", ""),
            }
            labels[(row.get("job", ""), "", row.get("requirement", ""))] = labels[key]
    return labels


def _write_labeling_queue(
    path: Path,
    candidates: list[RequirementCandidate],
    *,
    existing_labels: dict[tuple[str, str, str], dict[str, str]] | None = None,
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "case_id",
                "requirement_id",
                "company",
                "role_title",
                "query",
                "cleaned_query",
                "requirement_category",
                "retrieval_policy",
                "cleaner_reasons",
                "expected_evidence_ids",
                "suggested_evidence_ids",
                "suggested_evidence_titles",
                "suggested_claims",
            ],
        )
        writer.writeheader()
        for item in candidates:
            label = (existing_labels or {}).get(_candidate_label_key(item), {})
            writer.writerow(
                {
                    "case_id": item.case_id,
                    "requirement_id": item.requirement_id,
                    "company": item.company,
                    "role_title": item.role_title,
                    "query": item.query,
                    "cleaned_query": item.cleaned_query,
                    "requirement_category": item.requirement_category,
                    "retrieval_policy": item.retrieval_policy,
                    "cleaner_reasons": " | ".join(item.cleaner_reasons),
                    "expected_evidence_ids": label.get("expected_evidence_ids", ""),
                    "suggested_evidence_ids": " | ".join(item.suggested_evidence_ids),
                    "suggested_evidence_titles": " | ".join(item.suggested_evidence_titles),
                    "suggested_claims": " || ".join(item.suggested_claims),
                }
            )


def _format_evidence_option(record_id: str, title: str, claim: str, index: int) -> str:
    return f"{index}. {record_id} | {title} | {claim}"


def _write_labeling_queue_compact(
    path: Path,
    candidates: list[RequirementCandidate],
    *,
    existing_labels: dict[tuple[str, str, str], dict[str, str]] | None = None,
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "row_num",
                "job",
                "requirement_id",
                "requirement",
                "cleaned_requirement",
                "requirement_category",
                "retrieval_policy",
                "cleaner_reasons",
                "expected_evidence_ids",
                "support_label",
                "review_notes",
                "top_suggested_evidence_ids",
                "evidence_options",
            ],
        )
        writer.writeheader()
        for index, item in enumerate(candidates, start=1):
            label = (existing_labels or {}).get(_candidate_label_key(item), {})
            top_ids = item.suggested_evidence_ids[:5]
            options = [
                _format_evidence_option(record_id, title, claim, option_index)
                for option_index, (record_id, title, claim) in enumerate(
                    zip(item.suggested_evidence_ids[:5], item.suggested_evidence_titles[:5], item.suggested_claims[:5]),
                    start=1,
                )
            ]
            writer.writerow(
                {
                    "row_num": index,
                    "job": f"{item.company} - {item.role_title}",
                    "requirement_id": item.requirement_id,
                    "requirement": item.query,
                    "cleaned_requirement": item.cleaned_query,
                    "requirement_category": item.requirement_category,
                    "retrieval_policy": item.retrieval_policy,
                    "cleaner_reasons": " | ".join(item.cleaner_reasons),
                    "expected_evidence_ids": label.get("expected_evidence_ids", ""),
                    "support_label": label.get("support_label", ""),
                    "review_notes": label.get("review_notes", ""),
                    "top_suggested_evidence_ids": " | ".join(top_ids),
                    "evidence_options": "\n".join(options),
                }
            )


def _write_readme(path: Path, *, jobs: list[SavedJob], records: list[ProjectEvidenceRecord], candidates: list[RequirementCandidate]) -> None:
    lines = [
        "# Resume Tailoring JD Label Pack",
        "",
        "This is a local offline labeling pack. It is designed to create human-reviewed JD requirement labels before running a real retrieval eval.",
        "",
        "## Contents",
        "",
        "- `saved_jds.json`: saved local application JDs exported from the app database.",
        "- `evidence_cards.csv`: resume-safe evidence cards extracted from project markdown reports.",
        "- `evidence_cards_compact.csv`: compact evidence lookup for manual review.",
        "- `jd_requirement_label_queue.csv`: candidate JD requirements with suggested evidence IDs. Fill `expected_evidence_ids` before treating this as eval truth.",
        "- `jd_requirement_label_queue_compact.csv`: compact labeling view with one requirement, one label field, and top evidence options per row.",
        "- `project_doc_ingest_summary.json`: preflight and extraction counts for the project docs.",
        "",
        "## Counts",
        "",
        f"- Saved JDs: `{len(jobs)}`",
        f"- Resume-safe evidence cards: `{len(records)}`",
        f"- Requirement candidates: `{len(candidates)}`",
        "",
        "## Labeling Rule",
        "",
        "Put reviewed supporting evidence IDs into `expected_evidence_ids`. Use `|` to separate multiple IDs. Leave it blank when the requirement is unsupported.",
        "",
        "In the compact queue, optional `support_label` values are `direct`, `partial`, `none`, or `unsure`. Use `direct` when the evidence supports the requirement cleanly. Use `partial` when the evidence supports the transferable skill but not the exact business domain or every qualifier in the requirement.",
        "",
        "Do not use `suggested_evidence_ids` as truth without review. Those are lexical suggestions to make labeling faster.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


async def _amain(args: argparse.Namespace) -> dict[str, Any]:
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.saved_jds_json:
        jobs = _load_saved_jobs_json(args.saved_jds_json, user_email=args.user_email, limit=args.limit)
    else:
        jobs = await _load_saved_jobs(args.database_url, user_email=args.user_email, limit=args.limit)
    for extra_path in args.extra_jds_json or []:
        jobs.extend(_load_extra_jobs_json(extra_path))
    project_doc_results = extract_project_doc_results(args.project_doc_dir)
    project_doc_summary = summarize_project_doc_results(project_doc_results)
    records = project_records_from_doc_results(project_doc_results)
    candidates = _build_requirement_candidates(
        jobs,
        records,
        requirements_per_job=args.requirements_per_job,
        evidence_suggestions=args.evidence_suggestions,
    )
    existing_labels = _load_existing_compact_labels(output_dir / "jd_requirement_label_queue_compact.csv")

    _write_json(output_dir / "saved_jds.json", [asdict(job) for job in jobs])
    _write_json(output_dir / "project_doc_ingest_summary.json", project_doc_summary)
    _write_evidence_cards(output_dir / "evidence_cards.csv", records)
    _write_evidence_cards_compact(output_dir / "evidence_cards_compact.csv", records)
    _write_labeling_queue(output_dir / "jd_requirement_label_queue.csv", candidates, existing_labels=existing_labels)
    _write_labeling_queue_compact(output_dir / "jd_requirement_label_queue_compact.csv", candidates, existing_labels=existing_labels)
    _write_readme(output_dir / "README.md", jobs=jobs, records=records, candidates=candidates)

    return {
        "output_dir": str(output_dir),
        "saved_jds": len(jobs),
        "resume_safe_evidence_cards": len(records),
        "requirement_candidates": len(candidates),
        "project_docs_scanned": project_doc_summary["project_doc_count"],
        "preflight_status_counts": project_doc_summary["preflight_status_counts"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a local JD requirement labeling pack for resume-tailoring retrieval evals.")
    parser.add_argument("--database-url", default=DEFAULT_LOCAL_DATABASE_URL)
    parser.add_argument("--saved-jds-json", type=Path, default=None)
    parser.add_argument("--extra-jds-json", type=Path, action="append", default=[])
    parser.add_argument("--user-email", default=None)
    parser.add_argument("--project-doc-dir", type=Path, action="append", default=[], required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--requirements-per-job", type=int, default=5)
    parser.add_argument("--evidence-suggestions", type=int, default=8)
    args = parser.parse_args()
    summary = asyncio.run(_amain(args))
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
