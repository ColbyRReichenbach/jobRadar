"""production hardening constraints and admin role

Revision ID: 040
Revises: 039
Create Date: 2026-04-24
"""

from alembic import op
import sqlalchemy as sa


revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.drop_constraint("applications_job_url_key", "applications", type_="unique")
    op.create_unique_constraint(
        "uq_applications_user_job_url",
        "applications",
        ["user_id", "job_url"],
    )

    op.drop_constraint("email_events_gmail_message_id_key", "email_events", type_="unique")
    op.create_unique_constraint(
        "uq_email_events_user_gmail_message_id",
        "email_events",
        ["user_id", "gmail_message_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_email_events_user_gmail_message_id", "email_events", type_="unique")
    op.create_unique_constraint(
        "email_events_gmail_message_id_key",
        "email_events",
        ["gmail_message_id"],
    )

    op.drop_constraint("uq_applications_user_job_url", "applications", type_="unique")
    op.create_unique_constraint(
        "applications_job_url_key",
        "applications",
        ["job_url"],
    )

    op.drop_column("users", "is_admin")
