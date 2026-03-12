"""Add local hidden flag to email events.

Revision ID: 024
Revises: 023
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "email_events",
        sa.Column("hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("email_events", "hidden")
