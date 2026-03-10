"""Add companies table and company_id FKs

Revision ID: 006
Revises: 005
Create Date: 2026-03-09
"""
from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("logo_url", sa.Text(), nullable=True),
        sa.Column("industry", sa.Text(), nullable=True),
        sa.Column("size", sa.Text(), nullable=True),
        sa.Column("ats_platform", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("domain"),
    )
    op.add_column("applications", sa.Column("company_id", sa.Uuid(), nullable=True))
    op.add_column("contacts", sa.Column("company_id", sa.Uuid(), nullable=True))
    op.add_column("email_events", sa.Column("company_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_app_company", "applications", "companies", ["company_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_contact_company", "contacts", "companies", ["company_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_email_company", "email_events", "companies", ["company_id"], ["id"], ondelete="SET NULL")


def downgrade():
    op.drop_constraint("fk_email_company", "email_events", type_="foreignkey")
    op.drop_constraint("fk_contact_company", "contacts", type_="foreignkey")
    op.drop_constraint("fk_app_company", "applications", type_="foreignkey")
    op.drop_column("email_events", "company_id")
    op.drop_column("contacts", "company_id")
    op.drop_column("applications", "company_id")
    op.drop_table("companies")
