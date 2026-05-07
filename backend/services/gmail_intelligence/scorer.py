"""Weighted local scoring for Gmail classifier decisions."""

from __future__ import annotations

from backend.services.gmail_intelligence.types import EmailClassification, EmailFeatures, EmailRoute, EmailSubtype, ScoreResult

CATEGORIES: tuple[EmailClassification, ...] = (
    "job_update",
    "interview_request",
    "action_item",
    "offer",
    "rejection",
    "conversation",
    "not_relevant",
)

ROUTES: tuple[EmailRoute, ...] = (
    "filter",
    "opportunity_discovery",
    "conversation",
    "application_inbox",
    "action_review",
)

SUBTYPES: tuple[EmailSubtype, ...] = (
    "application_received",
    "application_status_update",
    "interview_request",
    "rejection",
    "offer",
    "assessment_or_task",
    "document_request",
    "recruiter_outreach",
    "referral_or_networking",
    "job_alert",
    "job_board_promo",
    "career_fair_or_event",
    "company_newsletter",
    "marketing_promo",
    "system_notification",
    "finance_noise",
    "retail_noise",
    "unknown_other",
)


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def _has(features: EmailFeatures, category: str) -> bool:
    return bool(features.category_feature_hits.get(category))


def _route_has(features: EmailFeatures, feature_name: str) -> bool:
    return bool(features.route_feature_hits.get(feature_name))


def _matched(features: EmailFeatures, feature_name: str) -> bool:
    return feature_name in features.matched_features


