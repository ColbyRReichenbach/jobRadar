"""expand research profiles for research mode

Revision ID: 036
Revises: 035
Create Date: 2026-04-22
"""

from alembic import op
import sqlalchemy as sa


revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("research_profiles", sa.Column("mode", sa.Text(), server_default="internal", nullable=False))
    op.add_column("research_profiles", sa.Column("depth", sa.Text(), server_default="standard", nullable=False))
    op.add_column("research_profiles", sa.Column("target_locations", sa.JSON(), nullable=True))
    op.add_column("research_profiles", sa.Column("remote_types", sa.JSON(), nullable=True))
    op.add_column("research_profiles", sa.Column("seniority_levels", sa.JSON(), nullable=True))
    op.add_column("research_profiles", sa.Column("research_source_scopes", sa.JSON(), nullable=True))
    op.add_column("research_profiles", sa.Column("use_profile_context", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column("research_profiles", sa.Column("include_public_web_research", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("research_profiles", sa.Column("report_prompt_notes", sa.Text(), nullable=True))
    op.add_column("research_profiles", sa.Column("max_search_queries", sa.Integer(), server_default="8", nullable=False))
    op.add_column("research_profiles", sa.Column("max_sources_per_run", sa.Integer(), server_default="20", nullable=False))
    op.add_column("research_profiles", sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("research_profiles", sa.Column("last_successful_run_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("research_profiles", "last_successful_run_at")
    op.drop_column("research_profiles", "next_run_at")
    op.drop_column("research_profiles", "max_sources_per_run")
    op.drop_column("research_profiles", "max_search_queries")
    op.drop_column("research_profiles", "report_prompt_notes")
    op.drop_column("research_profiles", "include_public_web_research")
    op.drop_column("research_profiles", "use_profile_context")
    op.drop_column("research_profiles", "research_source_scopes")
    op.drop_column("research_profiles", "seniority_levels")
    op.drop_column("research_profiles", "remote_types")
    op.drop_column("research_profiles", "target_locations")
    op.drop_column("research_profiles", "depth")
    op.drop_column("research_profiles", "mode")
