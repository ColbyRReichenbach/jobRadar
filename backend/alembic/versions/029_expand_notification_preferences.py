"""Expand notification preferences.

Revision ID: 029
Revises: 028
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa


revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_preferences",
        sa.Column("browser_notifications_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "notification_preferences",
        sa.Column("inbox_updates_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "notification_preferences",
        sa.Column("conversations_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "notification_preferences",
        sa.Column("network_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "notification_preferences",
        sa.Column("interviews_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "notification_preferences",
        sa.Column("followups_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "notification_preferences",
        sa.Column("listings_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "notification_preferences",
        sa.Column("quiet_hours_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("notification_preferences", sa.Column("quiet_hours_start", sa.Integer(), nullable=True))
    op.add_column("notification_preferences", sa.Column("quiet_hours_end", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("notification_preferences", "quiet_hours_end")
    op.drop_column("notification_preferences", "quiet_hours_start")
    op.drop_column("notification_preferences", "quiet_hours_enabled")
    op.drop_column("notification_preferences", "listings_enabled")
    op.drop_column("notification_preferences", "followups_enabled")
    op.drop_column("notification_preferences", "interviews_enabled")
    op.drop_column("notification_preferences", "network_enabled")
    op.drop_column("notification_preferences", "conversations_enabled")
    op.drop_column("notification_preferences", "inbox_updates_enabled")
    op.drop_column("notification_preferences", "browser_notifications_enabled")
