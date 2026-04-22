from __future__ import annotations

from backend.services.research_radar.config import DEPTH_TASK_LIMITS
from backend.services.research_radar.llm import plan_research_tasks


async def plan_research_tasks_node(state):
    tracker = state["tracker"]
    depth = tracker.get("depth", "standard")
    max_queries = min(tracker.get("max_search_queries", 8), DEPTH_TASK_LIMITS.get(depth, 8))
    tasks = await plan_research_tasks(state["normalized_brief"], depth, max_queries)
    task_payloads = [task.model_dump() for task in tasks[:max_queries]]
    return {
        "search_tasks": task_payloads,
        "research_plan": {
            "depth": depth,
            "task_count": len(task_payloads),
        },
    }
