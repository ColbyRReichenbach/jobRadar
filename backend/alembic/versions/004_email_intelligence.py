"""Add email intelligence fields and email_feedback table

Revision ID: 004
Revises: 003
Create Date: 2026-03-08
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to email_events
    op.add_column("email_events", sa.Column("company_name", sa.Text(), nullable=True))
    op.add_column("email_events", sa.Column("company_logo_url", sa.Text(), nullable=True))
    op.add_column("email_events", sa.Column("sender_domain", sa.Text(), nullable=True))
    op.add_column("email_events", sa.Column("confidence", sa.Float(), nullable=True))

    # Create email_feedback table
    op.create_table(
        "email_feedback",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email_id", sa.Uuid(), sa.ForeignKey("email_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_job_related", sa.Boolean(), nullable=False),
        sa.Column("sender_domain", sa.Text(), nullable=True),
        sa.Column("subject_pattern", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade():
    op.drop_table("email_feedback")
    op.drop_column("email_events", "confidence")
    op.drop_column("email_events", "sender_domain")
    op.drop_column("email_events", "company_logo_url")
    op.drop_column("email_events", "company_name")
