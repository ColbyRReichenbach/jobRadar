from pathlib import Path

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
