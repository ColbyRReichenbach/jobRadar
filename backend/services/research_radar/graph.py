from __future__ import annotations

import time
from typing import Any

from langgraph.graph import END, StateGraph
from sqlalchemy import select

from backend.models import ResearchRun
from backend.metrics import (
    observe_research_evidence_items,
    observe_research_failure,
    observe_research_report_generated,
    observe_research_sources_fetched,
    observe_research_step,
)
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
from backend.services.research_radar.observability import (
    build_step_input_snapshot,
    build_step_output_snapshot,
    emit_langsmith_step_trace,
    extract_llm_calls,
    merge_step_metrics,
)
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

        step_input = build_step_input_snapshot(name, state)
        step = await start_step(
            db,
            run=run,
            step_name=name,
            step_order=NODE_ORDER[name],
            input_json=step_input,
            model_name=get_task(NODE_AI_TASK[name]).model if name in NODE_AI_TASK else None,
            prompt_version=get_task(NODE_AI_TASK[name]).prompt_version if name in NODE_AI_TASK else None,
        )
        await db.commit()

        started = time.perf_counter()
        try:
            result = await func(state) or {}
            llm_calls = extract_llm_calls(result)
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            run = (
                await db.execute(select(ResearchRun).where(ResearchRun.id == state["run_id"]))
            ).scalars().first()
            tokens_in = sum((item.get("tokens_in") or 0) for item in llm_calls) or None
            tokens_out = sum((item.get("tokens_out") or 0) for item in llm_calls) or None
            cost_estimate_cents = sum((item.get("cost_estimate_cents") or 0) for item in llm_calls) or None
            output_snapshot = build_step_output_snapshot(
                name,
                state,
                result,
                llm_calls=llm_calls,
                duration_ms=duration_ms,
            )
            await finish_step(
                db,
                step,
                output_json=output_snapshot,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_estimate_cents=cost_estimate_cents,
            )
            if run:
                run.current_step = name
                if llm_calls:
                    run.llm_call_count = (run.llm_call_count or 0) + len(llm_calls)
                    run.tokens_in = (run.tokens_in or 0) + (tokens_in or 0)
                    run.tokens_out = (run.tokens_out or 0) + (tokens_out or 0)
                    run.cost_estimate_cents = (run.cost_estimate_cents or 0) + (cost_estimate_cents or 0)

            observe_research_step(
                mode=run.mode if run else state.get("mode"),
                step_name=name,
                outcome="success",
                duration_seconds=duration_ms / 1000,
            )
            if name == "fetch_documents":
                source_counts: dict[str, int] = {}
                for item in result.get("source_items", []):
                    source_type = item.get("source_type") or "unknown"
                    source_counts[source_type] = source_counts.get(source_type, 0) + 1
                for source_type, count in source_counts.items():
                    observe_research_sources_fetched(mode=run.mode if run else state.get("mode"), source_type=source_type, count=count)
            if name == "dedupe_and_rank_evidence":
                evidence_counts: dict[str, int] = {}
                for item in result.get("evidence_items", []):
                    evidence_type = item.get("evidence_type") or "unknown"
                    evidence_counts[evidence_type] = evidence_counts.get(evidence_type, 0) + 1
                for evidence_type, count in evidence_counts.items():
                    observe_research_evidence_items(mode=run.mode if run else state.get("mode"), evidence_type=evidence_type, count=count)
            if name == "persist_report":
                observe_research_report_generated(
                    mode=run.mode if run else state.get("mode"),
                    status=(result.get("final_report") or {}).get("status"),
                )

            result["step_metrics"] = merge_step_metrics(
                result.get("step_metrics") or state.get("step_metrics"),
                step_name=name,
                status="succeeded",
                duration_ms=duration_ms,
                llm_calls=llm_calls,
            )

            emit_langsmith_step_trace(
                run_id=str(state["run_id"]),
                profile_id=str(state["profile_id"]),
                user_id=str(state["user_id"]),
                step_name=name,
                input_payload=step_input,
                output_payload=output_snapshot,
                error_message=None,
                metadata={"mode": run.mode if run else state.get("mode"), "trigger": state.get("trigger")},
            )
            await db.commit()
            return result
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            await db.rollback()
            run = (
                await db.execute(select(ResearchRun).where(ResearchRun.id == state["run_id"]))
            ).scalars().first()
            step = await latest_running_step(db, state["run_id"])
            failure_output = {"failed_node": name, "duration_ms": duration_ms}
            await fail_step(
                db,
                step,
                error_message=str(exc),
                output_json=failure_output,
            )
            if run:
                run.status = "failed"
                run.current_step = name
                run.error_message = str(exc)[:2000]
                run.status_detail = {"failed_step": name}
            observe_research_step(
                mode=run.mode if run else state.get("mode"),
                step_name=name,
                outcome="failure",
                duration_seconds=duration_ms / 1000,
            )
            observe_research_failure(mode=run.mode if run else state.get("mode"), step_name=name)
            emit_langsmith_step_trace(
                run_id=str(state["run_id"]),
                profile_id=str(state["profile_id"]),
                user_id=str(state["user_id"]),
                step_name=name,
                input_payload=step_input,
                output_payload=failure_output,
                error_message=str(exc),
                metadata={"mode": run.mode if run else state.get("mode"), "trigger": state.get("trigger")},
            )
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
