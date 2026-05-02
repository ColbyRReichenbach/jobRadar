"""create extraction_reports table

Revision ID: 031
Revises: 030
Create Date: 2026-03-18
"""
from alembic import op
import sqlalchemy as sa

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "extraction_reports",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("report_type", sa.Text, nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("domain", sa.Text, nullable=True),
        sa.Column("platform_detected", sa.Text, nullable=True),
        sa.Column("extraction_method", sa.Text, nullable=True),
        sa.Column("extracted_data", sa.JSON, nullable=True),
        sa.Column("corrected_data", sa.JSON, nullable=True),
        sa.Column("fields_flagged", sa.JSON, nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("extension_version", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("resolved", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_extraction_reports_report_type", "extraction_reports", ["report_type"])
    op.create_index("ix_extraction_reports_platform", "extraction_reports", ["platform_detected"])
    op.create_index("ix_extraction_reports_domain", "extraction_reports", ["domain"])


def downgrade() -> None:
    op.drop_index("ix_extraction_reports_domain")
    op.drop_index("ix_extraction_reports_platform")
    op.drop_index("ix_extraction_reports_report_type")
    op.drop_table("extraction_reports")
