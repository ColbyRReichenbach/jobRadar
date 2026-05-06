"""Redacted LLM adjudication for ambiguous Gmail classifier cases."""

from __future__ import annotations

from backend.services import ai_safety, email_classifier
from backend.services.ai_pricing import estimate_cost_cents
from backend.services.gmail_intelligence.classifier import action_needed_for_classification, is_automated_sender
from backend.services.gmail_intelligence.privacy import redact_email_for_llm
from backend.services.gmail_intelligence.preflight import GmailLlmPreflightDecision
from backend.services.gmail_intelligence.types import (
    EmailFeatures,
    HybridClassificationResult,
    HybridThresholds,
    NormalizedEmail,
    ScoreResult,
)


def _cost_from_tokens(model: str, prompt_tokens: int | None, output_tokens: int | None) -> float:
    _, breakdown = estimate_cost_cents(
        model=model,
        provider="openai",
        prompt_tokens=prompt_tokens,
        output_tokens=output_tokens,
    )
    return round(
        float(breakdown.get("input_cost_cents") or 0)
        + float(breakdown.get("cached_input_cost_cents") or 0)
        + float(breakdown.get("output_cost_cents") or 0)
        + float(breakdown.get("reasoning_cost_cents") or 0),
        6,
    )


def build_adjudication_prompt(
    normalized: NormalizedEmail,
    features: EmailFeatures,
    scores: ScoreResult,
    thresholds: HybridThresholds,
) -> tuple[str, dict[str, int], list[str]]:
    redacted = redact_email_for_llm(normalized)
    prompt = f"""Classify this redacted Gmail message. Use only the allowed categories.

Allowed categories:
- job_update
- interview_request
- action_item
- offer
- rejection
- conversation
- not_relevant

Precomputed local features:
- sender_domain: {features.sender_domain}
- matched_features: {features.matched_features}
- url_feature_types: {features.url_feature_types}
- job_signal_score: {scores.job_signal_score}
- noise_score: {scores.noise_score}
- category_scores: {scores.category_scores}
- threshold_version: {thresholds.version}

Redacted message:
From: {redacted.sender} <{redacted.sender_email}>
Subject: {redacted.subject}

{redacted.body[:3000]}"""
    return prompt, redacted.redaction_counts, redacted.redaction_reasons


async def adjudicate_with_llm(
    normalized: NormalizedEmail,
    features: EmailFeatures,
    scores: ScoreResult,
    fallback: HybridClassificationResult,
    thresholds: HybridThresholds,
    preflight_decision: GmailLlmPreflightDecision,
) -> HybridClassificationResult:
    if preflight_decision.blocked or not preflight_decision.should_call_llm or not preflight_decision.redacted_prompt:
        return _with_llm_fallback(
            fallback,
            decision_path="llm_quarantined",
            fallback_reason=preflight_decision.block_reason or "llm_preflight_not_passed",
            redaction_counts=preflight_decision.redaction_counts,
        )

    prompt = preflight_decision.redacted_prompt
    redaction_counts = preflight_decision.redaction_counts
    redaction_reasons = preflight_decision.redaction_reasons
    try:
        result = await ai_safety.run_json_task_with_safety(
            email_classifier.CLASSIFIER_TASK,
            prompt,
            metadata={
                "surface": "email_classifier_hybrid_adjudicator",
                "threshold_version": thresholds.version,
                "redaction_reasons": redaction_reasons,
                "llm_preflight": "passed",
            },
            data_classes=[
                ai_safety.DATA_CLASS_UNTRUSTED_INBOUND,
                ai_safety.DATA_CLASS_CAREER_PRIVATE,
            ],
            allow_identity=False,
            untrusted_input=True,
        )
        normalized_payload = email_classifier._normalize_model_result(  # noqa: SLF001
            result.payload,
            normalized.subject,
            normalized.sender_email,
            normalized.sender,
        )
        if normalized_payload is None:
            return _with_llm_fallback(
                fallback,
                decision_path="llm_invalid_fallback",
                fallback_reason="invalid_model_payload",
                redaction_counts=redaction_counts,
            )
        classification = str(normalized_payload.get("classification") or fallback.classification)
        job_related = classification != "not_relevant"
        return HybridClassificationResult(
            classification=classification,  # type: ignore[arg-type]
            job_related=job_related,
            confidence=float(normalized_payload.get("confidence") or fallback.confidence),
            confidence_band="high" if float(normalized_payload.get("confidence") or fallback.confidence) >= thresholds.category_accept else "medium",
            decision_path="llm_adjudicated",
            model_used=True,
            action_needed=action_needed_for_classification(classification, features) if job_related else False,
            is_automated=bool(normalized_payload.get("is_automated", is_automated_sender(features))),
            sender_role=str(normalized_payload.get("sender_role") or fallback.sender_role),
            company_name=normalized_payload.get("company_name"),
            key_sentence=str(normalized_payload.get("key_sentence") or fallback.key_sentence),
            summary=str(normalized_payload.get("summary") or fallback.summary),
            matched_features=fallback.matched_features,
            ambiguity_reasons=fallback.ambiguity_reasons,
            redaction_applied=True,
            redaction_counts=redaction_counts,
            prompt_tokens=result.tokens_in,
            output_tokens=result.tokens_out,
            retry_count=result.retries,
            model=result.model,
            cost_estimate_cents=_cost_from_tokens(result.model, result.tokens_in, result.tokens_out),
        )
    except ai_safety.AiSafetyQuarantinedError:
        return _with_llm_fallback(
            fallback,
            decision_path="llm_quarantined",
            fallback_reason="safety_quarantine",
            redaction_counts=redaction_counts,
        )
    except Exception:
        return _with_llm_fallback(
            fallback,
            decision_path="llm_unavailable_fallback",
            fallback_reason="model_task_failure",
            redaction_counts=redaction_counts,
        )


def _with_llm_fallback(
    fallback: HybridClassificationResult,
    *,
    decision_path: str,
    fallback_reason: str,
    redaction_counts: dict[str, int],
) -> HybridClassificationResult:
    return HybridClassificationResult(
        classification=fallback.classification,
        job_related=fallback.job_related,
        confidence=fallback.confidence,
        confidence_band=fallback.confidence_band,
        decision_path=decision_path,  # type: ignore[arg-type]
        model_used=False,
        action_needed=fallback.action_needed,
        is_automated=fallback.is_automated,
        sender_role=fallback.sender_role,
        company_name=fallback.company_name,
        key_sentence=fallback.key_sentence,
        summary=fallback.summary,
        matched_features=fallback.matched_features,
        ambiguity_reasons=fallback.ambiguity_reasons,
        redaction_applied=True,
        redaction_counts=redaction_counts,
        fallback_reason=fallback_reason,
    )