def score_email(features: EmailFeatures) -> ScoreResult:
    noise_score = 0.0
    if features.is_noise_domain:
        noise_score += 0.65
    if _matched(features, "sender_local_part_is_automated"):
        noise_score += 0.25
    if _has(features, "not_relevant"):
        noise_score += 0.45
    if features.sender_domain_family in {"finance", "retail", "system_noise"}:
        noise_score += 0.35
    if features.sender_local_type in {"marketing", "notification", "no_reply"}:
        noise_score += 0.18
    if features.has_job_signal or features.is_ats_domain:
        noise_score -= 0.35

    category_scores: dict[EmailClassification, float] = {category: 0.0 for category in CATEGORIES}
    route_scores: dict[EmailRoute, float] = {route: 0.0 for route in ROUTES}
    subtype_scores: dict[EmailSubtype, float] = {subtype: 0.0 for subtype in SUBTYPES}

    has_application_lifecycle = _route_has(features, "application_lifecycle")
    has_scheduler_language = _route_has(features, "scheduler_language")
    has_opportunity_discovery = _route_has(features, "opportunity_discovery")
    has_marketing_language = _route_has(features, "marketing_language")
    has_finance_language = _route_has(features, "finance_language")
    has_retail_language = _route_has(features, "retail_language")
    has_conversation_language = _route_has(features, "conversation_language")
    has_location_context_only = (
        _route_has(features, "location_context")
        and not has_scheduler_language
        and not has_application_lifecycle
        and not any(_has(features, category) for category in {"rejection", "offer", "action_item", "job_update"})
    )

    if features.is_ats_domain:
        category_scores["job_update"] += 0.35
    if features.is_known_company_domain:
        category_scores["job_update"] += 0.2
        category_scores["conversation"] += 0.1
    if features.has_recruiting_sender_signal:
        category_scores["conversation"] += 0.28
        category_scores["job_update"] += 0.12
    if features.is_likely_person:
        category_scores["conversation"] += 0.25
    if "ats_url" in features.url_feature_types:
        category_scores["job_update"] += 0.2
    if features.has_private_url_signal:
        category_scores["job_update"] += 0.15

    if _has(features, "rejection"):
        category_scores["rejection"] += 0.94
    if _has(features, "offer"):
        category_scores["offer"] += 0.94
    if _has(features, "action_item"):
        category_scores["action_item"] += 0.88
    if _has(features, "interview_request"):
        category_scores["interview_request"] += 0.86
    if features.has_scheduler_url or has_scheduler_language:
        category_scores["interview_request"] += 0.2
    if _has(features, "job_update"):
        category_scores["job_update"] += 0.82
    if _has(features, "conversation"):
        category_scores["conversation"] += 0.88

    # Resolve common phrase conflicts. Recruiter conversations often mention
    # availability but should not become interview requests unless the message
    # actually asks the user to schedule or select a time.
    if _has(features, "conversation") and not features.has_scheduler_url:
        category_scores["interview_request"] = min(category_scores["interview_request"], 0.42)
    if has_location_context_only:
        category_scores["interview_request"] = min(category_scores["interview_request"], 0.2)
        category_scores["job_update"] = min(category_scores["job_update"], 0.35)

    # Lifecycle categories should outrank generic updates when explicit.
    explicit_lifecycle = max(
        category_scores["rejection"],
        category_scores["offer"],
        category_scores["action_item"],
        category_scores["interview_request"],
    )
    if explicit_lifecycle >= 0.7:
        category_scores["job_update"] = min(category_scores["job_update"], 0.55)
    if category_scores["conversation"] >= 0.7:
        category_scores["job_update"] = min(category_scores["job_update"], 0.55)

    # Route first. Routes represent product destinations. Subtype/category only
    # controls what happens after the email is safely routed.
    if noise_score >= 0.45:
        route_scores["filter"] += noise_score
    if has_marketing_language:
        route_scores["filter"] += 0.38
    if has_finance_language or features.sender_domain_family == "finance":
        route_scores["filter"] += 0.48
        subtype_scores["finance_noise"] += 0.72
    if has_retail_language or features.sender_domain_family == "retail":
        route_scores["filter"] += 0.42
        subtype_scores["retail_noise"] += 0.68
    if features.sender_domain_family == "system_noise":
        route_scores["filter"] += 0.46
        subtype_scores["system_notification"] += 0.72
    if has_marketing_language:
        subtype_scores["marketing_promo"] += 0.62

    if has_opportunity_discovery:
        if features.sender_domain_family == "job_board":
            route_scores["filter"] += 0.72
        else:
            route_scores["opportunity_discovery"] += 0.72
        subtype_scores["job_alert"] += 0.72
    if features.sender_domain_family == "job_board":
        route_scores["filter"] += 0.42
        subtype_scores["job_board_promo"] += 0.45
    if features.sender_local_type in {"jobs", "careers"} and has_opportunity_discovery:
        if features.sender_domain_family == "job_board":
            route_scores["filter"] += 0.18
        else:
            route_scores["opportunity_discovery"] += 0.18
    if features.has_job_signal and has_opportunity_discovery:
        if features.sender_domain_family == "job_board":
            route_scores["filter"] += 0.16
        else:
            route_scores["opportunity_discovery"] += 0.16

    if features.is_likely_person:
        route_scores["conversation"] += 0.3
    if features.has_recruiting_sender_signal:
        route_scores["conversation"] += 0.3
        subtype_scores["recruiter_outreach"] += 0.45
    if has_conversation_language:
        route_scores["conversation"] += 0.45
        subtype_scores["recruiter_outreach"] += 0.32
    if features.sender_domain_family == "personal" and features.has_job_signal:
        route_scores["conversation"] += 0.2

    if features.is_ats_domain:
        route_scores["application_inbox"] += 0.55
    if "ats_url" in features.url_feature_types:
        route_scores["application_inbox"] += 0.35
    if features.has_private_url_signal:
        route_scores["application_inbox"] += 0.25
    if has_application_lifecycle:
        route_scores["application_inbox"] += 0.5
    if features.has_scheduler_url or has_scheduler_language:
        route_scores["application_inbox"] += 0.38
    if category_scores["interview_request"] >= 0.7 and (features.has_scheduler_url or has_scheduler_language):
        route_scores["application_inbox"] += 0.22
        route_scores["conversation"] = min(route_scores["conversation"], 0.45)
    if any(category_scores[category] >= 0.7 for category in {"rejection", "offer", "action_item", "interview_request"}):
        route_scores["application_inbox"] += 0.3
    if category_scores["job_update"] >= 0.7 and has_application_lifecycle:
        route_scores["application_inbox"] += 0.2

    if features.has_job_signal and max(route_scores.values()) < 0.6:
        route_scores["action_review"] += 0.45
    if features.has_job_signal and features.is_likely_person and not has_conversation_language:
        route_scores["action_review"] += 0.2

    # EDA showed that opportunity emails containing "apply", location names, or
    # "onsite" were being treated as lifecycle updates. Do not let generic job
    # discovery language mutate the pipeline unless lifecycle/scheduler evidence
    # exists.
    if has_opportunity_discovery and not (has_application_lifecycle or has_scheduler_language or features.is_ats_domain):
        route_scores["application_inbox"] = min(route_scores["application_inbox"], 0.35)
        category_scores["interview_request"] = min(category_scores["interview_request"], 0.2)
        category_scores["action_item"] = min(category_scores["action_item"], 0.35)
        category_scores["job_update"] = min(category_scores["job_update"], 0.45)
    if route_scores["filter"] >= 0.75 and not (has_application_lifecycle or has_scheduler_language or features.is_ats_domain):
        route_scores["conversation"] = min(route_scores["conversation"], 0.25)
        route_scores["application_inbox"] = min(route_scores["application_inbox"], 0.2)

    if _has(features, "rejection"):
        subtype_scores["rejection"] += category_scores["rejection"]
    if _has(features, "offer"):
        subtype_scores["offer"] += category_scores["offer"]
    if _has(features, "interview_request") and not has_location_context_only:
        subtype_scores["interview_request"] += category_scores["interview_request"]
    if _has(features, "action_item"):
        subtype_scores["assessment_or_task"] += min(1.0, category_scores["action_item"])
    if _has(features, "job_update"):
        subtype_scores["application_status_update"] += category_scores["job_update"]
    if has_application_lifecycle and "thank you for applying" in features.route_feature_hits.get("application_lifecycle", []):
        subtype_scores["application_received"] += 0.82
    if has_conversation_language and subtype_scores["recruiter_outreach"] < 0.5:
        subtype_scores["referral_or_networking"] += 0.46
    if max(subtype_scores.values()) <= 0.05:
        subtype_scores["unknown_other"] = 0.4

    category_scores = {category: _clamp(score) for category, score in category_scores.items()}
    route_scores = {route: _clamp(score) for route, score in route_scores.items()}
    subtype_scores = {subtype: _clamp(score) for subtype, score in subtype_scores.items()}

    job_signal_score = max(
        category_scores["job_update"],
        category_scores["interview_request"],
        category_scores["action_item"],
        category_scores["offer"],
        category_scores["rejection"],
        category_scores["conversation"],
    )
    if features.has_job_signal:
        job_signal_score = max(job_signal_score, 0.5)
    if features.is_ats_domain:
        job_signal_score = max(job_signal_score, 0.75)
    if route_scores["opportunity_discovery"] >= 0.7:
        job_signal_score = max(job_signal_score, 0.6)
    if route_scores["conversation"] >= 0.7 or route_scores["application_inbox"] >= 0.7:
        job_signal_score = max(job_signal_score, 0.65)
    if route_scores["filter"] >= 0.75 and job_signal_score < 0.55:
        category_scores["not_relevant"] = max(category_scores["not_relevant"], noise_score)
        job_signal_score = min(job_signal_score, 0.25)

    category_scores = {category: _clamp(score) for category, score in category_scores.items()}
    sorted_routes = sorted(route_scores.items(), key=lambda item: item[1], reverse=True)
    top_route, top_route_score = sorted_routes[0]
    second_route_score = sorted_routes[1][1] if len(sorted_routes) > 1 else 0.0
    sorted_subtypes = sorted(subtype_scores.items(), key=lambda item: item[1], reverse=True)
    top_subtype, top_subtype_score = sorted_subtypes[0]
    second_subtype_score = sorted_subtypes[1][1] if len(sorted_subtypes) > 1 else 0.0
    sorted_scores = sorted(category_scores.items(), key=lambda item: item[1], reverse=True)
    top_category, top_score = sorted_scores[0]
    second_score = sorted_scores[1][1] if len(sorted_scores) > 1 else 0.0
    return ScoreResult(
        job_signal_score=_clamp(job_signal_score),
        noise_score=_clamp(noise_score),
        route_scores=route_scores,
        top_route=top_route,
        top_route_score=top_route_score,
        second_route_score=second_route_score,
        route_margin=_clamp(top_route_score - second_route_score),
        subtype_scores=subtype_scores,
        top_subtype=top_subtype,
        top_subtype_score=top_subtype_score,
        second_subtype_score=second_subtype_score,
        subtype_margin=_clamp(top_subtype_score - second_subtype_score),
        category_scores=category_scores,
        top_category=top_category,
        top_score=top_score,
        second_score=second_score,
        margin=_clamp(top_score - second_score),
    )
