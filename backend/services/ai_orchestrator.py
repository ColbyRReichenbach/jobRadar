"""Shared AI orchestration for prompt-backed OpenAI tasks."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import openai
from sqlalchemy.ext.asyncio import AsyncSession

from backend.metrics import observe_ai_fallback, observe_ai_task
from backend.services.ai_usage import TokenUsage, record_model_call

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PromptChangelogEntry:
    date: str
    version: str
    change: str
    reason: str


@dataclass(frozen=True)
class AiTaskConfig:
    name: str
    model: str
    max_tokens: int
    prompt_version: str
    service_path: str
    purpose: str
    fallback_behavior: str
    user_prompt_template: str
    system_prompt: str | None = None
    extra_sections: tuple[tuple[str, str], ...] = ()
    changelog: tuple[PromptChangelogEntry, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AiTaskRunResult:
    payload: dict[str, Any]
    task: str
    model: str
    prompt_version: str
    duration_ms: float
    retries: int
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_estimate_cents: int | None = None
    model_call_id: uuid.UUID | None = None


AI_TASKS: dict[str, AiTaskConfig] = {
    "email_classifier": AiTaskConfig(
        name="email_classifier",
        model="gpt-4o-mini",
        max_tokens=300,
        prompt_version="v3",
        service_path="backend/services/email_classifier.py",
        purpose="Classify every incoming Gmail email into a job-search category with metadata.",
        fallback_behavior="Keyword-based rule engine using rejection/interview/action heuristics.",
        user_prompt_template="""From: {sender} <{sender_email}>
Subject: {subject}

{body[:4000]}""",
        system_prompt="""You are an email classifier for a job search tracking application.
Classify the email into exactly ONE category and extract key metadata.

Categories:
- interview_request: Scheduling an interview, phone screen, onsite, technical assessment invite
- rejection: Application rejected, not moving forward, position filled
- offer: Job offer, compensation details, offer letter
- action_item: Requires user action — complete assessment, fill form, provide references, sign document
- job_update: Application received/confirmed, status update, under review, moved to next stage
- conversation: Personal message from recruiter/hiring manager, networking, informational
- not_relevant: Marketing, newsletters, product updates, promotions, account notifications, unrelated to job search

Important exclusions:
- Developer tooling notifications such as GitHub, Railway, Vercel, Linear, billing emails, deployment alerts, repository updates, account security notices, invoices, and newsletters are NOT job search emails.
- Product updates from a company domain are still not_relevant unless they directly concern an active application, interview, or recruiting conversation.
- Nuanced rejection phrasing such as "we will not be moving forward", "not selected", "position has been filled", "have not been accepted", and "pursuing other candidates" should all classify as rejection.
- Recruiter or hiring-manager replies like "great speaking with you", "following up", and "can you chat this week" should classify as conversation when they are from a human sender.
- Promotional recruiting-adjacent content from LinkedIn, alumni groups, newsletters, community events, and vendor marketing is still not_relevant unless it is directly tied to an active application or interview process.
- Only treat a sender as human if it looks like a real individual or direct recruiter. Team aliases, no-reply mailboxes, newsletters, and system notifications are automated.

Return ONLY valid JSON with these fields:
{
  "classification": "<one of the categories above>",
  "confidence": <0.0-1.0>,
  "company_name": "<extracted company name or null>",
  "sender_role": "<recruiter/hiring_manager/hr/automated/unknown>",
  "key_sentence": "<the most important sentence from the email>",
  "summary": "<1-2 sentence summary>",
  "action_needed": <true/false>,
  "is_automated": <true if from ATS/no-reply, false if from a person>
}""",
        changelog=(
            PromptChangelogEntry("2026-03-01", "v1", "Initial prompt with 7 categories", "Launch"),
            PromptChangelogEntry(
                "2026-03-15",
                "v2",
                'Added "Important exclusions" block for developer tooling, nuanced rejection phrasing, recruiter conversation signals, and human-sender heuristics',
                "Reduce false positives and soft-rejection misses",
            ),
            PromptChangelogEntry("2026-03-19", "v3", "Switched from Claude Haiku to GPT-4o-mini", "Consolidate on OpenAI"),
        ),
    ),
    "draft_writer": AiTaskConfig(
        name="draft_writer",
        model="gpt-4o",
        max_tokens=500,
        prompt_version="v2",
        service_path="backend/services/draft_writer.py",
        purpose="Generate contextual email drafts for follow-ups, introductions, replies, and thank-you notes.",
        fallback_behavior="Template-based drafts per draft type.",
        user_prompt_template="""{type_prompt}

