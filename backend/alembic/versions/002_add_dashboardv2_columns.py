"""add dashboardv2 columns

Revision ID: 002
Revises: 001
Create Date: 2026-03-08
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Application: new columns
    op.add_column("applications", sa.Column("salary", sa.Text(), nullable=True))
    op.add_column("applications", sa.Column("logo_url", sa.Text(), nullable=True))
    op.add_column("applications", sa.Column("location", sa.Text(), nullable=True))

    # EmailEvent: new columns for full email content + threading
    op.add_column("email_events", sa.Column("thread_id", sa.Text(), nullable=True))
    op.add_column("email_events", sa.Column("sender_email", sa.Text(), nullable=True))
    op.add_column("email_events", sa.Column("subject", sa.Text(), nullable=True))
    op.add_column("email_events", sa.Column("body", sa.Text(), nullable=True))
    op.add_column("email_events", sa.Column("snippet", sa.Text(), nullable=True))
    op.add_column("email_events", sa.Column("is_from_user", sa.Boolean(), server_default=sa.text("false")))
    op.add_column("email_events", sa.Column("email_type", sa.Text(), nullable=True))
    op.add_column("email_events", sa.Column("read", sa.Boolean(), server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("email_events", "read")
    op.drop_column("email_events", "email_type")
    op.drop_column("email_events", "is_from_user")
    op.drop_column("email_events", "snippet")
    op.drop_column("email_events", "body")
    op.drop_column("email_events", "subject")
    op.drop_column("email_events", "sender_email")
    op.drop_column("email_events", "thread_id")
    op.drop_column("applications", "location")
    op.drop_column("applications", "logo_url")
    op.drop_column("applications", "salary")
