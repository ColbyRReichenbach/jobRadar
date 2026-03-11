import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, text
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

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    company: Mapped[str] = mapped_column(Text, nullable=False)
    role_title: Mapped[str] = mapped_column(Text, nullable=False)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_url: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
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


class EmailEvent(Base):
    __tablename__ = "email_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("applications.id", ondelete="SET NULL"), nullable=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id"), nullable=True)
    gmail_message_id: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
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
    api_key_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    api_key_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    api_key_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    api_key_last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    # Sprint 6: Onboarding
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    preferred_locations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    preferred_remote_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)

    gmail_tokens: Mapped[list["GmailToken"]] = relationship("GmailToken", back_populates="user", cascade="all, delete-orphan")
    role_interests: Mapped[list["UserRoleInterest"]] = relationship("UserRoleInterest", back_populates="user", cascade="all, delete-orphan")
    profile: Mapped["UserProfile | None"] = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")


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