Context:
Draft type: {draft_type}
Company: {company}
Role: {role}
Contact: {contact_name}
Contact email: {contact_email}
Additional context: {additional_context}
Conversation history: {conversation_history}""",
        system_prompt="""You are an expert at writing professional job search emails.
Generate a draft email based on the context provided.

Rules:
1. Be concise and professional
2. Match the tone of any previous conversation (formal/casual)
3. Never sound desperate or pushy
4. Include specific details from the context (company name, role, conversation history)
5. Keep subject lines under 60 characters
6. Keep body under 150 words for follow-ups, 200 for introductions

Return ONLY valid JSON:
{
  "subject": "<email subject line>",
  "body": "<email body text>",
  "tone": "<formal|casual|neutral>"
}""",
        extra_sections=(
            (
                "Draft Type Prompts",
                "| Type | Prompt Template |\n|------|----------------|\n| follow_up | Write a polite follow-up email for a job application. It's been {days_since} days since the last activity. Keep it brief and professional. |\n| introduction | Write an introduction/networking email to {contact_name} at {company}. The user is interested in the {role} position. Make it warm but professional. |\n| reply | Write a reply to the most recent message in this email thread. Be helpful and responsive. |\n| thank_you | Write a thank-you email after an interview at {company} for the {role} position. |",
            ),
        ),
        changelog=(
            PromptChangelogEntry("2026-03-08", "v1", "Initial prompt with 4 draft types", "Sprint 14 launch"),
            PromptChangelogEntry("2026-03-19", "v2", "Switched from Claude Sonnet to GPT-4o", "Consolidate on OpenAI"),
        ),
    ),
    "resume_tailor": AiTaskConfig(
        name="resume_tailor",
        model="gpt-4o",
        max_tokens=4000,
        prompt_version="v2",
        service_path="backend/services/resume_tailor.py",
        purpose="Tailor existing resume content for a specific job application without inventing experience.",
        fallback_behavior='Returns the original resume with an "unable to generate" summary.',
        user_prompt_template="""Tailor this resume for the specified job.

Target company: {company}
Target role: {role}
Candidate's verified skills: {skills}

--- ORIGINAL RESUME ---
{original_text}

--- JOB DESCRIPTION ---
{job_description}

Remember: DO NOT invent any new experience or skills. Only reframe and reorder existing content.""",
        system_prompt="""You are an expert resume writer who tailors existing resumes for specific job applications.

CRITICAL RULES:
1. NEVER invent, fabricate, or add experiences, skills, or qualifications the candidate doesn't have
2. Only reframe, reorder, and emphasize existing content to better match the job description
3. Use keywords from the job description where they genuinely match existing experience
4. Reorder bullet points to lead with most relevant experience
5. Adjust phrasing to mirror the job posting's language where truthful
6. Keep the same overall structure and length

