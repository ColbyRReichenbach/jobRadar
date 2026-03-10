"""Add per-user API key storage columns.

Revision ID: 021
Revises: 020
"""

from alembic import op
import sqlalchemy as sa

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("api_key_hash", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("api_key_last4", sa.String(length=4), nullable=True))
    op.add_column("users", sa.Column("api_key_created_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("api_key_last_used_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("uq_users_api_key_hash", "users", ["api_key_hash"])


def downgrade():
    op.drop_constraint("uq_users_api_key_hash", "users", type_="unique")
    op.drop_column("users", "api_key_last_used_at")
    op.drop_column("users", "api_key_created_at")
    op.drop_column("users", "api_key_last4")
    op.drop_column("users", "api_key_hash")
