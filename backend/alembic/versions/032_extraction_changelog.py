"""create extraction_changelog table + add extractor_version to extraction_reports

Revision ID: 032
Revises: 031
Create Date: 2026-03-18
"""
from alembic import op
import sqlalchemy as sa

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Changelog table
    op.create_table(
        "extraction_changelog",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("version", sa.Text, nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("platforms_affected", sa.JSON, nullable=True),
        sa.Column("fields_affected", sa.JSON, nullable=True),
        sa.Column("change_type", sa.Text, server_default="extraction", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # Add extractor_version column to extraction_reports
    op.add_column("extraction_reports", sa.Column("extractor_version", sa.Text, nullable=True))
    op.create_index("ix_extraction_reports_extractor_version", "extraction_reports", ["extractor_version"])


def downgrade() -> None:
    op.drop_index("ix_extraction_reports_extractor_version")
    op.drop_column("extraction_reports", "extractor_version")
    op.drop_table("extraction_changelog")
