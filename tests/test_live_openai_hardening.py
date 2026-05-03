import os

import pytest


pytestmark = pytest.mark.asyncio


def _live_openai_enabled() -> bool:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    return os.getenv("RUN_LIVE_OPENAI_TESTS") == "1" and bool(api_key and api_key != "test-key")


@pytest.mark.skipif(not _live_openai_enabled(), reason="Set RUN_LIVE_OPENAI_TESTS=1 with a real OPENAI_API_KEY to run live OpenAI hardening tests.")
async def test_live_openai_email_classifier_runs_without_fallback(monkeypatch):
    """Opt-in provider test: intentionally calls OpenAI and fails if the provider path fails."""
    from backend.services import ai_safety
    from backend.services.email_classifier import VALID_CATEGORIES

    monkeypatch.setenv("TESTING", "0")

    payload = await ai_safety.run_json_task(
        "email_classifier",
        "From: Greenhouse <noreply@greenhouse.io>\nSubject: Application received\n\nThank you for applying to ExampleCo. We received your application.",
        metadata={"surface": "live_openai_hardening_test"},
        data_classes=[ai_safety.DATA_CLASS_UNTRUSTED_INBOUND, ai_safety.DATA_CLASS_CAREER_PRIVATE],
        allow_identity=True,
        untrusted_input=True,
    )

    assert payload["classification"] in VALID_CATEGORIES
    assert isinstance(payload.get("confidence"), (int, float))
