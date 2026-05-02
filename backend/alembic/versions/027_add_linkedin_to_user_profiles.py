"""Add linkedin_url to user_profiles.

Revision ID: 027
Revises: 026
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa


revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("linkedin_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_profiles", "linkedin_url")
