"""Add calendar connection flag to users.

Revision ID: 022
Revises: 021
"""

from alembic import op
import sqlalchemy as sa

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("calendar_connected", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("users", "calendar_connected", server_default=None)


def downgrade():
    op.drop_column("users", "calendar_connected")
