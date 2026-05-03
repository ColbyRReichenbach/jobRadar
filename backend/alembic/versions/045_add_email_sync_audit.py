"""add email sync audit

Revision ID: 045_add_email_sync_audit
Revises: 044_add_ai_experiments
Create Date: 2026-05-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "045_add_email_sync_audit"
down_revision = "044_add_ai_experiments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_sync_audit",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sync_run_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("email_event_id", sa.Uuid(), nullable=True),
        sa.Column("gmail_message_id", sa.Text(), nullable=True),
        sa.Column("thread_id", sa.Text(), nullable=True),
        sa.Column("sender", sa.Text(), nullable=True),
        sa.Column("sender_email", sa.Text(), nullable=True),
        sa.Column("sender_domain", sa.Text(), nullable=True),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("classification", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["email_event_id"], ["email_events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_sync_audit_user_created", "email_sync_audit", ["user_id", "created_at"])
    op.create_index("ix_email_sync_audit_run", "email_sync_audit", ["sync_run_id", "created_at"])
    op.create_index("ix_email_sync_audit_user_decision", "email_sync_audit", ["user_id", "decision", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_email_sync_audit_user_decision", table_name="email_sync_audit")
    op.drop_index("ix_email_sync_audit_run", table_name="email_sync_audit")
    op.drop_index("ix_email_sync_audit_user_created", table_name="email_sync_audit")
    op.drop_table("email_sync_audit")
