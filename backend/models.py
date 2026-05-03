import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow():
    return datetime.now(timezone.utc)


def _new_uuid():
    return uuid.uuid4()


class Base(DeclarativeBase):
    pass


# --- Sprint 2: Company Entity ---

class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    domain: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry: Mapped[str | None] = mapped_column(Text, nullable=True)
    size: Mapped[str | None] = mapped_column(Text, nullable=True)
    ats_platform: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    applications: Mapped[list["Application"]] = relationship("Application", back_populates="company_ref")
    contacts: Mapped[list["Contact"]] = relationship("Contact", back_populates="company_ref")
    email_events: Mapped[list["EmailEvent"]] = relationship("EmailEvent", back_populates="company_ref")


# --- Sprint 3: Role Taxonomy ---

class RoleUmbrella(Base):
    __tablename__ = "role_umbrellas"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    aliases: Mapped[list | None] = mapped_column(JSON, nullable=True)
    typical_skills: Mapped[list | None] = mapped_column(JSON, nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("role_umbrellas.id"), nullable=True)

    applications: Mapped[list["Application"]] = relationship("Application", back_populates="umbrella")


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("user_id", "job_url", name="uq_applications_user_job_url"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    company: Mapped[str] = mapped_column(Text, nullable=False)
    role_title: Mapped[str] = mapped_column(Text, nullable=False)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    salary: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    status: Mapped[str] = mapped_column(Text, default="saved")
    status_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ats_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    last_email_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    follow_up_due: Mapped[bool] = mapped_column(Boolean, default=False)
    # Sprint 2: Company FK
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)
    # Sprint 3: Umbrella FK
    umbrella_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("role_umbrellas.id"), nullable=True)
    # Sprint 4: Tech stack
    tech_stack: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Sprint 5: Match score
    match_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Sprint 7: Dead application detection
    listing_alive: Mapped[bool] = mapped_column(Boolean, default=True)
    # Sprint 11: Response time tracking
    first_response_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    listing_last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    listing_died_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Sprint 16: Salary intelligence
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(Text, nullable=True)
    salary_period: Mapped[str | None] = mapped_column(Text, nullable=True)  # yearly/monthly/hourly

    contacts: Mapped[list["Contact"]] = relationship("Contact", back_populates="application", cascade="all, delete-orphan")
    email_events: Mapped[list["EmailEvent"]] = relationship("EmailEvent", back_populates="application")
    company_ref: Mapped["Company | None"] = relationship("Company", back_populates="applications")
    umbrella: Mapped["RoleUmbrella | None"] = relationship("RoleUmbrella", back_populates="applications")
    interviews: Mapped[list["Interview"]] = relationship("Interview", back_populates="application", cascade="all, delete-orphan")


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reached_out: Mapped[bool] = mapped_column(Boolean, default=False)
    reached_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_received: Mapped[bool] = mapped_column(Boolean, default=False)
    # Sprint 2: Company FK
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)

    application: Mapped["Application"] = relationship("Application", back_populates="contacts")
    company_ref: Mapped["Company | None"] = relationship("Company", back_populates="contacts")


