"""Add contact distinct decisions

Revision ID: 030
Revises: 029
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contact_distinct_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name_key", sa.Text(), nullable=True),
        sa.Column("email_a", sa.Text(), nullable=False),
        sa.Column("email_b", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "email_a", "email_b", name="uq_contact_distinct_user_pair"),
    )


def downgrade() -> None:
    op.drop_table("contact_distinct_decisions")
