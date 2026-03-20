import asyncio
import json
import logging
import os

import openai

logger = logging.getLogger(__name__)

client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MODEL = "gpt-4o"


async def classify_email(body: str) -> dict:
    for attempt in range(3):
        try:
            response = await client.chat.completions.create(
                model=MODEL,
                max_tokens=500,
                messages=[
                    {"role": "system", "content": "Return only valid JSON. No preamble."},
                    {"role": "user", "content": body},
                ],
            )
            return json.loads(response.choices[0].message.content)
        except openai.RateLimitError:
            await asyncio.sleep(60)
        except openai.APIStatusError as e:
            if e.status_code == 529:  # overloaded
                await asyncio.sleep(2**attempt)
            elif attempt == 2:
                raise
        except json.JSONDecodeError:
            logger.error(f"OpenAI JSON parse failed on attempt {attempt}")
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
            response = await client.chat.completions.create(
                model=MODEL,
                max_tokens=1000,
                messages=[
                    {"role": "system", "content": "Return only valid JSON. No preamble."},
                    {"role": "user", "content": prompt},
                ],
            )
            return json.loads(response.choices[0].message.content)
        except openai.RateLimitError:
            await asyncio.sleep(60)
        except openai.APIStatusError as e:
            if e.status_code == 529:
                await asyncio.sleep(2**attempt)
            elif attempt == 2:
                raise
        except json.JSONDecodeError:
            logger.error(f"OpenAI JSON parse failed on attempt {attempt}")
            if attempt == 2:
                return {"title": None, "company": None, "location": None, "department": None, "description": None}
    return {"title": None, "company": None, "location": None, "department": None, "description": None}
