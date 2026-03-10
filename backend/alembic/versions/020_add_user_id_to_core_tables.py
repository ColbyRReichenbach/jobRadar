"""Add user_id to applications, email_events, and contacts for per-user data isolation.

Revision ID: 020
Revises: 019
"""

from alembic import op
import sqlalchemy as sa

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("applications", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_applications_user_id", "applications", "users", ["user_id"], ["id"], ondelete="CASCADE")

    op.add_column("email_events", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_email_events_user_id", "email_events", "users", ["user_id"], ["id"], ondelete="CASCADE")

    op.add_column("contacts", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_contacts_user_id", "contacts", "users", ["user_id"], ["id"], ondelete="CASCADE")


def downgrade():
    op.drop_constraint("fk_contacts_user_id", "contacts", type_="foreignkey")
    op.drop_column("contacts", "user_id")

    op.drop_constraint("fk_email_events_user_id", "email_events", type_="foreignkey")
    op.drop_column("email_events", "user_id")

    op.drop_constraint("fk_applications_user_id", "applications", type_="foreignkey")
    op.drop_column("applications", "user_id")
