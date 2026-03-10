"""create all tables

Revision ID: 001
Revises:
Create Date: 2026-03-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("company", sa.Text(), nullable=False),
        sa.Column("role_title", sa.Text(), nullable=False),
        sa.Column("department", sa.Text(), nullable=True),
        sa.Column("job_url", sa.Text(), nullable=True, unique=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("description_text", sa.Text(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("status", sa.Text(), server_default=sa.text("'applied'")),
        sa.Column("status_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ats_confirmed", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("last_email_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("follow_up_due", sa.Boolean(), server_default=sa.text("false")),
    )

    op.create_table(
        "contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("applications.id", ondelete="CASCADE")),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("linkedin_url", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("reached_out", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("reached_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_received", sa.Boolean(), server_default=sa.text("false")),
    )

    op.create_table(
        "email_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("applications.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contacts.id"), nullable=True),
        sa.Column("gmail_message_id", sa.Text(), unique=True, nullable=True),
        sa.Column("sender", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pipeline", sa.Text(), nullable=True),
        sa.Column("classification", sa.Text(), nullable=True),
        sa.Column("color_code", sa.Text(), nullable=True),
        sa.Column("urgency", sa.Text(), nullable=True),
        sa.Column("action_needed", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("action_url", sa.Text(), nullable=True),
        sa.Column("is_human", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("key_sentence", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("collapsed", sa.Boolean(), server_default=sa.text("false")),
    )

    op.create_table(
        "job_listings",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("company", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), unique=True, nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("description_snippet", sa.Text(), nullable=True),
        sa.Column("saved_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("applied", sa.Boolean(), server_default=sa.text("false")),
    )

    op.create_table(
        "scraper_errors",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("platform", sa.Text(), nullable=True),
        sa.Column("error_type", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("html_snippet", sa.Text(), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("resolved", sa.Boolean(), server_default=sa.text("false")),
    )

    op.create_table(
        "gmail_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("gmail_tokens")
    op.drop_table("scraper_errors")
    op.drop_table("job_listings")
    op.drop_table("email_events")
    op.drop_table("contacts")
    op.drop_table("applications")
