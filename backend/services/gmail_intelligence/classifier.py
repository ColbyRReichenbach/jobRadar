"""Deterministic classification gate for the hybrid Gmail lane."""

from __future__ import annotations

from backend.services.gmail_intelligence.types import (
    EmailCandidate,
    EmailFeatures,
    EmailRoute,
    EmailSubtype,
    HybridClassificationResult,
    HybridThresholds,
    NormalizedEmail,
    ScoreResult,
)


def infer_sender_role(sender: str, sender_email: str, is_human: bool) -> str:
    normalized = f"{(sender or '').lower()} {(sender_email or '').lower()}"
    if not is_human:
        return "automated"
    if "hiring manager" in normalized:
        return "hiring_manager"
    if any(token in normalized for token in {"recruiter", "recruiting", "talent", "sourcer"}):
        return "recruiter"
    if any(token in normalized for token in {"hr", "human resources", "people ops"}):
        return "hr"
    return "unknown"


def confidence_band(score: float, thresholds: HybridThresholds) -> str:
    if score >= thresholds.category_accept:
        return "high"
    if score >= thresholds.job_related_ambiguous:
        return "medium"
    return "low"


def action_needed_for_classification(classification: str, features: EmailFeatures) -> bool:
    if classification in {"offer", "action_item"}:
        return True
    if classification == "interview_request":
        return features.has_scheduler_url or bool(features.category_feature_hits.get("interview_request"))
    return False


def _best_subtype_for_route(scores: ScoreResult, route: EmailRoute) -> EmailSubtype:
    allowed: dict[EmailRoute, tuple[EmailSubtype, ...]] = {
        "filter": (
            "job_alert",
            "job_board_promo",
            "career_fair_or_event",
            "company_newsletter",
            "finance_noise",
            "retail_noise",
            "marketing_promo",
            "system_notification",
            "unknown_other",
        ),
        "opportunity_discovery": ("job_alert", "job_board_promo", "career_fair_or_event", "company_newsletter", "unknown_other"),
        "conversation": ("recruiter_outreach", "referral_or_networking", "unknown_other"),
        "application_inbox": (
            "interview_request",
            "rejection",
            "offer",
            "assessment_or_task",
            "document_request",
            "application_received",
            "application_status_update",
            "unknown_other",
        ),
        "action_review": (
            "recruiter_outreach",
            "job_alert",
            "interview_request",
            "assessment_or_task",
            "application_status_update",
            "unknown_other",
        ),
    }
    candidates = allowed[route]
    return max(candidates, key=lambda subtype: scores.subtype_scores.get(subtype, 0.0))


def _classification_for_route(route: EmailRoute, subtype: EmailSubtype, scores: ScoreResult) -> str:
    if route == "filter":
        return "not_relevant"
    if route == "conversation":
        return "conversation"
    if route == "opportunity_discovery":
        return "job_update"
    if subtype == "interview_request":
        return "interview_request"
    if subtype == "rejection":
        return "rejection"
    if subtype == "offer":
        return "offer"
    if subtype in {"assessment_or_task", "document_request"}:
        return "action_item"
    if route == "action_review" and scores.top_category != "not_relevant":
        return scores.top_category
    return "job_update"


def _status_update_allowed(route: EmailRoute, subtype: EmailSubtype, route_confidence: float, subtype_confidence: float) -> bool:
    return (
        route == "application_inbox"
        and subtype
        in {
            "application_received",
            "application_status_update",
            "interview_request",
            "rejection",
            "offer",
            "assessment_or_task",
            "document_request",
        }
        and route_confidence >= 0.7
        and subtype_confidence >= 0.55
    )


def _action_needed_for_route(route: EmailRoute, subtype: EmailSubtype, classification: str, features: EmailFeatures) -> bool:
    if route != "application_inbox":
        return False
    if subtype in {"offer", "assessment_or_task", "document_request"}:
        return True
    return action_needed_for_classification(classification, features)


