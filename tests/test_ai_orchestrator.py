from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.services.ai_orchestrator import render_prompt_registry_markdown, write_prompt_registry


def test_prompt_registry_renderer_includes_expected_sections():
    markdown = render_prompt_registry_markdown()

    assert "# Prompt Registry" in markdown
    assert "Generated from `backend/services/ai_orchestrator.py`." in markdown
    assert "## 1. Email Classifier" in markdown
    assert "**Service:** `backend/services/email_classifier.py`" in markdown
    assert "## 6. Html Job Extractor" in markdown
    assert "**Fallback:** Regex-based tech stack extraction with empty structured fields for the rest." in markdown


def test_write_prompt_registry_matches_renderer(tmp_path: Path):
    output_path = tmp_path / "PROMPT_REGISTRY.md"

    write_prompt_registry(str(output_path))

    assert output_path.read_text(encoding="utf-8") == render_prompt_registry_markdown()


@pytest.mark.asyncio
async def test_run_json_task_with_metadata_captures_usage(monkeypatch):
    from backend.services import ai_orchestrator

    async def _fake_create(**kwargs):
        assert kwargs["model"] == "gpt-4o-mini"
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"classification":"job_update"}'))],
            usage=SimpleNamespace(prompt_tokens=123, completion_tokens=45),
        )

    monkeypatch.setattr(ai_orchestrator, "has_configured_api_key", lambda: True)
    monkeypatch.setattr(
        ai_orchestrator.client.chat.completions,
        "create",
        _fake_create,
    )

    result = await ai_orchestrator.run_json_task_with_metadata(
        "email_classifier",
        "Classify this email.",
        metadata={"surface": "test"},
    )

    assert result.payload == {"classification": "job_update"}
    assert result.task == "email_classifier"
    assert result.model == "gpt-4o-mini"
    assert result.prompt_version == "v3"
    assert result.tokens_in == 123
    assert result.tokens_out == 45
