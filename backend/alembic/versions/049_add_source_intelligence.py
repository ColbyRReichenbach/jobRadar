"""add source intelligence tables

Revision ID: 049_add_source_intelligence
Revises: 048_add_ai_safety_review
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "049_add_source_intelligence"
down_revision = "048_add_ai_safety_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_job_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("company_name", sa.Text(), nullable=False),
        sa.Column("company_domain", sa.Text(), nullable=True),
        sa.Column("provider_type", sa.Text(), nullable=False),
        sa.Column("provider_key", sa.Text(), nullable=True),
        sa.Column("access_mode", sa.Text(), nullable=False, server_default="unknown"),
        sa.Column("career_url", sa.Text(), nullable=True),
        sa.Column("public_jobs_endpoint", sa.Text(), nullable=True),
        sa.Column("source_config", sa.JSON(), nullable=True),
        sa.Column("source_confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("verification_status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("robots_allowed", sa.Boolean(), nullable=True),
        sa.Column("terms_risk", sa.Text(), nullable=False, server_default="unknown"),
        sa.Column("discovered_from", sa.Text(), nullable=False),
        sa.Column("verified_by", sa.Text(), nullable=True),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stale_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_company_job_sources_identity",
        "company_job_sources",
        [
            sa.text("provider_type"),
            sa.text("coalesce(provider_key, '')"),
            sa.text("access_mode"),
            sa.text("coalesce(company_domain, '')"),
            sa.text("coalesce(career_url, '')"),
        ],
        unique=True,
    )
    op.create_index("ix_company_job_sources_domain_provider_active", "company_job_sources", ["company_domain", "provider_type", "active"])
    op.create_index(
        "ix_company_job_sources_status_active_mode_verified",
        "company_job_sources",
        ["verification_status", "active", "access_mode", "last_verified_at"],
    )
    op.create_index("ix_company_job_sources_company_active", "company_job_sources", ["company_id", "active"])

    op.create_table(
        "user_application_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("email_event_id", sa.Uuid(), nullable=True),
        sa.Column("raw_url_encrypted", sa.Text(), nullable=True),
        sa.Column("raw_url_hash", sa.Text(), nullable=False),
        sa.Column("raw_url_hash_version", sa.Text(), nullable=False, server_default="v1"),
        sa.Column("canonical_public_url", sa.Text(), nullable=True),
        sa.Column("canonical_public_url_hash", sa.Text(), nullable=True),
        sa.Column("canonical_public_url_hash_version", sa.Text(), nullable=True),
        sa.Column("link_type", sa.Text(), nullable=False),
        sa.Column("provider_type", sa.Text(), nullable=True),
        sa.Column("provider_key", sa.Text(), nullable=True),
        sa.Column("company_domain", sa.Text(), nullable=True),
        sa.Column("contains_private_token", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sanitization_status", sa.Text(), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("parser_version", sa.Text(), nullable=True),
        sa.Column("encryption_key_version", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["email_event_id"], ["email_events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "raw_url_hash", name="uq_user_application_links_user_raw_hash"),
    )
    op.create_index("ix_user_application_links_user_application", "user_application_links", ["user_id", "application_id"])
    op.create_index("ix_user_application_links_user_type_created", "user_application_links", ["user_id", "link_type", "created_at"])
    op.create_index("ix_user_application_links_provider_key", "user_application_links", ["provider_type", "provider_key"])

    op.create_table(
        "source_discovery_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("email_event_id", sa.Uuid(), nullable=True),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("provider_type", sa.Text(), nullable=True),
        sa.Column("company_domain", sa.Text(), nullable=True),
        sa.Column("confidence_delta", sa.Float(), nullable=False, server_default="0"),
        sa.Column("redacted_evidence", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["email_event_id"], ["email_events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_id"], ["company_job_sources.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "job_postings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("external_job_id", sa.Text(), nullable=True),
        sa.Column("dedupe_key", sa.Text(), nullable=False),
        sa.Column("company_name", sa.Text(), nullable=False),
        sa.Column("company_domain", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("normalized_title", sa.Text(), nullable=True),
        sa.Column("description_text", sa.Text(), nullable=True),
        sa.Column("description_hash", sa.Text(), nullable=True),
        sa.Column("location_text", sa.Text(), nullable=True),
        sa.Column("remote_status", sa.Text(), nullable=True),
        sa.Column("employment_type", sa.Text(), nullable=True),
        sa.Column("department", sa.Text(), nullable=True),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("salary_currency", sa.Text(), nullable=True),
        sa.Column("salary_period", sa.Text(), nullable=True),
        sa.Column("date_posted", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_through", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("inactive_reason", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["company_job_sources.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_job_postings_dedupe_key"),
    )
    op.create_index("ix_job_postings_company_active_seen", "job_postings", ["company_domain", "active", "last_seen_at"])
    op.create_index("ix_job_postings_source_active_seen", "job_postings", ["source_type", "active", "last_seen_at"])
    op.create_index("ix_job_postings_title_active", "job_postings", ["normalized_title", "active"])
    op.create_index("ix_job_postings_verified_active", "job_postings", ["last_verified_at", "active"])

    op.create_table(
        "application_source_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("job_posting_id", sa.Uuid(), nullable=True),
        sa.Column("company_job_source_id", sa.Uuid(), nullable=True),
        sa.Column("user_application_link_id", sa.Uuid(), nullable=True),
        sa.Column("relationship_type", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_from", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_job_source_id"], ["company_job_sources.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_posting_id"], ["job_postings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_application_link_id"], ["user_application_links.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_id", "job_posting_id", "relationship_type", name="uq_application_source_links_posting"),
        sa.UniqueConstraint("application_id", "user_application_link_id", "relationship_type", name="uq_application_source_links_private_link"),
    )
    op.create_index("ix_application_source_links_user_application", "application_source_links", ["user_id", "application_id"])
    op.create_index("ix_application_source_links_source_relationship", "application_source_links", ["company_job_source_id", "relationship_type"])

    op.create_table(
        "source_verification_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("job_count", sa.Integer(), nullable=True),
        sa.Column("new_job_count", sa.Integer(), nullable=True),
        sa.Column("inactive_job_count", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.Text(), nullable=True),
        sa.Column("error_message_redacted", sa.Text(), nullable=True),
        sa.Column("robots_allowed", sa.Boolean(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["company_job_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "job_search_provider_usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("user_key", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("request_mode", sa.Text(), nullable=False),
        sa.Column("query_hash", sa.Text(), nullable=False),
        sa.Column("month_bucket", sa.Date(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_key", "provider", "request_mode", "query_hash", "month_bucket", name="uq_job_search_provider_usage_bucket"),
    )
    op.create_index("ix_job_search_provider_usage_provider_month", "job_search_provider_usage", ["provider", "month_bucket"])
    op.create_index("ix_job_search_provider_usage_user_provider_month", "job_search_provider_usage", ["user_id", "provider", "month_bucket"])


def downgrade() -> None:
    op.drop_index("ix_job_search_provider_usage_user_provider_month", table_name="job_search_provider_usage")
    op.drop_index("ix_job_search_provider_usage_provider_month", table_name="job_search_provider_usage")
    op.drop_table("job_search_provider_usage")
    op.drop_table("source_verification_runs")
    op.drop_index("ix_application_source_links_source_relationship", table_name="application_source_links")
    op.drop_index("ix_application_source_links_user_application", table_name="application_source_links")
    op.drop_table("application_source_links")
    op.drop_index("ix_job_postings_verified_active", table_name="job_postings")
    op.drop_index("ix_job_postings_title_active", table_name="job_postings")
    op.drop_index("ix_job_postings_source_active_seen", table_name="job_postings")
    op.drop_index("ix_job_postings_company_active_seen", table_name="job_postings")
    op.drop_table("job_postings")
    op.drop_table("source_discovery_events")
    op.drop_index("ix_user_application_links_provider_key", table_name="user_application_links")
    op.drop_index("ix_user_application_links_user_type_created", table_name="user_application_links")
    op.drop_index("ix_user_application_links_user_application", table_name="user_application_links")
    op.drop_table("user_application_links")
    op.drop_index("ix_company_job_sources_company_active", table_name="company_job_sources")
    op.drop_index("ix_company_job_sources_status_active_mode_verified", table_name="company_job_sources")
    op.drop_index("ix_company_job_sources_domain_provider_active", table_name="company_job_sources")
    op.drop_index("uq_company_job_sources_identity", table_name="company_job_sources")
    op.drop_table("company_job_sources")