Return ONLY valid JSON:
{
  "tailored_text": "<the tailored resume text>",
  "changes_summary": "<bullet list of changes made and why>",
  "match_improvements": "<specific keywords/phrases aligned with the job>"
}""",
        changelog=(
            PromptChangelogEntry("2026-03-14", "v1", "Initial prompt with integrity rules", "Sprint 20 launch"),
            PromptChangelogEntry("2026-03-19", "v2", "Switched from Claude Sonnet to GPT-4o", "Consolidate on OpenAI"),
        ),
    ),
    "resume_parser": AiTaskConfig(
        name="resume_parser",
        model="gpt-4o-mini",
        max_tokens=2000,
        prompt_version="v2",
        service_path="backend/services/resume_parser.py",
        purpose="Extract structured skills, education, tools, and experience fields from resume text.",
        fallback_behavior="Regex-based tech stack extraction with empty structured fields for the rest.",
        user_prompt_template="""Extract structured information from this resume. Return ONLY valid JSON with these fields:
- skills: list of technical skills (e.g. ["Python", "React", "SQL"])
- education: list of objects with "institution", "degree", "field", "year"
- experience_years: estimated total years of professional experience (integer)
- tools: list of tools/platforms (e.g. ["Git", "Docker", "AWS"])
- certifications: list of certification names

Resume text:
{text[:8000]}""",
        system_prompt=None,
        changelog=(
            PromptChangelogEntry("2026-03-06", "v1", "Initial extraction prompt", "Sprint 5 launch"),
            PromptChangelogEntry("2026-03-19", "v2", "Switched from Claude Haiku to GPT-4o-mini", "Consolidate on OpenAI"),
        ),
    ),
    "legacy_email_classifier": AiTaskConfig(
        name="legacy_email_classifier",
        model="gpt-4o",
        max_tokens=500,
        prompt_version="v2",
        service_path="backend/services/claude_client.py",
        purpose="Legacy generic email classification compatibility shim.",
        fallback_behavior='Returns {"classification": "unknown", "color_code": "gray", "urgency": "low"}.',
        user_prompt_template="{body}",
        system_prompt="Return only valid JSON. No preamble.",
        changelog=(
            PromptChangelogEntry("2026-02-28", "v1", "Initial generic prompt", "Phase 1 launch"),
            PromptChangelogEntry("2026-03-19", "v2", "Switched from Claude Sonnet to GPT-4o", "Consolidate on OpenAI"),
        ),
    ),
    "html_job_extractor": AiTaskConfig(
        name="html_job_extractor",
        model="gpt-4o",
        max_tokens=1000,
        prompt_version="v2",
        service_path="backend/services/claude_client.py",
        purpose="Legacy HTML job extraction fallback when deterministic scraping misses.",
        fallback_behavior='Returns null fields for title, company, location, department, and description.',
        user_prompt_template="""Extract job posting information from this HTML content.
Return JSON only with keys: title, company, location, department, description.
If a field is not found, set it to null.

{html[:8000]}""",
        system_prompt="Return only valid JSON. No preamble.",
        changelog=(
            PromptChangelogEntry("2026-02-28", "v1", "Initial generic prompt", "Phase 1 launch"),
            PromptChangelogEntry("2026-03-19", "v2", "Switched from Claude Sonnet to GPT-4o", "Consolidate on OpenAI"),
        ),
    ),
    "research_brief_normalizer": AiTaskConfig(
        name="research_brief_normalizer",
        model=os.getenv("RADAR_BRIEF_MODEL", "gpt-5.1"),
        max_tokens=1200,
        prompt_version="v1",
        service_path="backend/services/research_radar/llm.py",
        purpose="Turn a Radar tracker plus AppTrail profile context into a strict research brief schema.",
        fallback_behavior="Production fails closed if OpenAI is unavailable; deterministic fallback is limited to tests/evals.",
        user_prompt_template="See `backend/services/research_radar/prompts.py::build_brief_normalization_prompt`.",
        system_prompt="""You normalize job-search research trackers into strict JSON.
