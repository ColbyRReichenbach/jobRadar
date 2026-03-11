"""Add resolved flag to email_events

Revision ID: 005
Revises: 004
Create Date: 2026-03-09
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("email_events", sa.Column("resolved", sa.Boolean(), nullable=True, server_default=sa.false()))


def downgrade():
    op.drop_column("email_events", "resolved")
