"""Add notifications_started_at to users.

Revision ID: 028_add_notifications_started_at_to_users
Revises: 027_add_linkedin_to_user_profiles
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa


revision = "028_add_notifications_started_at_to_users"
down_revision = "027_add_linkedin_to_user_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("notifications_started_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "notifications_started_at")
