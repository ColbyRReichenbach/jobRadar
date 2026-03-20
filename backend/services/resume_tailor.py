"""Sprint 20: AI resume tailoring using GPT-4o.

Generates tailored resume versions per job application.
Critical: never invents experience, only reframes existing content.
"""

import json
import logging
import os

import openai

from backend.utils.retry import with_retry

logger = logging.getLogger(__name__)

client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

TAILOR_MODEL = "gpt-4o"

SYSTEM_PROMPT = """You are an expert resume writer who tailors existing resumes for specific job applications.

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
}"""


async def tailor_resume(
    original_text: str,
    job_description: str,
    company: str = "",
    role: str = "",
    skills: list[str] | None = None,
) -> dict:
    """Generate a tailored resume version.

    Args:
        original_text: The user's current resume text
        job_description: The job listing description
        company: Target company name
        role: Target role title
        skills: User's parsed skills list

    Returns:
        Dict with tailored_text, changes_summary, match_improvements
    """
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
        response = await with_retry(
            client.chat.completions.create,
            model=TAILOR_MODEL,
            max_tokens=4000,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
        )

        text = response.choices[0].message.content.strip()

        # Parse JSON response
        if text.startswith("{"):
            result = json.loads(text)
        else:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(text[start:end])
            else:
                result = {
                    "tailored_text": text,
                    "changes_summary": "AI generated tailored version",
                    "match_improvements": "",
                }

        return {
            "tailored_text": result.get("tailored_text", ""),
            "changes_summary": result.get("changes_summary", ""),
            "match_improvements": result.get("match_improvements", ""),
        }

    except Exception as e:
        logger.warning("Resume tailoring failed: %s", e)
        return _fallback_tailor(original_text, role, company)


def _fallback_tailor(original_text: str, role: str = "", company: str = "") -> dict:
    """Fallback when LLM is unavailable — returns original with suggestions."""
    return {
        "tailored_text": original_text,
        "changes_summary": f"Unable to generate AI tailoring for {role} at {company}. Showing original resume.",
        "match_improvements": "",
        "is_fallback": True,
    }
