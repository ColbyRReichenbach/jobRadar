"""Add company_visits table.

Revision ID: 017
Revises: 016
"""

from alembic import op
import sqlalchemy as sa

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "company_visits",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("user_id", sa.Text, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("domain", sa.Text, nullable=False),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column("visit_count", sa.Integer, server_default="1"),
        sa.Column("first_visited_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_visited_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("company_visits")
