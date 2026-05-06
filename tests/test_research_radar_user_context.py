import uuid

import pytest


class Dumpable:
    def __init__(self, payload):
        self._payload = payload

    def model_dump(self):
        return self._payload


@pytest.mark.asyncio
async def test_radar_llm_nodes_preserve_missing_user_id(monkeypatch):
    from backend.services.research_radar.nodes import extract, normalize, plan, report, verify

    captured: dict[str, object] = {}

    async def _normalize(*args, user_id=None, **kwargs):
        captured["normalize"] = user_id
        return Dumpable({
            "ideal_role_titles": [],
            "target_domains": [],
            "target_companies": [],
            "target_locations": [],
            "remote_preferences": [],
        }), {"task": "normalize"}

    async def _plan(*args, user_id=None, **kwargs):
        captured["plan"] = user_id
        return [Dumpable({"task_id": "task-1"})], {"task": "plan"}

    async def _extract(*args, user_id=None, **kwargs):
        captured["extract"] = user_id
        return [Dumpable({"source_item_id": "source-1"})], {"task": "extract"}

    async def _report(*args, user_id=None, **kwargs):
        captured["report"] = user_id
        return Dumpable({"title": "Report"}), [Dumpable({"section_key": "summary"})], {"task": "report"}

    async def _verify(*args, user_id=None, **kwargs):
        captured["verify"] = user_id
        result = Dumpable({"status": "ready"})
        result.status = "ready"
        return result, {"task": "verify"}

    monkeypatch.setattr(normalize, "normalize_brief_with_metrics", _normalize)
    monkeypatch.setattr(plan, "plan_research_tasks_with_metrics", _plan)
    monkeypatch.setattr(extract, "extract_evidence_with_metrics", _extract)
    monkeypatch.setattr(report, "write_report_with_metrics", _report)
    monkeypatch.setattr(verify, "verify_report_with_metrics", _verify)

    base_state = {
        "tracker": {"depth": "quick", "max_search_queries": 1},
        "user_context": {},
        "normalized_brief": {"search_objective": "Find AI platform roles."},
        "source_items": [{"source_item_id": "source-1"}],
        "diff_summary": {},
        "evidence_items": [],
        "report_sections": [],
        "final_report": {},
    }

    await normalize.normalize_research_brief(base_state)
    await plan.plan_research_tasks_node(base_state)
    await extract.extract_evidence_node(base_state)
    await report.write_report_node(base_state)
    await verify.verify_report_node(base_state)

    assert captured == {
        "normalize": None,
        "plan": None,
        "extract": None,
        "report": None,
        "verify": None,
    }


@pytest.mark.asyncio
async def test_radar_llm_nodes_preserve_real_user_id(monkeypatch):
    from backend.services.research_radar.nodes import normalize

    user_id = uuid.uuid4()
    captured = {}

    async def _normalize(*args, user_id=None, **kwargs):
        captured["user_id"] = user_id
        return Dumpable({
            "ideal_role_titles": [],
            "target_domains": [],
            "target_companies": [],
            "target_locations": [],
            "remote_preferences": [],
        }), None

    monkeypatch.setattr(normalize, "normalize_brief_with_metrics", _normalize)

    await normalize.normalize_research_brief({
        "tracker": {},
        "user_context": {},
        "user_id": user_id,
    })

    assert captured["user_id"] == user_id


@pytest.mark.asyncio
async def test_extract_evidence_skips_failed_source(monkeypatch):
    from backend.services.research_radar.llm import ResearchModelUnavailableError
    from backend.services.research_radar.nodes import extract

    calls: list[str] = []

    async def _extract(_brief, source_item, **_kwargs):
        calls.append(source_item["source_item_id"])
        if source_item["source_item_id"] == "source-fails":
            raise ResearchModelUnavailableError("Radar evidence extraction failed")
        return [Dumpable({"source_item_id": source_item["source_item_id"], "claim": "Hiring signal"})], {
            "task": "extract"
        }

    monkeypatch.setattr(extract, "extract_evidence_with_metrics", _extract)

    result = await extract.extract_evidence_node(
        {
            "normalized_brief": {"search_objective": "Find platform roles."},
            "source_items": [
                {"source_item_id": "source-fails", "source_url": "https://example.com/fail"},
                {"source_item_id": "source-ok", "source_url": "https://example.com/ok"},
            ],
        }
    )

    assert calls == ["source-fails", "source-ok"]
    assert result["evidence_items"] == [{"source_item_id": "source-ok", "claim": "Hiring signal"}]
    assert result["_llm_calls"] == [{"task": "extract"}]
    assert result["evidence_extraction_errors"][0]["source_item_id"] == "source-fails"


@pytest.mark.asyncio
async def test_extract_evidence_fails_when_all_sources_fail(monkeypatch):
    from backend.services.research_radar.llm import ResearchModelUnavailableError
    from backend.services.research_radar.nodes import extract

    async def _extract(*_args, **_kwargs):
        raise ResearchModelUnavailableError("Radar evidence extraction failed")

    monkeypatch.setattr(extract, "extract_evidence_with_metrics", _extract)

    with pytest.raises(ResearchModelUnavailableError, match="all sources"):
        await extract.extract_evidence_node(
            {
                "normalized_brief": {"search_objective": "Find platform roles."},
                "source_items": [
                    {"source_item_id": "source-1", "source_url": "https://example.com/one"},
                    {"source_item_id": "source-2", "source_url": "https://example.com/two"},
                ],
            }
        )
