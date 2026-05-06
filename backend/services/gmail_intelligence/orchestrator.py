"""Orchestrate the eval-first hybrid Gmail classifier lane."""

from __future__ import annotations

from dataclasses import dataclass, replace

from backend.services.gmail_intelligence.classifier import deterministic_classify, requires_llm_adjudication
from backend.services.gmail_intelligence.feature_extractor import extract_email_features
from backend.services.gmail_intelligence.normalizer import normalize_email
from backend.services.gmail_intelligence.preflight import GmailLlmPreflightDecision, evaluate_llm_preflight
from backend.services.gmail_intelligence.scorer import score_email
from backend.services.gmail_intelligence.types import (
    EmailCandidate,
    EmailFeatures,
    HybridClassificationResult,
    HybridThresholds,
    NormalizedEmail,
    ScoreResult,
)


@dataclass(frozen=True)
class HybridEmailAnalysis:
    candidate: EmailCandidate
    normalized: NormalizedEmail
    features: EmailFeatures
    scores: ScoreResult
    result: HybridClassificationResult
    thresholds: HybridThresholds
    llm_preflight: GmailLlmPreflightDecision | None = None


def _preflight_fallback_result(
    fallback: HybridClassificationResult,
    preflight: GmailLlmPreflightDecision,
) -> HybridClassificationResult:
    blocked_as_safety = preflight.block_reason in {"prompt_injection_risk", "redaction_leak", "prompt_too_large"}
    return replace(
        fallback,
        decision_path="llm_quarantined" if blocked_as_safety else "ambiguous_no_model_fallback",
        redaction_applied=bool(preflight.redaction_counts),
        redaction_counts=preflight.redaction_counts,
        fallback_reason=preflight.block_reason or "llm_preflight_not_passed",
    )


async def analyze_email(
    candidate: EmailCandidate,
    *,
    thresholds: HybridThresholds | None = None,
    ai_enabled: bool = True,
    ai_consent: bool = True,
    forbidden_prompt_terms: list[str] | None = None,
) -> HybridEmailAnalysis:
    thresholds = thresholds or HybridThresholds()
    normalized = normalize_email(candidate)
    features = extract_email_features(candidate, normalized)
    scores = score_email(features)
    local_result = deterministic_classify(candidate, normalized, features, scores, thresholds)

    result = local_result
    llm_preflight: GmailLlmPreflightDecision | None = None
    if ai_enabled and requires_llm_adjudication(scores, thresholds):
        llm_preflight = evaluate_llm_preflight(
            candidate,
            ai_consent=ai_consent,
            thresholds=thresholds,
            forbidden_prompt_terms=forbidden_prompt_terms,
        )
        if not llm_preflight.should_call_llm:
            result = _preflight_fallback_result(local_result, llm_preflight)
        else:
            from backend.services.gmail_intelligence.adjudicator import adjudicate_with_llm

            result = await adjudicate_with_llm(
                normalized,
                features,
                scores,
                local_result,
                thresholds,
                llm_preflight,
            )

    return HybridEmailAnalysis(
        candidate=candidate,
        normalized=normalized,
        features=features,
        scores=scores,
        result=result,
        thresholds=thresholds,
        llm_preflight=llm_preflight,
    )
