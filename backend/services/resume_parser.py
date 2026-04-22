"""Resume parsing: PDF text extraction + LLM structured extraction."""

import json
import os
from typing import Any

from backend.services import ai_orchestrator


async def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfplumber."""
    import io
    import pdfplumber

    text_parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n\n".join(text_parts)


async def parse_resume(text: str, ai_enabled: bool = True) -> dict[str, Any]:
    """Parse resume text into structured profile using GPT-4o-mini."""
    if not ai_enabled or not ai_orchestrator.has_configured_api_key():
        ai_orchestrator.record_fallback(
            "resume_parser",
            "disabled_or_unconfigured",
            {"surface": "resume_parser", "ai_enabled": ai_enabled},
        )
        # Fallback: basic keyword extraction without LLM
        return _fallback_parse(text)

    prompt = f"""Extract structured information from this resume. Return ONLY valid JSON with these fields:
- skills: list of technical skills (e.g. ["Python", "React", "SQL"])
- education: list of objects with "institution", "degree", "field", "year"
- experience_years: estimated total years of professional experience (integer)
- tools: list of tools/platforms (e.g. ["Git", "Docker", "AWS"])
- certifications: list of certification names

Resume text:
{text[:8000]}"""

    try:
        return await ai_orchestrator.run_json_task(
            "resume_parser",
            prompt,
            metadata={"surface": "resume_parser"},
        )
    except Exception:
        ai_orchestrator.record_fallback("resume_parser", "task_failure", {"surface": "resume_parser"})

    return _fallback_parse(text)


def _fallback_parse(text: str) -> dict[str, Any]:
    """Basic keyword extraction without LLM."""
    from backend.services.tech_extractor import extract_tech_stack

    tech = extract_tech_stack(text)
    skills = [t["name"] for t in tech]

    return {
        "skills": skills,
        "education": [],
        "experience_years": None,
        "tools": [],
        "certifications": [],
    }