class IgnoredNetworkContact(Base):
    __tablename__ = "ignored_network_contacts"
    __table_args__ = (
        UniqueConstraint("user_id", "email", name="uq_ignored_network_contact_user_email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ContactDistinctDecision(Base):
    __tablename__ = "contact_distinct_decisions"
    __table_args__ = (
        UniqueConstraint("user_id", "email_a", "email_b", name="uq_contact_distinct_user_pair"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_a: Mapped[str] = mapped_column(Text, nullable=False)
    email_b: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class EmailEvent(Base):
    __tablename__ = "email_events"
    __table_args__ = (
        UniqueConstraint("user_id", "gmail_message_id", name="uq_email_events_user_gmail_message_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("applications.id", ondelete="SET NULL"), nullable=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id"), nullable=True)
    gmail_message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    thread_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    sender: Mapped[str | None] = mapped_column(Text, nullable=True)
    sender_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pipeline: Mapped[str | None] = mapped_column(Text, nullable=True)
    classification: Mapped[str | None] = mapped_column(Text, nullable=True)
    color_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    urgency: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_needed: Mapped[bool] = mapped_column(Boolean, default=False)
    action_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_human: Mapped[bool] = mapped_column(Boolean, default=False)
    is_from_user: Mapped[bool] = mapped_column(Boolean, default=False)
    email_type: Mapped[str | None] = mapped_column(Text, nullable=True)  # 'decision' | 'conversation'
    key_sentence: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    collapsed: Mapped[bool] = mapped_column(Boolean, default=False)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    company_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    sender_domain: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Sprint 1: resolved flag
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    # Sprint 2: Company FK
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)

    application: Mapped["Application | None"] = relationship("Application", back_populates="email_events")
    company_ref: Mapped["Company | None"] = relationship("Company", back_populates="email_events")


class EmailFeedback(Base):
    """User feedback on email classification — powers the learning loop."""
    __tablename__ = "email_feedback"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    email_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("email_events.id", ondelete="CASCADE"))
    is_job_related: Mapped[bool] = mapped_column(Boolean, nullable=False)
    sender_domain: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ApplicationSuggestionDecision(Base):
    """User review decision for an email-derived pipeline suggestion."""
    __tablename__ = "application_suggestion_decisions"
    __table_args__ = (
        UniqueConstraint("user_id", "suggestion_key", name="uq_app_suggestion_decision_user_key"),
        Index("ix_app_suggestion_decisions_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    suggestion_key: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    application_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("applications.id", ondelete="SET NULL"), nullable=True)
    email_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class InterviewSuggestionDecision(Base):
    """User review decision for an email-derived interview suggestion."""
    __tablename__ = "interview_suggestion_decisions"
    __table_args__ = (
        UniqueConstraint("user_id", "email_event_id", name="uq_interview_suggestion_decision_user_email"),
        Index("ix_interview_suggestion_decisions_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    email_event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("email_events.id", ondelete="CASCADE"), nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    interview_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("interviews.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class EmailSyncAudit(Base):
    """Per-message Gmail sync decision log for user-visible sync diagnostics."""
    __tablename__ = "email_sync_audit"
    __table_args__ = (
        Index("ix_email_sync_audit_user_created", "user_id", "created_at"),
        Index("ix_email_sync_audit_run", "sync_run_id", "created_at"),
        Index("ix_email_sync_audit_user_decision", "user_id", "decision", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    sync_run_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    email_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("email_events.id", ondelete="SET NULL"), nullable=True)
    gmail_message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    thread_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    sender: Mapped[str | None] = mapped_column(Text, nullable=True)
    sender_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    sender_domain: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    classification: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class JobListing(Base):
    __tablename__ = "job_listings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    company: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    description_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)


class ScraperError(Base):
    __tablename__ = "scraper_errors"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    platform: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    html_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    google_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    picture: Mapped[str | None] = mapped_column(Text, nullable=True)
    gmail_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    calendar_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    notifications_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    api_key_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    api_key_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    api_key_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    api_key_last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    # Sprint 6: Onboarding
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    preferred_locations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    preferred_remote_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Data consent
    data_consent_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    gmail_tokens: Mapped[list["GmailToken"]] = relationship("GmailToken", back_populates="user", cascade="all, delete-orphan")
    role_interests: Mapped[list["UserRoleInterest"]] = relationship("UserRoleInterest", back_populates="user", cascade="all, delete-orphan")
    profile: Mapped["UserProfile | None"] = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    consents: Mapped[list["DataConsent"]] = relationship("DataConsent", back_populates="user", cascade="all, delete-orphan")


class GmailToken(Base):
    __tablename__ = "gmail_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped["User | None"] = relationship("User", back_populates="gmail_tokens")


# Sprint 4: Company Tech Profile
class CompanyTechProfile(Base):
    __tablename__ = "company_tech_profiles"
    __table_args__ = (
        UniqueConstraint("company_id", "tech_name", name="uq_company_tech"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    tech_name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    mention_count: Mapped[int] = mapped_column(Integer, default=1)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# Sprint 5: User Profile (resume intelligence)
class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills: Mapped[list | None] = mapped_column(JSON, nullable=True)
    education: Mapped[list | None] = mapped_column(JSON, nullable=True)
    experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tools: Mapped[list | None] = mapped_column(JSON, nullable=True)
    certifications: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped["User | None"] = relationship("User", back_populates="profile")


# Sprint 6: User Role Interest (many-to-many)
class UserRoleInterest(Base):
    __tablename__ = "user_role_interests"
    __table_args__ = (
        UniqueConstraint("user_id", "umbrella_id", name="uq_user_role_interest"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    umbrella_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("role_umbrellas.id", ondelete="CASCADE"))

    user: Mapped["User"] = relationship("User", back_populates="role_interests")
    umbrella: Mapped["RoleUmbrella"] = relationship("RoleUmbrella")


# Sprint 8: ATS Behavior
class AtsBehavior(Base):
    __tablename__ = "ats_behaviors"
    __table_args__ = (
        UniqueConstraint("platform", "metric_name", name="uq_ats_metric"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    metric_name: Mapped[str] = mapped_column(Text, nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# Sprint 9: Warm Connections
class WarmConnection(Base):
    __tablename__ = "warm_connections"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    company_domain: Mapped[str] = mapped_column(Text, nullable=False)
    contact_email: Mapped[str] = mapped_column(Text, nullable=False)
    contact_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_count: Mapped[int] = mapped_column(Integer, default=1)
    last_interaction_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# Sprint 11: Alerts
# Sprint 13: Interview
class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    application_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    interview_type: Mapped[str] = mapped_column(Text, default="phone")  # phone/technical/onsite/panel
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interviewer_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    interviewer_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_or_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str] = mapped_column(Text, default="pending")  # pending/passed/failed
    calendar_event_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    application: Mapped["Application | None"] = relationship("Application", back_populates="interviews")


# Sprint 17: Company Visits (career page browsing tracking)
class CompanyVisit(Base):
    __tablename__ = "company_visits"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    visit_count: Mapped[int] = mapped_column(Integer, default=1)
    first_visited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_visited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# Sprint 18: Interview Notes
class InterviewNote(Base):
    __tablename__ = "interview_notes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    interview_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"), nullable=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=True)
    questions_asked: Mapped[str | None] = mapped_column(Text, nullable=True)
    went_well: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_improve: Mapped[str | None] = mapped_column(Text, nullable=True)
    overall_feeling: Mapped[str | None] = mapped_column(Text, nullable=True)  # great/good/okay/poor
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    interview: Mapped["Interview | None"] = relationship("Interview", backref="interview_notes")


# Sprint 19: Notification Preferences
class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=True)
    sms_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    sms_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    weekly_digest_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    browser_notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    radar_updates_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    inbox_updates_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    conversations_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    network_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    interviews_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    followups_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    listings_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    quiet_hours_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    quiet_hours_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quiet_hours_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# Sprint 20: Resume Draft
class ResumeDraft(Base):
    __tablename__ = "resume_drafts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=True)
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    tailored_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    changes_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    application: Mapped["Application | None"] = relationship("Application")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    alert_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ExtractionReport(Base):
    __tablename__ = "extraction_reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # "missing_data" | "undetected_site" | "false_positive" | "wrong_data"
    report_type: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str | None] = mapped_column(Text, nullable=True)
    platform_detected: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    # What our extractor returned (JSON)
    extracted_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # What the user corrected it to (JSON)
    corrected_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Which fields were flagged as wrong/missing
    fields_flagged: Mapped[list | None] = mapped_column(JSON, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    extension_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Granular extractor logic version (bumped with each extraction logic change)
    extractor_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ExtractionChangelog(Base):
    __tablename__ = "extraction_changelog"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    version: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Which platforms were affected by this change
    platforms_affected: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Which fields were affected (salary, description, company, etc.)
    fields_affected: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # "extraction" | "classifier" | "both"
    change_type: Mapped[str] = mapped_column(Text, default="extraction")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class DataConsent(Base):
    __tablename__ = "data_consents"
    __table_args__ = (
        UniqueConstraint("user_id", "consent_type", name="uq_user_consent_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    consent_type: Mapped[str] = mapped_column(String(50), nullable=False)  # core | ai_processing | third_party_enrichment | web_research
    granted: Mapped[bool] = mapped_column(Boolean, default=False)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped["User"] = relationship("User", back_populates="consents")


class ResearchProfile(Base):
    __tablename__ = "research_profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_domains: Mapped[list | None] = mapped_column(JSON, nullable=True)
    selected_roles: Mapped[list | None] = mapped_column(JSON, nullable=True)
    selected_companies: Mapped[list | None] = mapped_column(JSON, nullable=True)
    keywords: Mapped[list | None] = mapped_column(JSON, nullable=True)
    excluded_keywords: Mapped[list | None] = mapped_column(JSON, nullable=True)
    source_types: Mapped[list | None] = mapped_column(JSON, nullable=True)
    mode: Mapped[str] = mapped_column(Text, default="internal")
    frequency: Mapped[str] = mapped_column(Text, default="daily")
    depth: Mapped[str] = mapped_column(Text, default="standard")
    notification_mode: Mapped[str] = mapped_column(Text, default="in_app")
    minimum_score: Mapped[int] = mapped_column(Integer, default=70)
    target_locations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    remote_types: Mapped[list | None] = mapped_column(JSON, nullable=True)
    seniority_levels: Mapped[list | None] = mapped_column(JSON, nullable=True)
    research_source_scopes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    use_profile_context: Mapped[bool] = mapped_column(Boolean, default=True)
    include_public_web_research: Mapped[bool] = mapped_column(Boolean, default=False)
    report_prompt_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_search_queries: Mapped[int] = mapped_column(Integer, default=8)
    max_sources_per_run: Mapped[int] = mapped_column(Integer, default=20)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ResearchRun(Base):
    __tablename__ = "research_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_profiles.id", ondelete="CASCADE"), nullable=False)
    run_type: Mapped[str] = mapped_column(Text, default="manual")
    mode: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="queued")
    orchestrator_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    graph_thread_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_step: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_counts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    signal_counts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_call_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ResearchRunStep(Base):
    __tablename__ = "research_run_steps"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_profiles.id", ondelete="CASCADE"), nullable=True)
    step_name: Mapped[str] = mapped_column(Text, nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="queued")
    model_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ResearchReport(Base):
    __tablename__ = "research_reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_profiles.id", ondelete="CASCADE"), nullable=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_runs.id", ondelete="SET NULL"), nullable=True)
    report_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    diff_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="draft")
    overall_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    finding_count: Mapped[int] = mapped_column(Integer, default=0)
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    new_findings_count: Mapped[int] = mapped_column(Integer, default=0)
    changed_findings_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ResearchReportSection(Base):
    __tablename__ = "research_report_sections"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    report_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_reports.id", ondelete="CASCADE"), nullable=False)
    section_key: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ResearchEvidenceItem(Base):
    __tablename__ = "research_evidence_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=True)
    report_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_reports.id", ondelete="CASCADE"), nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_profiles.id", ondelete="CASCADE"), nullable=True)
    source_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_source_items.id", ondelete="SET NULL"), nullable=True)
    evidence_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    role_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    novelty_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    structured_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ResearchSourceItem(Base):
    __tablename__ = "research_source_items"
    __table_args__ = (
        UniqueConstraint("user_id", "source_url", "content_hash", name="uq_research_source_user_url_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_runs.id", ondelete="SET NULL"), nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_profiles.id", ondelete="CASCADE"), nullable=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_handle: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class OpportunitySignal(Base):
    __tablename__ = "opportunity_signals"
    __table_args__ = (
        UniqueConstraint("user_id", "source_item_id", "event_type", name="uq_opportunity_signal_user_source_event"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_profiles.id", ondelete="CASCADE"), nullable=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_runs.id", ondelete="SET NULL"), nullable=True)
    source_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_source_items.id", ondelete="SET NULL"), nullable=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("applications.id", ondelete="SET NULL"), nullable=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[list | None] = mapped_column(JSON, nullable=True)
    people: Mapped[list | None] = mapped_column(JSON, nullable=True)
    domains: Mapped[list | None] = mapped_column(JSON, nullable=True)
    roles: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tech_stack: Mapped[list | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class OpportunityScore(Base):
    __tablename__ = "opportunity_scores"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    signal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunity_signals.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_profiles.id", ondelete="CASCADE"), nullable=True)
    total_score: Mapped[int] = mapped_column(Integer, nullable=False)
    role_fit: Mapped[float] = mapped_column(Float, default=0.0)
    domain_fit: Mapped[float] = mapped_column(Float, default=0.0)
    company_interest: Mapped[float] = mapped_column(Float, default=0.0)
    recency: Mapped[float] = mapped_column(Float, default=0.0)
    public_data_buildability: Mapped[float] = mapped_column(Float, default=0.0)
    outreach_path_strength: Mapped[float] = mapped_column(Float, default=0.0)
    portfolio_gap_relevance: Mapped[float] = mapped_column(Float, default=0.0)
    source_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class OpportunityBrief(Base):
    __tablename__ = "opportunity_briefs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_profiles.id", ondelete="CASCADE"), nullable=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_runs.id", ondelete="SET NULL"), nullable=True)
    signal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("opportunity_signals.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    brief_type: Mapped[str] = mapped_column(Text, nullable=False)
    markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class RecommendedAction(Base):
    __tablename__ = "recommended_actions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_profiles.id", ondelete="CASCADE"), nullable=True)
    signal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("opportunity_signals.id", ondelete="SET NULL"), nullable=True)
    brief_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("opportunity_briefs.id", ondelete="SET NULL"), nullable=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("applications.id", ondelete="SET NULL"), nullable=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=50)
    status: Mapped[str] = mapped_column(Text, default="open")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchFeedback(Base):
    __tablename__ = "research_feedback"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    signal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("opportunity_signals.id", ondelete="CASCADE"), nullable=True)
    brief_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("opportunity_briefs.id", ondelete="CASCADE"), nullable=True)
    action_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recommended_actions.id", ondelete="CASCADE"), nullable=True)
    report_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_reports.id", ondelete="CASCADE"), nullable=True)
    run_step_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_run_steps.id", ondelete="CASCADE"), nullable=True)
    feedback_scope: Mapped[str] = mapped_column(Text, default="signal")
    rating: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SearchDocument(Base):
    __tablename__ = "search_documents"
    __table_args__ = (
        UniqueConstraint("user_id", "source_type", "source_id", name="uq_search_documents_user_source"),
        Index("ix_search_documents_user_type_indexed", "user_id", "source_type", "indexed_at"),
        Index("ix_search_documents_user_indexed", "user_id", "indexed_at"),
        Index("ix_search_documents_source", "source_type", "source_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    subtitle: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords: Mapped[list | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CopilotConversation(Base):
    __tablename__ = "copilot_conversations"
    __table_args__ = (
        Index("ix_copilot_conversations_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(Text, default="New conversation")
    status: Mapped[str] = mapped_column(Text, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CopilotMessage(Base):
    __tablename__ = "copilot_messages"
    __table_args__ = (
        Index("ix_copilot_messages_conversation_created", "conversation_id", "created_at"),
        Index("ix_copilot_messages_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("copilot_conversations.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    suggested_actions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model_call_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_model_calls.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CopilotFeedback(Base):
    __tablename__ = "copilot_feedback"
    __table_args__ = (
        UniqueConstraint("user_id", "message_id", name="uq_copilot_feedback_user_message"),
        Index("ix_copilot_feedback_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("copilot_messages.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rating: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AiExperiment(Base):
    __tablename__ = "ai_experiments"
    __table_args__ = (
        UniqueConstraint("experiment_key", name="uq_ai_experiments_key"),
        Index("ix_ai_experiments_surface_task_status", "surface", "task_name", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    experiment_key: Mapped[str] = mapped_column(Text, nullable=False)
    surface: Mapped[str] = mapped_column(Text, nullable=False)
    task_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="draft")
    control_variant: Mapped[str] = mapped_column(Text, default="control")
    candidate_variants: Mapped[list | None] = mapped_column(JSON, nullable=True)
    traffic_allocation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    guardrail_thresholds: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AiExperimentAssignment(Base):
    __tablename__ = "ai_experiment_assignments"
    __table_args__ = (
        UniqueConstraint("experiment_id", "user_id", name="uq_ai_experiment_assignment_user"),
        Index("ix_ai_experiment_assignments_variant", "experiment_id", "variant"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    experiment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_experiments.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    variant: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_by: Mapped[str] = mapped_column(Text, default="deterministic_hash")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AiFeedbackRewardEvent(Base):
    __tablename__ = "ai_feedback_reward_events"
    __table_args__ = (
        UniqueConstraint("feedback_id", name="uq_ai_feedback_reward_feedback"),
        Index("ix_ai_feedback_reward_model_call", "model_call_id", "created_at"),
        Index("ix_ai_feedback_reward_variant", "experiment_key", "variant", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    feedback_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("copilot_feedback.id", ondelete="CASCADE"), nullable=False)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("copilot_messages.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    model_call_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_model_calls.id", ondelete="SET NULL"), nullable=True)
    experiment_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    variant: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[str] = mapped_column(Text, nullable=False)
    reward_score: Mapped[float] = mapped_column(Float, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AiShadowRun(Base):
    __tablename__ = "ai_shadow_runs"
    __table_args__ = (
        Index("ix_ai_shadow_runs_experiment_created", "experiment_id", "created_at"),
        Index("ix_ai_shadow_runs_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    experiment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_experiments.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    production_model_call_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_model_calls.id", ondelete="SET NULL"), nullable=True)
    candidate_variant: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(Text, default="queued")
    visible_to_user: Mapped[bool] = mapped_column(Boolean, default=False)
    output_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AiPromotionReport(Base):
    __tablename__ = "ai_promotion_reports"
    __table_args__ = (
        Index("ix_ai_promotion_reports_experiment_created", "experiment_id", "created_at"),
        Index("ix_ai_promotion_reports_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    experiment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_experiments.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(Text, default="pending_review")
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    report_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    generated_after_calls: Mapped[int] = mapped_column(Integer, default=0)
    generated_after_feedback: Mapped[int] = mapped_column(Integer, default=0)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AiModelPricing(Base):
    __tablename__ = "ai_model_pricing"
    __table_args__ = (
        UniqueConstraint("provider", "model", "effective_at", name="uq_ai_model_pricing_provider_model_effective"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    provider: Mapped[str] = mapped_column(Text, default="openai")
    model: Mapped[str] = mapped_column(Text, nullable=False)
    input_token_cents_per_1m: Mapped[float] = mapped_column(Float, default=0.0)
    output_token_cents_per_1m: Mapped[float] = mapped_column(Float, default=0.0)
    cached_input_token_cents_per_1m: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasoning_token_cents_per_1m: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AiModelCard(Base):
    __tablename__ = "ai_model_cards"
    __table_args__ = (
        UniqueConstraint("task_name", "model", "prompt_version", name="uq_ai_model_card_task_model_prompt"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    task_name: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    intended_use: Mapped[str] = mapped_column(Text, nullable=False)
    prohibited_use: Mapped[str | None] = mapped_column(Text, nullable=True)
    limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    eval_dataset_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    guardrail_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    approval_status: Mapped[str] = mapped_column(Text, default="draft")
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rollback_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_cadence: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AiModelCall(Base):
    __tablename__ = "ai_model_calls"
    __table_args__ = (
        Index("ix_ai_model_calls_user_created", "user_id", "created_at"),
        Index("ix_ai_model_calls_surface_task_created", "surface", "task_name", "created_at"),
        Index("ix_ai_model_calls_model_prompt_created", "model", "prompt_version", "created_at"),
        Index("ix_ai_model_calls_variant_created", "variant", "created_at"),
        Index("ix_ai_model_calls_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    surface: Mapped[str] = mapped_column(Text, nullable=False)
    task_name: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, default="openai")
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    variant: Mapped[str | None] = mapped_column(Text, nullable=True)
    release_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    validation_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)
    fallback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    context_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tool_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    billable_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    billable_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    request_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    response_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_class: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_card_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_model_cards.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AiSafetyDecision(Base):
    __tablename__ = "ai_safety_decisions"
    __table_args__ = (
        Index("ix_ai_safety_decisions_user_created", "user_id", "created_at"),
        Index("ix_ai_safety_decisions_surface_task_created", "surface", "task_name", "created_at"),
        Index("ix_ai_safety_decisions_decision_created", "policy_decision", "created_at"),
        Index("ix_ai_safety_decisions_risk_created", "risk_score", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    model_call_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_model_calls.id", ondelete="SET NULL"), nullable=True)
    surface: Mapped[str] = mapped_column(Text, nullable=False)
    task_name: Mapped[str] = mapped_column(Text, nullable=False)
    stage: Mapped[str] = mapped_column(Text, nullable=False, default="preflight")
    policy_decision: Mapped[str] = mapped_column(Text, nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    prompt_injection_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    input_data_classes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    consent_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    redaction_counts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reasons: Mapped[list | None] = mapped_column(JSON, nullable=True)
    token_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AiArtifact(Base):
    __tablename__ = "ai_artifacts"
    __table_args__ = (
        Index("ix_ai_artifacts_user_created", "user_id", "created_at"),
        Index("ix_ai_artifacts_call_created", "model_call_id", "created_at"),
        Index("ix_ai_artifacts_type_ref", "artifact_type", "artifact_ref_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    model_call_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_model_calls.id", ondelete="SET NULL"), nullable=True)
    artifact_type: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_ref_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    path: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AiAdminAccessLog(Base):
    __tablename__ = "ai_admin_access_logs"
    __table_args__ = (
        Index("ix_ai_admin_access_logs_admin_created", "admin_user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    admin_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
