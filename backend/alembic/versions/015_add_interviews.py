"""Add interviews table.

Revision ID: 015
Revises: 014
"""

from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "interviews",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("application_id", sa.Text, sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=True),
        sa.Column("user_id", sa.Text, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("interview_type", sa.Text, server_default="phone"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_minutes", sa.Integer, nullable=True),
        sa.Column("interviewer_name", sa.Text, nullable=True),
        sa.Column("interviewer_email", sa.Text, nullable=True),
        sa.Column("location_or_link", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("outcome", sa.Text, server_default="pending"),
        sa.Column("calendar_event_id", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("interviews")
