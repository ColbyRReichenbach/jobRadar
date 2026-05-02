"""Sprint 9: Add warm_connections table.

Revision ID: 013
Revises: 012
"""

from alembic import op
import sqlalchemy as sa


revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "warm_connections",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("company_domain", sa.Text(), nullable=False),
        sa.Column("contact_email", sa.Text(), nullable=False),
        sa.Column("contact_name", sa.Text(), nullable=True),
        sa.Column("email_count", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("last_interaction_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_warm_connections_user_domain", "warm_connections", ["user_id", "company_domain"])


def downgrade() -> None:
    op.drop_index("ix_warm_connections_user_domain", table_name="warm_connections")
    op.drop_table("warm_connections")
