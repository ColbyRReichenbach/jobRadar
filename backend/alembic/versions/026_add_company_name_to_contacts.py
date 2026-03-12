"""Add company_name to contacts

Revision ID: 026
Revises: 025
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa


revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("company_name", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("contacts", "company_name")
