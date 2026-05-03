"""add ai safety review fields

Revision ID: 048_add_ai_safety_review
Revises: 047_add_ai_safety_decisions
Create Date: 2026-05-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "048_add_ai_safety_review"
down_revision = "047_add_ai_safety_decisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_safety_decisions",
        sa.Column("review_status", sa.Text(), nullable=False, server_default="unreviewed"),
    )
    op.add_column("ai_safety_decisions", sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True))
    op.add_column("ai_safety_decisions", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ai_safety_decisions", sa.Column("review_notes", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_ai_safety_decisions_reviewed_by_user",
        "ai_safety_decisions",
        "users",
        ["reviewed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_ai_safety_decisions_review_status_created",
        "ai_safety_decisions",
        ["review_status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_safety_decisions_review_status_created", table_name="ai_safety_decisions")
    op.drop_constraint("fk_ai_safety_decisions_reviewed_by_user", "ai_safety_decisions", type_="foreignkey")
    op.drop_column("ai_safety_decisions", "review_notes")
    op.drop_column("ai_safety_decisions", "reviewed_at")
    op.drop_column("ai_safety_decisions", "reviewed_by_user_id")
    op.drop_column("ai_safety_decisions", "review_status")