def is_automated_sender(features: EmailFeatures) -> bool:
    return not features.is_likely_person or features.is_ats_domain or "sender_local_part_is_automated" in features.matched_features


def ambiguity_reasons(scores: ScoreResult, thresholds: HybridThresholds) -> list[str]:
    reasons: list[str] = []
    if scores.top_route_score < thresholds.category_accept and scores.top_route != "filter":
        reasons.append("route_score_below_accept_threshold")
    if scores.route_margin < thresholds.category_margin and scores.top_route != "filter":
        reasons.append("route_margin_below_threshold")
    if scores.job_signal_score < thresholds.job_related_accept:
        reasons.append("job_signal_below_accept_threshold")
    if scores.top_score < thresholds.category_accept:
        reasons.append("category_score_below_accept_threshold")
    if scores.margin < thresholds.category_margin:
        reasons.append("category_margin_below_threshold")
    if scores.noise_score >= thresholds.noise_skip and scores.job_signal_score >= thresholds.job_related_ambiguous:
        reasons.append("conflicting_noise_and_job_signals")
    return reasons


def requires_llm_adjudication(scores: ScoreResult, thresholds: HybridThresholds) -> bool:
    ambiguous_action_subtype = scores.top_subtype in {"interview_request", "assessment_or_task", "document_request", "offer", "rejection"}
    if scores.top_route == "filter":
        return False
    if scores.top_route == "opportunity_discovery" and scores.top_route_score >= thresholds.category_accept:
        return False
    if scores.top_route_score >= thresholds.category_accept and scores.route_margin >= thresholds.category_margin:
        if scores.top_route == "application_inbox" and ambiguous_action_subtype and scores.subtype_margin < thresholds.category_margin:
            return True
        return False
    if scores.noise_score >= 0.35 and scores.top_score <= 0.05 and scores.job_signal_score <= 0.5:
        return False
    if scores.top_route == "action_review" and scores.job_signal_score >= thresholds.llm_escalation_min_job_score:
        return True
    return (
        scores.job_signal_score >= thresholds.llm_escalation_min_job_score
        and (
            scores.top_route_score < thresholds.category_accept
            or scores.route_margin < thresholds.category_margin
            or scores.top_score < thresholds.category_accept
            or scores.margin < thresholds.category_margin
            or (scores.noise_score >= thresholds.noise_skip and scores.job_signal_score >= thresholds.job_related_ambiguous)
        )
    )


