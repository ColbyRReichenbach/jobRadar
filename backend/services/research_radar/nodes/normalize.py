from __future__ import annotations

from backend.services.research_radar.config import DEPTH_TASK_LIMITS
from backend.services.research_radar.llm import normalize_brief_with_metrics


async def normalize_research_brief(state):
    tracker = state["tracker"]
    user_context = state["user_context"]
    normalized, llm_call = await normalize_brief_with_metrics(tracker, user_context)
    normalized_dict = normalized.model_dump()
    if not normalized_dict["ideal_role_titles"] and user_context.get("role_interest_labels"):
        normalized_dict["ideal_role_titles"] = user_context["role_interest_labels"][:6]
    if not normalized_dict["target_locations"] and user_context.get("preferred_locations"):
        normalized_dict["target_locations"] = user_context["preferred_locations"][:6]
    if not normalized_dict["remote_preferences"] and user_context.get("preferred_remote_type"):
        normalized_dict["remote_preferences"] = [user_context["preferred_remote_type"]]
    result = {"normalized_brief": normalized_dict}
    if llm_call:
        result["_llm_calls"] = [llm_call]
    return result


async def validate_brief(state):
    tracker = state["tracker"]
    normalized = dict(state["normalized_brief"])
    if not normalized["ideal_role_titles"] and tracker.get("selected_roles"):
        normalized["ideal_role_titles"] = tracker["selected_roles"][:6]
    if not normalized["target_domains"] and tracker.get("selected_domains"):
        normalized["target_domains"] = tracker["selected_domains"][:6]
    if not normalized["target_companies"] and tracker.get("selected_companies"):
        normalized["target_companies"] = tracker["selected_companies"][:8]
    if not any([normalized["ideal_role_titles"], normalized["target_domains"], normalized["target_companies"]]):
        normalized["ideal_role_titles"] = ["software engineer"]
    normalized["ideal_role_titles"] = list(dict.fromkeys(normalized["ideal_role_titles"]))[:8]
    normalized["target_domains"] = list(dict.fromkeys(normalized["target_domains"]))[:8]
    normalized["target_companies"] = list(dict.fromkeys(normalized["target_companies"]))[:10]
    depth = tracker.get("depth", "standard")
    max_queries = min(tracker.get("max_search_queries", 8), DEPTH_TASK_LIMITS.get(depth, 8))
    return {
        "normalized_brief": normalized,
        "step_metrics": {
            **state.get("step_metrics", {}),
            "validated_max_queries": max_queries,
        },
    }
