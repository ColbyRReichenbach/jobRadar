"""add ai experiments

Revision ID: 044_add_ai_experiments
Revises: 043_add_copilot_tables
Create Date: 2026-05-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "044_add_ai_experiments"
down_revision = "043_add_copilot_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_experiments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("experiment_key", sa.Text(), nullable=False),
        sa.Column("surface", sa.Text(), nullable=False),
        sa.Column("task_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("control_variant", sa.Text(), nullable=True),
        sa.Column("candidate_variants", sa.JSON(), nullable=True),
        sa.Column("traffic_allocation", sa.JSON(), nullable=True),
        sa.Column("guardrail_thresholds", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("experiment_key", name="uq_ai_experiments_key"),
    )
    op.create_index("ix_ai_experiments_surface_task_status", "ai_experiments", ["surface", "task_name", "status"])

    op.create_table(
        "ai_experiment_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("variant", sa.Text(), nullable=False),
        sa.Column("assigned_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["experiment_id"], ["ai_experiments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("experiment_id", "user_id", name="uq_ai_experiment_assignment_user"),
    )
    op.create_index("ix_ai_experiment_assignments_variant", "ai_experiment_assignments", ["experiment_id", "variant"])

    op.create_table(
        "ai_feedback_reward_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("feedback_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("model_call_id", sa.Uuid(), nullable=True),
        sa.Column("experiment_key", sa.Text(), nullable=True),
        sa.Column("variant", sa.Text(), nullable=True),
        sa.Column("rating", sa.Text(), nullable=False),
        sa.Column("reward_score", sa.Float(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["feedback_id"], ["copilot_feedback.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["copilot_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_call_id"], ["ai_model_calls.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feedback_id", name="uq_ai_feedback_reward_feedback"),
    )
    op.create_index("ix_ai_feedback_reward_model_call", "ai_feedback_reward_events", ["model_call_id", "created_at"])
    op.create_index("ix_ai_feedback_reward_variant", "ai_feedback_reward_events", ["experiment_key", "variant", "created_at"])

    op.create_table(
        "ai_shadow_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("production_model_call_id", sa.Uuid(), nullable=True),
        sa.Column("candidate_variant", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("visible_to_user", sa.Boolean(), nullable=True),
        sa.Column("output_metadata", sa.JSON(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cost_estimate_cents", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["experiment_id"], ["ai_experiments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["production_model_call_id"], ["ai_model_calls.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_shadow_runs_experiment_created", "ai_shadow_runs", ["experiment_id", "created_at"])
    op.create_index("ix_ai_shadow_runs_status_created", "ai_shadow_runs", ["status", "created_at"])

    op.create_table(
        "ai_promotion_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("report_json", sa.JSON(), nullable=False),
        sa.Column("generated_after_calls", sa.Integer(), nullable=True),
        sa.Column("generated_after_feedback", sa.Integer(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["experiment_id"], ["ai_experiments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_promotion_reports_experiment_created", "ai_promotion_reports", ["experiment_id", "created_at"])
    op.create_index("ix_ai_promotion_reports_status_created", "ai_promotion_reports", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_promotion_reports_status_created", table_name="ai_promotion_reports")
    op.drop_index("ix_ai_promotion_reports_experiment_created", table_name="ai_promotion_reports")
    op.drop_table("ai_promotion_reports")
    op.drop_index("ix_ai_shadow_runs_status_created", table_name="ai_shadow_runs")
    op.drop_index("ix_ai_shadow_runs_experiment_created", table_name="ai_shadow_runs")
    op.drop_table("ai_shadow_runs")
    op.drop_index("ix_ai_feedback_reward_variant", table_name="ai_feedback_reward_events")
    op.drop_index("ix_ai_feedback_reward_model_call", table_name="ai_feedback_reward_events")
    op.drop_table("ai_feedback_reward_events")
    op.drop_index("ix_ai_experiment_assignments_variant", table_name="ai_experiment_assignments")
    op.drop_table("ai_experiment_assignments")
    op.drop_index("ix_ai_experiments_surface_task_status", table_name="ai_experiments")
    op.drop_table("ai_experiments")
