"""add ai safety decisions

Revision ID: 047_add_ai_safety_decisions
Revises: 046_email_suggestion_decisions
Create Date: 2026-05-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "047_add_ai_safety_decisions"
down_revision = "046_email_suggestion_decisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_safety_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("model_call_id", sa.Uuid(), nullable=True),
        sa.Column("surface", sa.Text(), nullable=False),
        sa.Column("task_name", sa.Text(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("policy_decision", sa.Text(), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("prompt_injection_score", sa.Float(), nullable=True),
        sa.Column("input_data_classes", sa.JSON(), nullable=True),
        sa.Column("consent_snapshot", sa.JSON(), nullable=True),
        sa.Column("redaction_counts", sa.JSON(), nullable=True),
        sa.Column("reasons", sa.JSON(), nullable=True),
        sa.Column("token_estimate", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["model_call_id"], ["ai_model_calls.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_safety_decisions_user_created",
        "ai_safety_decisions",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_ai_safety_decisions_surface_task_created",
        "ai_safety_decisions",
        ["surface", "task_name", "created_at"],
    )
    op.create_index(
        "ix_ai_safety_decisions_decision_created",
        "ai_safety_decisions",
        ["policy_decision", "created_at"],
    )
    op.create_index(
        "ix_ai_safety_decisions_risk_created",
        "ai_safety_decisions",
        ["risk_score", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_safety_decisions_risk_created", table_name="ai_safety_decisions")
    op.drop_index("ix_ai_safety_decisions_decision_created", table_name="ai_safety_decisions")
    op.drop_index("ix_ai_safety_decisions_surface_task_created", table_name="ai_safety_decisions")
    op.drop_index("ix_ai_safety_decisions_user_created", table_name="ai_safety_decisions")
    op.drop_table("ai_safety_decisions")
