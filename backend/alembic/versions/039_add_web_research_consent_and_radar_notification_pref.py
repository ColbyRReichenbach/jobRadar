"""add web research consent and radar notification preference

Revision ID: 039
Revises: 038
Create Date: 2026-04-22
"""

from alembic import op
import sqlalchemy as sa


revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_preferences",
        sa.Column("radar_updates_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("notification_preferences", "radar_updates_enabled")