Do not add narrative. Return only valid JSON that matches the requested schema.
Prefer explicit tracker inputs, then use the AppTrail profile context to fill reasonable gaps without inventing facts.""",
        changelog=(
            PromptChangelogEntry("2026-04-22", "v1", "Initial research brief normalizer", "Radar Research graph launch"),
        ),
    ),
    "research_planner": AiTaskConfig(
        name="research_planner",
        model=os.getenv("RADAR_PLANNER_MODEL", "gpt-5.1"),
        max_tokens=1400,
        prompt_version="v1",
        service_path="backend/services/research_radar/llm.py",
        purpose="Convert a normalized Radar brief into bounded research tasks with search queries and priorities.",
        fallback_behavior="Production fails closed if OpenAI is unavailable; deterministic fallback is limited to tests/evals.",
        user_prompt_template="See `backend/services/research_radar/prompts.py::build_research_plan_prompt`.",
        system_prompt="""You plan bounded web research tasks for a job-search assistant.
Return only valid JSON with a `tasks` array.
Do not create more tasks than requested. Each task must be concrete, externally searchable, and directly tied to the tracker objective.""",
        changelog=(
            PromptChangelogEntry("2026-04-22", "v1", "Initial research planner", "Radar Research graph launch"),
        ),
    ),
    "research_evidence_extractor": AiTaskConfig(
        name="research_evidence_extractor",
        model=os.getenv("RADAR_EVIDENCE_MODEL", "gpt-5.1"),
        max_tokens=1800,
        prompt_version="v1",
        service_path="backend/services/research_radar/llm.py",
        purpose="Extract grounded evidence items from fetched public documents for Radar reports.",
        fallback_behavior="Production fails closed if OpenAI is unavailable; deterministic fallback is limited to tests/evals.",
        user_prompt_template="See `backend/services/research_radar/prompts.py::build_evidence_extraction_prompt`.",
        system_prompt="""You extract only grounded evidence from public documents for a job-search research report.
Return only valid JSON with an `evidence_items` array.
Every evidence item must be directly supported by the supplied document and must not invent facts.""",
        changelog=(
            PromptChangelogEntry("2026-04-22", "v1", "Initial research evidence extractor", "Radar Research graph launch"),
        ),
    ),
    "research_report_writer": AiTaskConfig(
        name="research_report_writer",
        model=os.getenv("RADAR_REPORT_MODEL", "gpt-5.4"),
        max_tokens=3000,
        prompt_version="v1",
        service_path="backend/services/research_radar/llm.py",
        purpose="Write the structured Radar research report from validated evidence and diff data.",
        fallback_behavior="Production fails closed if OpenAI is unavailable; deterministic fallback is limited to tests/evals.",
        user_prompt_template="See `backend/services/research_radar/prompts.py::build_report_prompt`.",
        system_prompt="""You write grounded research reports for a job-search assistant.
Return only valid JSON with report title, summary markdown, and sections.
Every section must stay inside the provided evidence. Do not invent companies, roles, or claims.""",
        changelog=(
            PromptChangelogEntry("2026-04-22", "v1", "Initial research report writer", "Radar Research graph launch"),
        ),
    ),
    "research_report_verifier": AiTaskConfig(
        name="research_report_verifier",
        model=os.getenv("RADAR_VERIFY_MODEL", "gpt-5.1"),
        max_tokens=1200,
        prompt_version="v1",
        service_path="backend/services/research_radar/llm.py",
        purpose="Check report grounding, citation coverage, and tracker fit before Radar exposes the report as ready.",
        fallback_behavior="Production fails closed if OpenAI is unavailable; deterministic fallback is limited to tests/evals.",
        user_prompt_template="See `backend/services/research_radar/prompts.py::build_verification_prompt`.",
        system_prompt="""You verify whether a structured research report is grounded in its evidence.
