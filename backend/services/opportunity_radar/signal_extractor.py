from backend.models import OpportunitySignal, ResearchSourceItem


def _build_evidence(source_item: ResearchSourceItem, field: str, confidence: float) -> dict:
    raw_json = source_item.raw_json or {}
    excerpt = None
    if source_item.raw_text:
        excerpt = source_item.raw_text.strip()[:240]
    elif raw_json:
        excerpt = ", ".join(f"{key}: {value}" for key, value in list(raw_json.items())[:3])[:240]

    return {
        "url": source_item.source_url,
        "field": field,
        "confidence": confidence,
        "source_type": source_item.source_type,
        "source_name": source_item.source_name,
        "title": source_item.title,
        "excerpt": excerpt,
    }


def extract_signals(source_item: ResearchSourceItem, user_id, profile_id=None, run_id=None, company_id=None) -> list[OpportunitySignal]:
    signals: list[OpportunitySignal] = []

    if source_item.source_type == "application":
        title = source_item.title or "New role from your application history"
        roles = [source_item.raw_json.get("role_title")] if source_item.raw_json else []
        roles = [r for r in roles if r]
        signals.append(
            OpportunitySignal(
                user_id=user_id,
                profile_id=profile_id,
                run_id=run_id,
                source_item_id=source_item.id,
                company_id=company_id,
                event_type="new_role",
                title=title,
                summary="Role captured from your existing application pipeline.",
                evidence=[_build_evidence(source_item, "application", 0.9)],
                roles=roles,
                domains=[],
                tech_stack=[],
                confidence=0.85,
                occurred_at=source_item.published_at,
            )
        )

    if source_item.source_type == "company_visit":
        visit_count = (source_item.raw_json or {}).get("visit_count", 0)
        if visit_count >= 3:
            signals.append(
                OpportunitySignal(
                    user_id=user_id,
                    profile_id=profile_id,
                    run_id=run_id,
                    source_item_id=source_item.id,
                    company_id=company_id,
                    event_type="company_visit_interest",
                    title=f"Repeated company interest: {(source_item.raw_json or {}).get('domain', 'company')}",
                    summary=f"You visited this company {visit_count} times.",
                    evidence=[_build_evidence(source_item, "company_visit", 0.95)],
                    roles=[],
                    domains=[],
                    tech_stack=[],
                    confidence=0.9,
                    occurred_at=source_item.published_at,
                )
            )

    if source_item.source_type == "company_tech":
        tech_name = (source_item.raw_json or {}).get("tech_name")
        tech_stack = [tech_name] if tech_name else []
        signals.append(
            OpportunitySignal(
                user_id=user_id,
                profile_id=profile_id,
                run_id=run_id,
                source_item_id=source_item.id,
                company_id=company_id,
                event_type="tech_stack_signal",
                title=source_item.title or "Tech stack movement",
                summary="Company tech profile indicates recurring technology mentions.",
                evidence=[_build_evidence(source_item, "company_tech", 0.85)],
                roles=[],
                domains=[],
                tech_stack=tech_stack,
                confidence=0.8,
                occurred_at=source_item.published_at,
            )
        )

    return signals
