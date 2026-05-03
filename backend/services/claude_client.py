import logging

from backend.services import ai_orchestrator

logger = logging.getLogger(__name__)

client = ai_orchestrator.client

LEGACY_EMAIL_CLASSIFIER_TASK = ai_orchestrator.get_task("legacy_email_classifier")
HTML_JOB_EXTRACTOR_TASK = ai_orchestrator.get_task("html_job_extractor")
MODEL = LEGACY_EMAIL_CLASSIFIER_TASK.model


async def classify_email(body: str) -> dict:
    try:
        return await ai_orchestrator.run_json_task(
            LEGACY_EMAIL_CLASSIFIER_TASK,
            body,
            metadata={"surface": "legacy_email_classifier"},
        )
    except Exception:
        logger.error("Legacy classifier failed", exc_info=True)
        ai_orchestrator.record_fallback(
            LEGACY_EMAIL_CLASSIFIER_TASK,
            "task_failure",
            {"surface": "legacy_email_classifier"},
        )
        return {"classification": "unknown", "color_code": "gray", "urgency": "low"}


async def extract_job_from_html(html: str) -> dict:
    prompt = (
        "Extract job posting information from this HTML content. "
        "Return JSON only with keys: title, company, location, department, description. "
        "If a field is not found, set it to null.\n\n"
        f"{html[:8000]}"
    )
    try:
        return await ai_orchestrator.run_json_task(
            HTML_JOB_EXTRACTOR_TASK,
            prompt,
            metadata={"surface": "html_job_extractor"},
        )
    except Exception:
        logger.error("HTML job extraction failed", exc_info=True)
        ai_orchestrator.record_fallback(
            HTML_JOB_EXTRACTOR_TASK,
            "task_failure",
            {"surface": "html_job_extractor"},
        )
        return {"title": None, "company": None, "location": None, "department": None, "description": None}
