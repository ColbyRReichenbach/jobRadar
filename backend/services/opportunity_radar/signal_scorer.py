from datetime import datetime, timezone


def _normalize(v: float) -> float:
    return max(0.0, min(1.0, v))


def score_signal(signal, profile=None, user_profile=None, applications=None, company_visits=None, warm_connections=None):
    roles = set((signal.roles or []))
    selected_roles = set((profile.selected_roles or [])) if profile else set()
    role_fit = 1.0 if roles and roles.intersection(selected_roles) else (0.4 if signal.event_type == "new_role" else 0.2)

    domains = set((signal.domains or []))
    selected_domains = set((profile.selected_domains or [])) if profile else set()
    domain_fit = 1.0 if domains and domains.intersection(selected_domains) else 0.3

    company_interest = 0.3
    if signal.event_type == "company_visit_interest":
        company_interest = 0.9
    elif signal.company_id:
        company_interest = 0.7

    occurred_at = signal.occurred_at or datetime.now(timezone.utc)
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (datetime.now(timezone.utc) - occurred_at).total_seconds() / 86400.0)
    recency = 1.0 if age_days <= 1 else (0.7 if age_days <= 7 else 0.4)

    public_data_buildability = 0.8 if signal.event_type in {"tech_stack_signal", "new_role"} else 0.5
    outreach_path_strength = 0.5 if signal.event_type == "company_visit_interest" else 0.3
    portfolio_gap_relevance = 0.8 if signal.event_type == "tech_stack_signal" else 0.5
    source_confidence = _normalize(signal.confidence or 0.0)

    total = (
        0.20 * role_fit
        + 0.20 * domain_fit
        + 0.15 * company_interest
        + 0.15 * recency
        + 0.10 * public_data_buildability
        + 0.10 * outreach_path_strength
        + 0.05 * portfolio_gap_relevance
        + 0.05 * source_confidence
    )

    explanation = (
        f"Scored for {signal.event_type}: role fit {role_fit:.2f}, domain fit {domain_fit:.2f}, "
        f"company interest {company_interest:.2f}, recency {recency:.2f}."
    )

    return {
        "total_score": int(round(_normalize(total) * 100)),
        "role_fit": role_fit,
        "domain_fit": domain_fit,
        "company_interest": company_interest,
        "recency": recency,
        "public_data_buildability": public_data_buildability,
        "outreach_path_strength": outreach_path_strength,
        "portfolio_gap_relevance": portfolio_gap_relevance,
        "source_confidence": source_confidence,
        "explanation": explanation,
    }
