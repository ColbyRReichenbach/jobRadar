import asyncio
import json
import logging
import os

import anthropic

logger = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

MODEL = "claude-sonnet-4-20250514"


async def classify_email(body: str) -> dict:
    for attempt in range(3):
        try:
            response = await client.messages.create(
                model=MODEL,
                max_tokens=500,
                system="Return only valid JSON. No preamble.",
                messages=[{"role": "user", "content": body}],
            )
            return json.loads(response.content[0].text)
        except anthropic.RateLimitError:
            await asyncio.sleep(60)
        except anthropic.APIStatusError as e:
            if e.status_code == 529:  # overloaded
                await asyncio.sleep(2**attempt)
            elif attempt == 2:
                raise
        except json.JSONDecodeError:
            logger.error(f"Claude JSON parse failed on attempt {attempt}")
            if attempt == 2:
                return {"classification": "unknown", "color_code": "gray", "urgency": "low"}
    return {"classification": "unknown", "color_code": "gray", "urgency": "low"}


async def extract_job_from_html(html: str) -> dict:
    prompt = (
        "Extract job posting information from this HTML content. "
        "Return JSON only with keys: title, company, location, department, description. "
        "If a field is not found, set it to null.\n\n"
        f"{html[:8000]}"
    )
    for attempt in range(3):
        try:
            response = await client.messages.create(
                model=MODEL,
                max_tokens=1000,
                system="Return only valid JSON. No preamble.",
                messages=[{"role": "user", "content": prompt}],
            )
            return json.loads(response.content[0].text)
        except anthropic.RateLimitError:
            await asyncio.sleep(60)
        except anthropic.APIStatusError as e:
            if e.status_code == 529:
                await asyncio.sleep(2**attempt)
            elif attempt == 2:
                raise
        except json.JSONDecodeError:
            logger.error(f"Claude JSON parse failed on attempt {attempt}")
            if attempt == 2:
                return {"title": None, "company": None, "location": None, "department": None, "description": None}
    return {"title": None, "company": None, "location": None, "department": None, "description": None}
