"""Allow manual contacts and add phone numbers.

Revision ID: 023
Revises: 022
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("contacts", sa.Column("phone_number", sa.Text(), nullable=True))
    op.alter_column("contacts", "application_id", existing_type=sa.Uuid(), nullable=True)


def downgrade():
    op.alter_column("contacts", "application_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_column("contacts", "phone_number")
