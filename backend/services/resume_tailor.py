"""Sprint 20: AI resume tailoring using GPT-4o.

Generates tailored resume versions per job application.
Critical: never invents experience, only reframes existing content.
"""

import logging

from backend.services import ai_orchestrator, ai_safety

logger = logging.getLogger(__name__)

TAILOR_TASK = ai_orchestrator.get_task("resume_tailor")
TAILOR_MODEL = TAILOR_TASK.model
SYSTEM_PROMPT = TAILOR_TASK.system_prompt or ""


async def tailor_resume(
    original_text: str,
    job_description: str,
    company: str = "",
    role: str = "",
    skills: list[str] | None = None,
    ai_enabled: bool = True,
) -> dict:
    """Generate a tailored resume version.

    Args:
        original_text: The user's current resume text
        job_description: The job listing description
        company: Target company name
        role: Target role title
        skills: User's parsed skills list
        ai_enabled: When False, skip LLM and return original with notice

    Returns:
        Dict with tailored_text, changes_summary, match_improvements
    """
    if not ai_enabled:
        ai_orchestrator.record_fallback(TAILOR_TASK, "disabled_by_consent", {"surface": "resume_tailor", "company": company, "role": role})
        return {
            "tailored_text": original_text,
            "changes_summary": "AI resume tailoring is disabled. Enable AI processing in Settings > Privacy & Data to use this feature.",
            "match_improvements": "",
            "is_fallback": True,
        }

    context_parts = []
    if company:
        context_parts.append(f"Target company: {company}")
    if role:
        context_parts.append(f"Target role: {role}")
    if skills:
        context_parts.append(f"Candidate's verified skills: {', '.join(skills)}")

    user_message = f"""Tailor this resume for the specified job.

{chr(10).join(context_parts)}

--- ORIGINAL RESUME ---
{original_text}

--- JOB DESCRIPTION ---
{job_description}

Remember: DO NOT invent any new experience or skills. Only reframe and reorder existing content."""

    try:
        result = await ai_safety.run_json_task(
            TAILOR_TASK,
            user_message,
            metadata={"surface": "resume_tailor", "company": company, "role": role},
            data_classes=[ai_safety.DATA_CLASS_CAREER_PRIVATE, ai_safety.DATA_CLASS_PUBLIC_RESEARCH],
            allow_identity=False,
            untrusted_input=True,
        )

        normalized = _normalize_tailor_result(
            result,
            original_text=original_text,
            verified_skills=skills or [],
        )
        if normalized is None:
            ai_orchestrator.record_fallback(TAILOR_TASK, "invalid_payload", {"surface": "resume_tailor", "company": company, "role": role})
            return _fallback_tailor(original_text, role, company)
        return normalized

    except Exception as e:
        logger.warning("Resume tailoring failed: %s", e)
        ai_orchestrator.record_fallback(TAILOR_TASK, "task_failure", {"surface": "resume_tailor", "company": company, "role": role})
        return _fallback_tailor(original_text, role, company)


def _fallback_tailor(original_text: str, role: str = "", company: str = "") -> dict:
    """Fallback when LLM is unavailable — returns original with suggestions."""
    return {
        "tailored_text": original_text,
        "changes_summary": f"Unable to generate AI tailoring for {role} at {company}. Showing original resume.",
        "match_improvements": "",
        "is_fallback": True,
    }


def _clean_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _extract_skill_names(text: str) -> set[str]:
    from backend.services.tech_extractor import extract_tech_stack

    return {item["name"].lower() for item in extract_tech_stack(text or "") if item.get("name")}


def _has_unverified_skill_additions(tailored_text: str, original_text: str, verified_skills: list[str]) -> bool:
    original_skills = _extract_skill_names(original_text)
    verified = {skill.strip().lower() for skill in verified_skills if isinstance(skill, str) and skill.strip()}
    tailored_skills = _extract_skill_names(tailored_text)
    additions = tailored_skills - original_skills - verified
    return bool(additions)


def _normalize_tailor_result(result: dict, original_text: str = "", verified_skills: list[str] | None = None) -> dict | None:
    tailored_text = _clean_text(result.get("tailored_text"))
    if not tailored_text:
        logger.warning("Resume tailor returned invalid payload with tailored_text missing")
        return None
    if original_text and _has_unverified_skill_additions(tailored_text, original_text, verified_skills or []):
        logger.warning("Resume tailor returned unverified skill additions")
        return None

    return {
        "tailored_text": tailored_text,
        "changes_summary": _clean_text(result.get("changes_summary")),
        "match_improvements": _clean_text(result.get("match_improvements")),
    }
