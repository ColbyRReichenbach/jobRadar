from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph
from sqlalchemy import select

from backend.models import ResearchRun
from backend.services.ai_orchestrator import get_task
from backend.services.research_radar.config import ORCHESTRATOR_VERSION
from backend.services.research_radar.nodes.actions import derive_report_actions
from backend.services.research_radar.nodes.context import load_tracker_context
from backend.services.research_radar.nodes.dedupe import dedupe_and_rank_evidence
from backend.services.research_radar.nodes.diff import build_report_diff
from backend.services.research_radar.nodes.extract import extract_evidence_node
from backend.services.research_radar.nodes.fetch import fetch_documents
from backend.services.research_radar.nodes.normalize import normalize_research_brief, validate_brief
from backend.services.research_radar.nodes.notify import emit_alerts, schedule_next_run
from backend.services.research_radar.nodes.persist import persist_report_node
from backend.services.research_radar.nodes.plan import plan_research_tasks_node
from backend.services.research_radar.nodes.report import write_report_node
from backend.services.research_radar.nodes.search import run_search_tasks
from backend.services.research_radar.nodes.verify import verify_report_node
from backend.services.research_radar.state import ResearchRadarState
from backend.services.research_radar.storage import fail_step, finish_step, latest_running_step, start_step


NODE_ORDER = {
    "load_tracker_context": 1,
    "normalize_research_brief": 2,
    "validate_brief": 3,
    "plan_research_tasks": 4,
    "run_search_tasks": 5,
    "fetch_documents": 6,
    "extract_evidence": 7,
    "dedupe_and_rank_evidence": 8,
    "build_report_diff": 9,
    "write_report": 10,
    "derive_report_actions": 11,
    "verify_report": 12,
    "persist_report": 13,
    "emit_alerts": 14,
    "schedule_next_run": 15,
}

NODE_AI_TASK = {
    "normalize_research_brief": "research_brief_normalizer",
    "plan_research_tasks": "research_planner",
    "extract_evidence": "research_evidence_extractor",
    "write_report": "research_report_writer",
    "verify_report": "research_report_verifier",
}


def _node_wrapper(name: str, func):
    async def _wrapped(state: ResearchRadarState):
        db = state["db"]
        run = (
            await db.execute(select(ResearchRun).where(ResearchRun.id == state["run_id"]))
        ).scalars().first()
        if not run:
            raise RuntimeError(f"Research run {state['run_id']} was not found.")

        step = await start_step(
            db,
            run=run,
            step_name=name,
            step_order=NODE_ORDER[name],
            input_json={
                "mode": state.get("mode"),
                "trigger": state.get("trigger"),
                "tracker_name": state.get("tracker", {}).get("name"),
                "search_task_count": len(state.get("search_tasks", [])),
                "source_item_count": len(state.get("source_items", [])),
                "evidence_count": len(state.get("evidence_items", [])),
            },
            model_name=get_task(NODE_AI_TASK[name]).model if name in NODE_AI_TASK else None,
            prompt_version=get_task(NODE_AI_TASK[name]).prompt_version if name in NODE_AI_TASK else None,
        )
        await db.commit()

        try:
            result = await func(state)
            run = (
                await db.execute(select(ResearchRun).where(ResearchRun.id == state["run_id"]))
            ).scalars().first()
            await finish_step(
                db,
                step,
                output_json={
                    "keys": sorted((result or {}).keys()),
                    "report_id": (result or {}).get("report_id"),
                    "final_status": (result or {}).get("final_report", {}).get("status") if isinstance((result or {}).get("final_report"), dict) else None,
                },
            )
            if run:
                run.current_step = name
            await db.commit()
            return result or {}
        except Exception as exc:
            await db.rollback()
            run = (
                await db.execute(select(ResearchRun).where(ResearchRun.id == state["run_id"]))
            ).scalars().first()
            step = await latest_running_step(db, state["run_id"])
            await fail_step(
                db,
                step,
                error_message=str(exc),
                output_json={"failed_node": name},
            )
            if run:
                run.status = "failed"
                run.current_step = name
                run.error_message = str(exc)[:2000]
                run.status_detail = {"failed_step": name}
            await db.commit()
            raise

    return _wrapped


def build_research_graph():
    graph = StateGraph(ResearchRadarState)
    graph.add_node("load_tracker_context", _node_wrapper("load_tracker_context", load_tracker_context))
    graph.add_node("normalize_research_brief", _node_wrapper("normalize_research_brief", normalize_research_brief))
    graph.add_node("validate_brief", _node_wrapper("validate_brief", validate_brief))
    graph.add_node("plan_research_tasks", _node_wrapper("plan_research_tasks", plan_research_tasks_node))
    graph.add_node("run_search_tasks", _node_wrapper("run_search_tasks", run_search_tasks))
    graph.add_node("fetch_documents", _node_wrapper("fetch_documents", fetch_documents))
    graph.add_node("extract_evidence", _node_wrapper("extract_evidence", extract_evidence_node))
    graph.add_node("dedupe_and_rank_evidence", _node_wrapper("dedupe_and_rank_evidence", dedupe_and_rank_evidence))
    graph.add_node("build_report_diff", _node_wrapper("build_report_diff", build_report_diff))
    graph.add_node("write_report", _node_wrapper("write_report", write_report_node))
    graph.add_node("derive_report_actions", _node_wrapper("derive_report_actions", derive_report_actions))
    graph.add_node("verify_report", _node_wrapper("verify_report", verify_report_node))
    graph.add_node("persist_report", _node_wrapper("persist_report", persist_report_node))
    graph.add_node("emit_alerts", _node_wrapper("emit_alerts", emit_alerts))
    graph.add_node("schedule_next_run", _node_wrapper("schedule_next_run", schedule_next_run))

    graph.set_entry_point("load_tracker_context")
    graph.add_edge("load_tracker_context", "normalize_research_brief")
    graph.add_edge("normalize_research_brief", "validate_brief")
    graph.add_edge("validate_brief", "plan_research_tasks")
    graph.add_edge("plan_research_tasks", "run_search_tasks")
    graph.add_edge("run_search_tasks", "fetch_documents")
    graph.add_edge("fetch_documents", "extract_evidence")
    graph.add_edge("extract_evidence", "dedupe_and_rank_evidence")
    graph.add_edge("dedupe_and_rank_evidence", "build_report_diff")
    graph.add_edge("build_report_diff", "write_report")
    graph.add_edge("write_report", "derive_report_actions")
    graph.add_edge("derive_report_actions", "verify_report")
    graph.add_edge("verify_report", "persist_report")
    graph.add_edge("persist_report", "emit_alerts")
    graph.add_edge("emit_alerts", "schedule_next_run")
    graph.add_edge("schedule_next_run", END)
    return graph.compile()


RESEARCH_GRAPH = build_research_graph()


async def run_research_graph(db, run_id, profile_id, user_id, mode: str, trigger: str) -> dict[str, Any]:
    run = (
        await db.execute(select(ResearchRun).where(ResearchRun.id == run_id))
    ).scalars().first()
    if not run:
        raise RuntimeError(f"Research run {run_id} not found.")

    run.orchestrator_version = ORCHESTRATOR_VERSION
    run.graph_thread_id = f"research-run:{run_id}"
    run.current_step = "load_tracker_context"
    await db.commit()

    result = await RESEARCH_GRAPH.ainvoke(
        {
            "db": db,
            "run_id": run_id,
            "profile_id": profile_id,
            "user_id": user_id,
            "mode": mode,
            "trigger": trigger,
            "errors": [],
            "step_metrics": {},
        }
    )
    return result
