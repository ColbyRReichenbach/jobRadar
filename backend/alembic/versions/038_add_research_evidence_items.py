"""add research evidence items

Revision ID: 038
Revises: 037
Create Date: 2026-04-22
"""

from alembic import op
import sqlalchemy as sa


revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_evidence_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("report_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=True),
        sa.Column("source_item_id", sa.Uuid(), nullable=True),
        sa.Column("evidence_type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("domain", sa.Text(), nullable=True),
        sa.Column("company_name", sa.Text(), nullable=True),
        sa.Column("role_title", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("novelty_score", sa.Float(), nullable=True),
        sa.Column("structured_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["research_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["report_id"], ["research_reports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_item_id"], ["research_source_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column("research_feedback", sa.Column("report_id", sa.Uuid(), nullable=True))
    op.add_column("research_feedback", sa.Column("run_step_id", sa.Uuid(), nullable=True))
    op.add_column("research_feedback", sa.Column("feedback_scope", sa.Text(), server_default="signal", nullable=False))
    op.create_foreign_key(
        "fk_research_feedback_report_id",
        "research_feedback",
        "research_reports",
        ["report_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_research_feedback_run_step_id",
        "research_feedback",
        "research_run_steps",
        ["run_step_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_research_feedback_run_step_id", "research_feedback", type_="foreignkey")
    op.drop_constraint("fk_research_feedback_report_id", "research_feedback", type_="foreignkey")
    op.drop_column("research_feedback", "feedback_scope")
    op.drop_column("research_feedback", "run_step_id")
    op.drop_column("research_feedback", "report_id")
    op.drop_table("research_evidence_items")
