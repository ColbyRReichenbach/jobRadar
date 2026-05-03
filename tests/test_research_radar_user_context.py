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
