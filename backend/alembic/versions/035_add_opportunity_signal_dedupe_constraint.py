"""Add unique constraint for opportunity signal dedupe

Revision ID: 035
Revises: 034
Create Date: 2026-04-22
"""

from alembic import op
import sqlalchemy as sa


revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_opportunity_signal_user_source_event",
        "opportunity_signals",
        ["user_id", "source_item_id", "event_type"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_opportunity_signal_user_source_event", "opportunity_signals", type_="unique")
