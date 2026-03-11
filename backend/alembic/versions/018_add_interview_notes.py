"""Add interview_notes table.

Revision ID: 018
Revises: 017
"""

from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "interview_notes",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("interview_id", sa.Uuid(), sa.ForeignKey("interviews.id", ondelete="CASCADE"), nullable=True),
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=True),
        sa.Column("questions_asked", sa.Text, nullable=True),
        sa.Column("went_well", sa.Text, nullable=True),
        sa.Column("to_improve", sa.Text, nullable=True),
        sa.Column("overall_feeling", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("interview_notes")
