"""Resume parsing: PDF text extraction + LLM structured extraction."""

from typing import Any

from backend.services import ai_orchestrator, ai_safety


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
        result = await ai_safety.run_json_task(
            "resume_parser",
            prompt,
            metadata={"surface": "resume_parser"},
            data_classes=[ai_safety.DATA_CLASS_CAREER_PRIVATE],
            allow_identity=False,
            untrusted_input=True,
        )
        return _normalize_parse_result(result)
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


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(text)
    return cleaned


def _normalize_education(value: object) -> list[dict[str, str | None]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str | None]] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if text:
                normalized.append({"institution": text, "degree": None, "field": None, "year": None})
            continue
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "institution": item.get("institution") if isinstance(item.get("institution"), str) else None,
                "degree": item.get("degree") if isinstance(item.get("degree"), str) else None,
                "field": item.get("field") if isinstance(item.get("field"), str) else None,
                "year": str(item["year"]) if item.get("year") is not None else None,
            }
        )
    return normalized


def _normalize_experience_years(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        years = int(float(value))
    except (TypeError, ValueError):
        return None
    return max(0, min(80, years))


def _normalize_parse_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "skills": _string_list(result.get("skills")),
        "education": _normalize_education(result.get("education")),
        "experience_years": _normalize_experience_years(result.get("experience_years")),
        "tools": _string_list(result.get("tools")),
        "certifications": _string_list(result.get("certifications")),
    }
