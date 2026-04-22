"""add research reports and run steps

Revision ID: 037
Revises: 036
Create Date: 2026-04-22
"""

from alembic import op
import sqlalchemy as sa


revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("research_runs", sa.Column("run_type", sa.Text(), server_default="manual", nullable=False))
    op.add_column("research_runs", sa.Column("mode", sa.Text(), nullable=True))
    op.add_column("research_runs", sa.Column("trigger_reason", sa.Text(), nullable=True))
    op.add_column("research_runs", sa.Column("orchestrator_version", sa.Text(), nullable=True))
    op.add_column("research_runs", sa.Column("graph_thread_id", sa.Text(), nullable=True))
    op.add_column("research_runs", sa.Column("current_step", sa.Text(), nullable=True))
    op.add_column("research_runs", sa.Column("report_id", sa.Uuid(), nullable=True))
    op.add_column("research_runs", sa.Column("status_detail", sa.JSON(), nullable=True))
    op.add_column("research_runs", sa.Column("tokens_in", sa.Integer(), nullable=True))
    op.add_column("research_runs", sa.Column("tokens_out", sa.Integer(), nullable=True))
    op.add_column("research_runs", sa.Column("llm_call_count", sa.Integer(), nullable=True))

    op.create_table(
        "research_run_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=True),
        sa.Column("step_name", sa.Text(), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("tool_name", sa.Text(), nullable=True),
        sa.Column("input_json", sa.JSON(), nullable=True),
        sa.Column("output_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("cost_estimate_cents", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["research_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "research_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("report_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary_markdown", sa.Text(), nullable=True),
        sa.Column("structured_json", sa.JSON(), nullable=True),
        sa.Column("diff_summary", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("overall_confidence", sa.Float(), nullable=True),
        sa.Column("finding_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("new_findings_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("changed_findings_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["research_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "research_report_sections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("section_key", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("markdown", sa.Text(), nullable=True),
        sa.Column("structured_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["report_id"], ["research_reports.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("research_report_sections")
    op.drop_table("research_reports")
    op.drop_table("research_run_steps")
    op.drop_column("research_runs", "llm_call_count")
    op.drop_column("research_runs", "tokens_out")
    op.drop_column("research_runs", "tokens_in")
    op.drop_column("research_runs", "status_detail")
    op.drop_column("research_runs", "report_id")
    op.drop_column("research_runs", "current_step")
    op.drop_column("research_runs", "graph_thread_id")
    op.drop_column("research_runs", "orchestrator_version")
    op.drop_column("research_runs", "trigger_reason")
    op.drop_column("research_runs", "mode")
    op.drop_column("research_runs", "run_type")
