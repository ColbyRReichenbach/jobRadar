from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class NormalizedResearchBrief(BaseModel):
    search_objective: str
    ideal_role_titles: list[str] = Field(default_factory=list)
    target_domains: list[str] = Field(default_factory=list)
    target_companies: list[str] = Field(default_factory=list)
    target_locations: list[str] = Field(default_factory=list)
    remote_preferences: list[str] = Field(default_factory=list)
    seniority: list[str] = Field(default_factory=list)
    must_have_signals: list[str] = Field(default_factory=list)
    avoid_signals: list[str] = Field(default_factory=list)
    fit_summary: str
    search_constraints: list[str] = Field(default_factory=list)


class ResearchSearchTask(BaseModel):
    task_id: str
    task_type: Literal[
        "role_openings",
        "company_hiring_signal",
        "team_growth_signal",
        "tech_stack_signal",
        "company_strategy_signal",
    ]
    query: str
    company_hint: str | None = None
    role_hint: str | None = None
    expected_signal_type: str | None = None
    max_results: int = Field(default=5, ge=1, le=10)
    priority: int = Field(default=50, ge=1, le=100)
    candidates: list[dict] = Field(default_factory=list)


class SearchCandidate(BaseModel):
    url: str
    title: str
    snippet: str | None = None
    source_type: str
    domain: str | None = None
    published_at: str | None = None
    why_selected: str | None = None


class ExtractedEvidence(BaseModel):
    source_item_id: str | None = None
    evidence_type: str
    title: str | None = None
    claim: str
    snippet: str | None = None
    url: str | None = None
    domain: str | None = None
    company_name: str | None = None
    role_title: str | None = None
    published_at: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    relevance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    novelty_score: float = Field(default=0.5, ge=0.0, le=1.0)
    supports_objective: bool = True
    citation_ids: list[str] = Field(default_factory=list)


class ReportSectionDraft(BaseModel):
    section_key: str
    title: str
    display_order: int
    markdown: str
    structured_json: dict = Field(default_factory=dict)


class ReportActionDraft(BaseModel):
    action_type: str
    title: str
    body: str | None = None
    priority: int = Field(default=50, ge=1, le=100)
    payload: dict = Field(default_factory=dict)


class VerificationResult(BaseModel):
    unsupported_claim_count: int = 0
    section_completeness: float = Field(default=1.0, ge=0.0, le=1.0)
    tracker_fit_score: float = Field(default=0.8, ge=0.0, le=1.0)
    citation_coverage: float = Field(default=1.0, ge=0.0, le=1.0)
    hallucination_risk: Literal["low", "medium", "high"] = "low"
    status: Literal["ready", "needs_review"] = "ready"
    notes: list[str] = Field(default_factory=list)


class FinalReportDraft(BaseModel):
    title: str
    summary_markdown: str
    structured_json: dict = Field(default_factory=dict)
    diff_summary: str | None = None
    status: str = "draft"
    overall_confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    finding_count: int = Field(default=0, ge=0)
    source_count: int = Field(default=0, ge=0)
    new_findings_count: int = Field(default=0, ge=0)
    changed_findings_count: int = Field(default=0, ge=0)
