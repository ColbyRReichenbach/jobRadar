"""Deterministic classification gate for the hybrid Gmail lane."""

from __future__ import annotations

from backend.services.gmail_intelligence.types import (
    EmailCandidate,
    EmailFeatures,
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


def is_automated_sender(features: EmailFeatures) -> bool:
    return not features.is_likely_person or features.is_ats_domain or "sender_local_part_is_automated" in features.matched_features


def ambiguity_reasons(scores: ScoreResult, thresholds: HybridThresholds) -> list[str]:
    reasons: list[str] = []
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
    if scores.top_category == "not_relevant":
        return False
    if scores.noise_score >= 0.35 and scores.top_score <= 0.05 and scores.job_signal_score <= 0.5:
        return False
    return (
        scores.job_signal_score >= thresholds.llm_escalation_min_job_score
        and (
            scores.top_score < thresholds.category_accept
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

    if scores.noise_score >= thresholds.noise_skip and scores.job_signal_score < thresholds.job_related_ambiguous:
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
        )

    if scores.noise_score >= 0.35 and scores.top_score <= 0.05 and scores.job_signal_score <= 0.5:
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
        )

    if scores.job_signal_score < thresholds.job_related_ambiguous and scores.top_score < thresholds.job_related_ambiguous:
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
        )

    classification = scores.top_category
    job_related = classification != "not_relevant" and scores.job_signal_score >= thresholds.job_related_ambiguous
    confidence = max(scores.top_score, scores.job_signal_score if job_related else scores.noise_score)
    accepted = (
        job_related
        and scores.job_signal_score >= thresholds.job_related_accept
        and scores.top_score >= thresholds.category_accept
        and scores.margin >= thresholds.category_margin
    )
    reasons = ambiguity_reasons(scores, thresholds)
    if not accepted and not requires_llm_adjudication(scores, thresholds):
        reasons.append("below_llm_escalation_policy")

    return HybridClassificationResult(
        classification=classification if job_related else "not_relevant",
        job_related=job_related,
        confidence=confidence,
        confidence_band=confidence_band(confidence, thresholds),
        decision_path="deterministic_high_confidence" if accepted else "ambiguous_no_model_fallback",
        model_used=False,
        action_needed=action_needed_for_classification(classification, features) if job_related else False,
        is_automated=is_automated,
        sender_role=sender_role,
        company_name=None,
        key_sentence=normalized.subject,
        summary=f"Hybrid classifier selected {classification} for {normalized.sender_email or normalized.sender}.",
        matched_features=features.matched_features,
        ambiguity_reasons=reasons,
    )
