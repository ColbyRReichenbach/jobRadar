"""add email suggestion decisions

Revision ID: 046_email_suggestion_decisions
Revises: 045_add_email_sync_audit
Create Date: 2026-05-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "046_email_suggestion_decisions"
down_revision = "045_add_email_sync_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_suggestion_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("suggestion_key", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("email_ids", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "suggestion_key", name="uq_app_suggestion_decision_user_key"),
    )
    op.create_index(
        "ix_app_suggestion_decisions_user_created",
        "application_suggestion_decisions",
        ["user_id", "created_at"],
    )

    op.create_table(
        "interview_suggestion_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("email_event_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("interview_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["email_event_id"], ["email_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["interview_id"], ["interviews.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "email_event_id", name="uq_interview_suggestion_decision_user_email"),
    )
    op.create_index(
        "ix_interview_suggestion_decisions_user_created",
        "interview_suggestion_decisions",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_interview_suggestion_decisions_user_created", table_name="interview_suggestion_decisions")
    op.drop_table("interview_suggestion_decisions")
    op.drop_index("ix_app_suggestion_decisions_user_created", table_name="application_suggestion_decisions")
    op.drop_table("application_suggestion_decisions")
