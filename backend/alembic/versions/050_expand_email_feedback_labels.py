"""expand email feedback labels

Revision ID: 050_expand_email_feedback_labels
Revises: 049_add_source_intelligence
Create Date: 2026-05-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "050_expand_email_feedback_labels"
down_revision = "049_add_source_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("email_feedback", sa.Column("predicted_route", sa.Text(), nullable=True))
    op.add_column("email_feedback", sa.Column("predicted_subtype", sa.Text(), nullable=True))
    op.add_column("email_feedback", sa.Column("predicted_classification", sa.Text(), nullable=True))
    op.add_column("email_feedback", sa.Column("feedback_action", sa.Text(), nullable=True))
    op.add_column("email_feedback", sa.Column("corrected_route", sa.Text(), nullable=True))
    op.add_column("email_feedback", sa.Column("corrected_subtype", sa.Text(), nullable=True))
    op.add_column("email_feedback", sa.Column("feedback_label", sa.Text(), nullable=True))
    op.add_column("email_feedback", sa.Column("source_surface", sa.Text(), nullable=True))
    op.add_column("email_feedback", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("email_feedback", "notes")
    op.drop_column("email_feedback", "source_surface")
    op.drop_column("email_feedback", "feedback_label")
    op.drop_column("email_feedback", "corrected_subtype")
    op.drop_column("email_feedback", "corrected_route")
    op.drop_column("email_feedback", "feedback_action")
    op.drop_column("email_feedback", "predicted_classification")
    op.drop_column("email_feedback", "predicted_subtype")
    op.drop_column("email_feedback", "predicted_route")
