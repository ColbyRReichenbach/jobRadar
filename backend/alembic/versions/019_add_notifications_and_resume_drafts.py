"""Add notification_preferences and resume_drafts tables.

Revision ID: 019
Revises: 018
"""

from alembic import op
import sqlalchemy as sa

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("user_id", sa.Text, sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True),
        sa.Column("sms_enabled", sa.Boolean, server_default="false"),
        sa.Column("sms_phone", sa.Text, nullable=True),
        sa.Column("weekly_digest_enabled", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "resume_drafts",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("user_id", sa.Text, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("application_id", sa.Text, sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=True),
        sa.Column("original_text", sa.Text, nullable=True),
        sa.Column("tailored_text", sa.Text, nullable=True),
        sa.Column("changes_summary", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("resume_drafts")
    op.drop_table("notification_preferences")
