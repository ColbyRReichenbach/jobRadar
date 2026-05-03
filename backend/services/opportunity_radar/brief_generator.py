def generate_briefs(signal, score):
    markdown = (
        f"## What changed\n{signal.title}\n\n"
        f"## Why it matters\n{signal.summary or 'A new opportunity signal was detected.'}\n\n"
        f"## Why it matters to you\n{score.get('explanation', '')}\n\n"
        f"## Evidence\n"
        + "\n".join([f"- {e.get('url')}" for e in (signal.evidence or [])])
    )
    structured = {
        "what_happened": signal.title,
        "why_it_matters": signal.summary,
        "why_it_matters_to_user": score.get("explanation"),
        "recommended_actions": [],
        "evidence": signal.evidence or [],
        "caveats": [],
    }
    return {"title": f"Brief: {signal.title}", "brief_type": "signal_brief", "markdown": markdown, "structured_json": structured, "confidence": signal.confidence or 0.0}
