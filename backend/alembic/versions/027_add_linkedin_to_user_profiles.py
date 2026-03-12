"""Add linkedin_url to user_profiles.

Revision ID: 027_add_linkedin_to_user_profiles
Revises: 026_add_company_name_to_contacts
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa


revision = "027_add_linkedin_to_user_profiles"
down_revision = "026_add_company_name_to_contacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("linkedin_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_profiles", "linkedin_url")
