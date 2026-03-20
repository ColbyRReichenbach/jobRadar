"""Resume parsing: PDF text extraction + LLM structured extraction."""

import json
import os
from typing import Any

from backend.utils.retry import with_retry


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


async def parse_resume(text: str) -> dict[str, Any]:
    """Parse resume text into structured profile using GPT-4o-mini."""
    import openai

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key or api_key == "test-key":
        # Fallback: basic keyword extraction without LLM
        return _fallback_parse(text)

    client = openai.AsyncOpenAI(api_key=api_key)

    prompt = f"""Extract structured information from this resume. Return ONLY valid JSON with these fields:
- skills: list of technical skills (e.g. ["Python", "React", "SQL"])
- education: list of objects with "institution", "degree", "field", "year"
- experience_years: estimated total years of professional experience (integer)
- tools: list of tools/platforms (e.g. ["Git", "Docker", "AWS"])
- certifications: list of certification names

Resume text:
{text[:8000]}"""

    try:
        response = await with_retry(
            client.chat.completions.create,
            model="gpt-4o-mini",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content
        # Try to extract JSON from the response
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(content[start:end])
    except Exception:
        pass

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
