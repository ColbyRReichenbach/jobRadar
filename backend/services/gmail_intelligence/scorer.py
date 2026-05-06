"""Weighted local scoring for Gmail classifier decisions."""

from __future__ import annotations

from backend.services.gmail_intelligence.types import EmailClassification, EmailFeatures, ScoreResult

CATEGORIES: tuple[EmailClassification, ...] = (
    "job_update",
    "interview_request",
    "action_item",
    "offer",
    "rejection",
    "conversation",
    "not_relevant",
)


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def _has(features: EmailFeatures, category: str) -> bool:
    return bool(features.category_feature_hits.get(category))


def score_email(features: EmailFeatures) -> ScoreResult:
    noise_score = 0.0
    if features.is_noise_domain:
        noise_score += 0.65
    if "sender_local_part_is_automated" in features.matched_features:
        noise_score += 0.25
    if _has(features, "not_relevant"):
        noise_score += 0.45
    if features.has_job_signal or features.is_ats_domain:
        noise_score -= 0.35

    category_scores: dict[EmailClassification, float] = {category: 0.0 for category in CATEGORIES}

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
    if features.has_scheduler_url:
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

    category_scores = {category: _clamp(score) for category, score in category_scores.items()}

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
    if noise_score >= 0.75 and job_signal_score < 0.55:
        category_scores["not_relevant"] = max(category_scores["not_relevant"], noise_score)
        job_signal_score = min(job_signal_score, 0.25)

    sorted_scores = sorted(category_scores.items(), key=lambda item: item[1], reverse=True)
    top_category, top_score = sorted_scores[0]
    second_score = sorted_scores[1][1] if len(sorted_scores) > 1 else 0.0
    return ScoreResult(
        job_signal_score=_clamp(job_signal_score),
        noise_score=_clamp(noise_score),
        category_scores=category_scores,
        top_category=top_category,
        top_score=top_score,
        second_score=second_score,
        margin=_clamp(top_score - second_score),
    )