Return only valid JSON describing unsupported claims, citation coverage, tracker fit, hallucination risk, and final readiness.""",
        changelog=(
            PromptChangelogEntry("2026-04-22", "v1", "Initial research report verifier", "Radar Research graph launch"),
        ),
    ),
    "copilot_answer": AiTaskConfig(
        name="copilot_answer",
        model=os.getenv("COPILOT_MODEL", "gpt-5.1"),
        max_tokens=1200,
        prompt_version="copilot_v1",
        service_path="backend/services/copilot/orchestrator.py",
        purpose="Answer job-search questions using only backend-retrieved, user-owned context with citations.",
        fallback_behavior="Production fails closed if OpenAI is unavailable; search-only fallback is limited to tests/evals.",
        user_prompt_template="See `backend/services/copilot/orchestrator.py::build_copilot_prompt`.",
        system_prompt="""You are AppTrail Copilot, a read-only job-search assistant.
Use only the provided retrieved context.
Do not claim access to records not listed in the context.
Every factual claim based on user data must cite retrieved document IDs.
Do not perform mutations, send emails, apply to jobs, or change records.
Return only valid JSON with answer, citations, and suggested_actions.""",
        changelog=(
            PromptChangelogEntry("2026-05-02", "copilot_v1", "Initial cited Copilot answer prompt", "Copilot backend launch"),
        ),
    ),
}


client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
_client_api_key: str | None = os.getenv("OPENAI_API_KEY")
_AI_METRICS: dict[str, dict[str, Any]] = {}


def get_task(name: str) -> AiTaskConfig:
    try:
        return AI_TASKS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown AI task: {name}") from exc


def has_configured_api_key() -> bool:
    if os.getenv("TESTING") == "1":
        return False
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    return bool(api_key and api_key != "test-key")


def get_openai_client() -> openai.AsyncOpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    global client, _client_api_key
    if _client_api_key != api_key:
        client = openai.AsyncOpenAI(api_key=api_key)
        _client_api_key = api_key
    return client


def parse_json_payload(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if not text:
        raise ValueError("Empty model response")

    if text.startswith("{"):
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("Model response was not a JSON object")

    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        parsed = json.loads(text[start:end])
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("Could not parse JSON object from model response")


def _should_retry(exc: Exception) -> bool:
    if isinstance(exc, (json.JSONDecodeError, ValueError)):
        return True
    if isinstance(exc, (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError)):
        return True
    if isinstance(exc, openai.APIStatusError):
        return exc.status_code == 429 or exc.status_code >= 500
    return False


def _retry_delay_seconds(exc: Exception, attempt: int) -> float:
    default_delay = float(2**attempt)
    if isinstance(exc, openai.RateLimitError):
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", {}) or {}
        retry_after = headers.get("retry-after") or headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
        return max(5.0, default_delay)
    if isinstance(exc, openai.APIStatusError) and exc.status_code >= 500:
        return default_delay
    if isinstance(exc, (json.JSONDecodeError, ValueError)):
        return 0.5 * (attempt + 1)
    return default_delay


def _task_metrics_row(task_config: AiTaskConfig) -> dict[str, Any]:
    row = _AI_METRICS.get(task_config.name)
    if row is None:
        row = {
            "task": task_config.name,
            "model": task_config.model,
            "prompt_version": task_config.prompt_version,
            "runs": 0,
            "successes": 0,
            "failures": 0,
            "fallbacks": 0,
            "retries": 0,
            "total_duration_ms": 0.0,
            "last_duration_ms": None,
            "last_run_at": None,
            "last_success_at": None,
            "last_failure_at": None,
            "last_error": None,
            "last_fallback_reason": None,
        }
        _AI_METRICS[task_config.name] = row
    return row


def record_fallback(task: str | AiTaskConfig, reason: str, metadata: dict[str, Any] | None = None) -> None:
    task_config = get_task(task) if isinstance(task, str) else task
    row = _task_metrics_row(task_config)
    row["fallbacks"] += 1
    row["last_fallback_reason"] = reason
    observe_ai_fallback(task=task_config.name, reason=reason)
    logger.info(
        "ai_task_fallback task=%s model=%s version=%s reason=%s metadata=%s",
        task_config.name,
        task_config.model,
        task_config.prompt_version,
        reason,
        metadata or {},
    )


def get_metrics_snapshot() -> dict[str, Any]:
    tasks = []
    for task_name in AI_TASKS:
        task_config = AI_TASKS[task_name]
        row = dict(_task_metrics_row(task_config))
        runs = row["runs"] or 0
        row["average_duration_ms"] = round(row["total_duration_ms"] / runs, 2) if runs else 0.0
        tasks.append(row)
    return {"tasks": tasks}


def reset_metrics_for_tests() -> None:
    _AI_METRICS.clear()


def render_prompt_registry_markdown() -> str:
    lines = [
        "# Prompt Registry",
        "",
        "Generated from `backend/services/ai_orchestrator.py`.",
        "",
        "**This file is NOT public.** It is for internal auditing and development only.",
        "",
        "---",
        "",
    ]

    for index, task in enumerate(AI_TASKS.values(), start=1):
        lines.extend(
            [
                f"## {index}. {task.name.replace('_', ' ').title()}",
                "",
                f"**Service:** `{task.service_path}`",
                f"**Model:** `{task.model}`",
                f"**Purpose:** {task.purpose}",
                f"**Max tokens:** {task.max_tokens}",
                "",
            ]
        )
        if task.system_prompt:
            lines.extend(["### System Prompt", "", "```", task.system_prompt, "```", ""])
        lines.extend(["### User Prompt Template", "", "```", task.user_prompt_template, "```", ""])
        for title, content in task.extra_sections:
            lines.extend([f"### {title}", "", content, ""])
        lines.extend(
            [
                "### Changelog",
                "",
                "| Date | Version | Change | Reason |",
                "|------|---------|--------|--------|",
            ]
        )
        for entry in task.changelog:
            lines.append(f"| {entry.date} | {entry.version} | {entry.change} | {entry.reason} |")
        lines.extend(["", f"**Fallback:** {task.fallback_behavior}", "", "---", ""])

    lines.extend(
        [
            "## Model Selection Rationale",
            "",
            "| Tier | Model | Use Case | Why |",
            "|------|-------|----------|-----|",
            "| High volume / Low cost | `gpt-4o-mini` | Email classifier, Resume parser | Runs on every email/resume; needs speed + low cost |",
            "| High quality | `gpt-4o` | Draft writer, Resume tailor, legacy extraction | User-facing output; quality matters more than cost |",
            "| Governed AI features | `gpt-5.x` | Copilot and Radar research reports | Production requires OpenAI and fails closed rather than silently substituting fallback outputs |",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def write_prompt_registry(output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(render_prompt_registry_markdown())


def _extract_usage_counts(response: Any) -> tuple[int | None, int | None]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None, None
    return (
        getattr(usage, "prompt_tokens", None),
        getattr(usage, "completion_tokens", None),
    )


async def run_json_task_with_metadata(
    task: str | AiTaskConfig,
    user_message: str,
    *,
    metadata: dict[str, Any] | None = None,
    max_tokens: int | None = None,
    db_session: AsyncSession | None = None,
    user_id: str | None = None,
) -> AiTaskRunResult:
    if not has_configured_api_key():
        raise RuntimeError("OPENAI_API_KEY is not configured")

    task_config = get_task(task) if isinstance(task, str) else task
    started = time.perf_counter()
    last_error: Exception | None = None
    retry_count = 0

    for attempt in range(3):
        try:
            request_kwargs: dict[str, Any] = {
                "model": task_config.model,
                "messages": [],
                "response_format": {"type": "json_object"},
            }
            token_key = "max_completion_tokens" if task_config.model.startswith("gpt-5") else "max_tokens"
            request_kwargs[token_key] = max_tokens or task_config.max_tokens
            if task_config.system_prompt:
                request_kwargs["messages"].append({"role": "system", "content": task_config.system_prompt})
            request_kwargs["messages"].append({"role": "user", "content": user_message})

            response = await get_openai_client().chat.completions.create(**request_kwargs)
            parsed = parse_json_payload(response.choices[0].message.content or "")
            tokens_in, tokens_out = _extract_usage_counts(response)
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            row = _task_metrics_row(task_config)
            row["runs"] += 1
            row["successes"] += 1
            row["retries"] += retry_count
            row["total_duration_ms"] += duration_ms
            row["last_duration_ms"] = duration_ms
            row["last_run_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            row["last_success_at"] = row["last_run_at"]
            row["last_error"] = None
            observe_ai_task(task=task_config.name, model=task_config.model, outcome="success", duration_seconds=duration_ms / 1000)
            logger.info(
                "ai_task_completed task=%s model=%s version=%s duration_ms=%s metadata=%s",
                task_config.name,
                task_config.model,
                task_config.prompt_version,
                duration_ms,
                metadata or {},
            )
            model_call_id = None
            if db_session is not None:
                model_call = await record_model_call(
                    db_session,
                    user_id=user_id or (metadata or {}).get("user_id"),
                    surface=str((metadata or {}).get("surface") or task_config.service_path),
                    task_name=task_config.name,
                    model=task_config.model,
                    prompt_version=task_config.prompt_version,
                    status="success",
                    latency_ms=duration_ms,
                    retry_count=retry_count,
                    token_usage=TokenUsage(
                        prompt_tokens=tokens_in,
                        output_tokens=tokens_out,
                    ),
                    request_metadata=metadata,
                    response_metadata={"response_format": "json_object"},
                )
                model_call_id = model_call.id
            return AiTaskRunResult(
                payload=parsed,
                task=task_config.name,
                model=task_config.model,
                prompt_version=task_config.prompt_version,
                duration_ms=duration_ms,
                retries=retry_count,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                model_call_id=model_call_id,
            )
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt == 2 or not _should_retry(exc):
                break
            retry_count += 1
            await asyncio.sleep(_retry_delay_seconds(exc, attempt))

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    row = _task_metrics_row(task_config)
    row["runs"] += 1
    row["failures"] += 1
    row["retries"] += retry_count
    row["total_duration_ms"] += duration_ms
    row["last_duration_ms"] = duration_ms
    row["last_run_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    row["last_failure_at"] = row["last_run_at"]
    row["last_error"] = repr(last_error)
    observe_ai_task(task=task_config.name, model=task_config.model, outcome="failure", duration_seconds=duration_ms / 1000)
    logger.warning(
        "ai_task_failed task=%s model=%s version=%s duration_ms=%s metadata=%s error=%s",
        task_config.name,
        task_config.model,
        task_config.prompt_version,
        duration_ms,
        metadata or {},
        repr(last_error),
    )
    if db_session is not None:
        await record_model_call(
            db_session,
            user_id=user_id or (metadata or {}).get("user_id"),
            surface=str((metadata or {}).get("surface") or task_config.service_path),
            task_name=task_config.name,
            model=task_config.model,
            prompt_version=task_config.prompt_version,
            status="failure",
            latency_ms=duration_ms,
            retry_count=retry_count,
            request_metadata=metadata,
            error_class=last_error.__class__.__name__ if last_error else "UnknownError",
            error_message=str(last_error) if last_error else None,
        )
    raise RuntimeError(f"AI task failed: {task_config.name}") from last_error


async def run_json_task(
    task: str | AiTaskConfig,
    user_message: str,
    *,
    metadata: dict[str, Any] | None = None,
    max_tokens: int | None = None,
    db_session: AsyncSession | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    return (
        await run_json_task_with_metadata(
            task,
            user_message,
            metadata=metadata,
            max_tokens=max_tokens,
            db_session=db_session,
            user_id=user_id,
        )
    ).payload
