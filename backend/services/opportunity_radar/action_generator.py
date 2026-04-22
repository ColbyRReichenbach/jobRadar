def generate_actions(signal, score):
    actions = []
    if score.get("total_score", 0) >= 70:
        actions.append(
            {
                "action_type": "research_company",
                "title": f"Research follow-up for {signal.title}",
                "body": "Review the signal evidence and decide whether to apply, build, or outreach.",
                "priority": score["total_score"],
                "payload": {"event_type": signal.event_type, "evidence": signal.evidence or []},
            }
        )
    if signal.event_type == "new_role":
        actions.append(
            {
                "action_type": "apply_to_job",
                "title": "Review role and consider application",
                "body": "Open the role source and decide if this should move to your pipeline.",
                "priority": max(55, score.get("total_score", 0) - 10),
                "payload": {"source_url": (signal.evidence or [{}])[0].get("url") if signal.evidence else None},
            }
        )
    if signal.event_type == "tech_stack_signal":
        actions.append(
            {
                "action_type": "build_portfolio_project",
                "title": "Capture a portfolio build idea from this signal",
                "body": "Translate this tech signal into a focused demo project aligned to your target roles.",
                "priority": max(50, score.get("total_score", 0) - 5),
                "payload": {"tech_stack": signal.tech_stack or []},
            }
        )
    return actions
