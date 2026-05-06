"""Typed contracts for the hybrid Gmail classifier."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

EmailClassification = Literal[
    "job_update",
    "interview_request",
    "action_item",
    "offer",
    "rejection",
    "conversation",
    "not_relevant",
]

DecisionPath = Literal[
    "deterministic_high_confidence",
    "deterministic_noise_skip",
    "deterministic_low_signal_skip",
    "llm_adjudicated",
    "llm_invalid_fallback",
    "llm_quarantined",
    "llm_unavailable_fallback",
    "ambiguous_no_model_fallback",
]


@dataclass(frozen=True)
class HybridThresholds:
    version: str = "classifier-thresholds-v1"
    job_related_accept: float = 0.55
    job_related_ambiguous: float = 0.35
    noise_skip: float = 0.75
    category_accept: float = 0.70
    category_margin: float = 0.20
    llm_escalation_min_job_score: float = 0.45
    llm_call_rate_budget: float = 0.25


@dataclass(frozen=True)
class EmailCandidate:
    subject: str
    body: str
    sender: str
    sender_email: str = ""
    received_at: datetime | None = None
    raw_candidate_urls: tuple[str, ...] = ()
    user_company_domains: frozenset[str] = frozenset()


@dataclass(frozen=True)
class NormalizedEmail:
    subject: str
    body: str
    sender: str
    sender_email: str
    subject_norm: str
    body_norm: str
    sender_norm: str
    combined_norm: str


@dataclass(frozen=True)
class RedactedEmail:
    subject: str
    body: str
    sender: str
    sender_email: str
    redaction_counts: dict[str, int] = field(default_factory=dict)
    redaction_reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EmailFeatures:
    sender_domain: str
    sender_local_part: str
    is_ats_domain: bool
    is_known_company_domain: bool
    is_noise_domain: bool
    is_likely_person: bool
    has_recruiting_sender_signal: bool
    has_job_signal: bool
    has_scheduler_url: bool
    has_private_url_signal: bool
    matched_features: list[str]
    category_feature_hits: dict[str, list[str]]
    url_feature_types: list[str]


@dataclass(frozen=True)
class ScoreResult:
    job_signal_score: float
    noise_score: float
    category_scores: dict[EmailClassification, float]
    top_category: EmailClassification
    top_score: float
    second_score: float
    margin: float


@dataclass(frozen=True)
class HybridClassificationResult:
    classification: EmailClassification
    job_related: bool
    confidence: float
    confidence_band: Literal["high", "medium", "low"]
    decision_path: DecisionPath
    model_used: bool
    action_needed: bool
    is_automated: bool
    sender_role: str
    company_name: str | None
    key_sentence: str
    summary: str
    matched_features: list[str]
    ambiguity_reasons: list[str]
    redaction_applied: bool = False
    redaction_counts: dict[str, int] = field(default_factory=dict)
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    retry_count: int = 0
    model: str | None = None
    cost_estimate_cents: float = 0.0
    fallback_reason: str | None = None

