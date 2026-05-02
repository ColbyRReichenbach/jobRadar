"""add ai model ledger tables

Revision ID: 041
Revises: 040
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa


revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_model_pricing",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("input_token_cents_per_1m", sa.Float(), nullable=False),
        sa.Column("output_token_cents_per_1m", sa.Float(), nullable=False),
        sa.Column("cached_input_token_cents_per_1m", sa.Float(), nullable=True),
        sa.Column("reasoning_token_cents_per_1m", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "model", "effective_at", name="uq_ai_model_pricing_provider_model_effective"),
    )

    op.create_table(
        "ai_model_cards",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_name", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("intended_use", sa.Text(), nullable=False),
        sa.Column("prohibited_use", sa.Text(), nullable=True),
        sa.Column("limitations", sa.Text(), nullable=True),
        sa.Column("eval_dataset_version", sa.Text(), nullable=True),
        sa.Column("primary_metrics", sa.JSON(), nullable=True),
        sa.Column("guardrail_metrics", sa.JSON(), nullable=True),
        sa.Column("approval_status", sa.Text(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rollback_plan", sa.Text(), nullable=True),
        sa.Column("review_cadence", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_name", "model", "prompt_version", name="uq_ai_model_card_task_model_prompt"),
    )

    op.create_table(
        "ai_model_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("surface", sa.Text(), nullable=False),
        sa.Column("task_name", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("variant", sa.Text(), nullable=True),
        sa.Column("release_version", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("validation_result", sa.Text(), nullable=True),
        sa.Column("fallback_used", sa.Boolean(), nullable=False),
        sa.Column("fallback_reason", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("context_tokens", sa.Integer(), nullable=True),
        sa.Column("tool_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=True),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("billable_input_tokens", sa.Integer(), nullable=True),
        sa.Column("billable_output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_estimate_cents", sa.Integer(), nullable=True),
        sa.Column("cost_breakdown", sa.JSON(), nullable=True),
        sa.Column("request_metadata", sa.JSON(), nullable=True),
        sa.Column("response_metadata", sa.JSON(), nullable=True),
        sa.Column("error_class", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("model_card_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["model_card_id"], ["ai_model_cards.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_model_calls_user_created", "ai_model_calls", ["user_id", "created_at"])
    op.create_index("ix_ai_model_calls_surface_task_created", "ai_model_calls", ["surface", "task_name", "created_at"])
    op.create_index("ix_ai_model_calls_model_prompt_created", "ai_model_calls", ["model", "prompt_version", "created_at"])
    op.create_index("ix_ai_model_calls_variant_created", "ai_model_calls", ["variant", "created_at"])
    op.create_index("ix_ai_model_calls_status_created", "ai_model_calls", ["status", "created_at"])

    op.create_table(
        "ai_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("model_call_id", sa.Uuid(), nullable=True),
        sa.Column("artifact_type", sa.Text(), nullable=False),
        sa.Column("artifact_ref_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["model_call_id"], ["ai_model_calls.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_artifacts_user_created", "ai_artifacts", ["user_id", "created_at"])
    op.create_index("ix_ai_artifacts_call_created", "ai_artifacts", ["model_call_id", "created_at"])
    op.create_index("ix_ai_artifacts_type_ref", "ai_artifacts", ["artifact_type", "artifact_ref_id"])

    op.create_table(
        "ai_admin_access_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("admin_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["admin_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_admin_access_logs_admin_created", "ai_admin_access_logs", ["admin_user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_admin_access_logs_admin_created", table_name="ai_admin_access_logs")
    op.drop_table("ai_admin_access_logs")
    op.drop_index("ix_ai_artifacts_type_ref", table_name="ai_artifacts")
    op.drop_index("ix_ai_artifacts_call_created", table_name="ai_artifacts")
    op.drop_index("ix_ai_artifacts_user_created", table_name="ai_artifacts")
    op.drop_table("ai_artifacts")
    op.drop_index("ix_ai_model_calls_status_created", table_name="ai_model_calls")
    op.drop_index("ix_ai_model_calls_variant_created", table_name="ai_model_calls")
    op.drop_index("ix_ai_model_calls_model_prompt_created", table_name="ai_model_calls")
    op.drop_index("ix_ai_model_calls_surface_task_created", table_name="ai_model_calls")
    op.drop_index("ix_ai_model_calls_user_created", table_name="ai_model_calls")
    op.drop_table("ai_model_calls")
    op.drop_table("ai_model_cards")
    op.drop_table("ai_model_pricing")
