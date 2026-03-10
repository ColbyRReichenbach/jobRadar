"""Add tech_stack JSON to applications and company_tech_profiles table

Revision ID: 008
Revises: 007
Create Date: 2026-03-09
"""
from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("applications", sa.Column("tech_stack", sa.JSON(), nullable=True))
    op.create_table(
        "company_tech_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("tech_name", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("mention_count", sa.Integer(), server_default=sa.text("1"), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("company_id", "tech_name", name="uq_company_tech"),
    )


def downgrade():
    op.drop_table("company_tech_profiles")
    op.drop_column("applications", "tech_stack")
