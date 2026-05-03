"""Radar Research graph runtime."""

__all__ = ["run_research_graph"]


def __getattr__(name: str):
    if name == "run_research_graph":
        from backend.services.research_radar.graph import run_research_graph

        return run_research_graph
    raise AttributeError(name)