def deterministic_classify(
    candidate: EmailCandidate,
    normalized: NormalizedEmail,
    features: EmailFeatures,
    scores: ScoreResult,
    thresholds: HybridThresholds | None = None,
) -> HybridClassificationResult:
    thresholds = thresholds or HybridThresholds()
    sender_role = infer_sender_role(normalized.sender, normalized.sender_email, features.is_likely_person)
    is_automated = is_automated_sender(features)
    route = scores.top_route
    subtype = _best_subtype_for_route(scores, route)
    route_confidence = scores.top_route_score
    subtype_confidence = scores.subtype_scores.get(subtype, 0.0)

    if route == "filter" and scores.noise_score >= thresholds.noise_skip and scores.job_signal_score < thresholds.job_related_ambiguous:
        return HybridClassificationResult(
            classification="not_relevant",
            job_related=False,
            confidence=max(scores.noise_score, 0.8),
            confidence_band="high",
            decision_path="deterministic_noise_skip",
            model_used=False,
            action_needed=False,
            is_automated=True,
            sender_role="automated",
            company_name=None,
            key_sentence=normalized.subject,
            summary=f"Obvious non-job notification from {normalized.sender_email or normalized.sender}.",
            matched_features=features.matched_features,
            ambiguity_reasons=[],
            route=route,
            subtype=subtype,
            route_confidence=route_confidence,
            subtype_confidence=subtype_confidence,
            status_update_allowed=False,
            route_scores=dict(scores.route_scores),
            subtype_scores=dict(scores.subtype_scores),
        )

    if route == "filter" and scores.noise_score >= 0.35 and scores.top_score <= 0.05 and scores.job_signal_score <= 0.5:
        return HybridClassificationResult(
            classification="not_relevant",
            job_related=False,
            confidence=max(0.65, scores.noise_score),
            confidence_band="high",
            decision_path="deterministic_low_signal_skip",
            model_used=False,
            action_needed=False,
            is_automated=is_automated,
            sender_role=sender_role,
            company_name=None,
            key_sentence=normalized.subject,
            summary=f"Generic notification/product text without a job-search lifecycle signal from {normalized.sender_email or normalized.sender}.",
            matched_features=features.matched_features,
            ambiguity_reasons=[],
            route=route,
            subtype=subtype,
            route_confidence=route_confidence,
            subtype_confidence=subtype_confidence,
            status_update_allowed=False,
            route_scores=dict(scores.route_scores),
            subtype_scores=dict(scores.subtype_scores),
        )

    if scores.job_signal_score < thresholds.job_related_ambiguous and scores.top_score < thresholds.job_related_ambiguous and route != "opportunity_discovery":
        return HybridClassificationResult(
            classification="not_relevant",
            job_related=False,
            confidence=max(0.6, 1.0 - scores.job_signal_score),
            confidence_band="high",
            decision_path="deterministic_low_signal_skip",
            model_used=False,
            action_needed=False,
            is_automated=is_automated,
            sender_role=sender_role,
            company_name=None,
            key_sentence=normalized.subject,
            summary=f"Low job-search signal from {normalized.sender_email or normalized.sender}.",
            matched_features=features.matched_features,
            ambiguity_reasons=[],
            route="filter",
            subtype=subtype,
            route_confidence=max(route_confidence, scores.noise_score),
            subtype_confidence=subtype_confidence,
            status_update_allowed=False,
            route_scores=dict(scores.route_scores),
            subtype_scores=dict(scores.subtype_scores),
        )

    classification = _classification_for_route(route, subtype, scores)
    job_related = route != "filter" and (
        scores.job_signal_score >= thresholds.job_related_ambiguous
        or route in {"opportunity_discovery", "conversation", "application_inbox"}
    )
    confidence = max(route_confidence, scores.top_score, scores.job_signal_score if job_related else scores.noise_score)
    accepted = (
        route in {"filter", "opportunity_discovery", "conversation", "application_inbox"}
        and (job_related or route == "filter")
        and route_confidence >= thresholds.category_accept
        and scores.route_margin >= thresholds.category_margin
        and (
            route != "application_inbox"
            or (
                subtype_confidence >= 0.55
                and (
                    subtype in {"application_received", "application_status_update", "unknown_other"}
                    or scores.subtype_margin >= thresholds.category_margin
                )
            )
        )
    )
    reasons = ambiguity_reasons(scores, thresholds)
    if not accepted and not requires_llm_adjudication(scores, thresholds):
        reasons.append("below_llm_escalation_policy")
    status_update_allowed = _status_update_allowed(route, subtype, route_confidence, subtype_confidence)

    return HybridClassificationResult(
        classification=classification if job_related else "not_relevant",
        job_related=job_related,
        confidence=confidence,
        confidence_band=confidence_band(confidence, thresholds),
        decision_path="deterministic_high_confidence" if accepted else "ambiguous_no_model_fallback",
        model_used=False,
        action_needed=_action_needed_for_route(route, subtype, classification, features) if job_related else False,
        is_automated=is_automated,
        sender_role=sender_role,
        company_name=None,
        key_sentence=normalized.subject,
        summary=f"Hybrid classifier routed message to {route}/{subtype} for {normalized.sender_email or normalized.sender}.",
        matched_features=features.matched_features,
        ambiguity_reasons=reasons,
        route=route,
        subtype=subtype,
        route_confidence=route_confidence,
        subtype_confidence=subtype_confidence,
        status_update_allowed=status_update_allowed,
        route_scores=dict(scores.route_scores),
        subtype_scores=dict(scores.subtype_scores),
    )
