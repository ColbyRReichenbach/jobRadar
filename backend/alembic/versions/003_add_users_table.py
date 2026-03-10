"""Add users table and link gmail_tokens to users

Revision ID: 003
Revises: 002
Create Date: 2026-03-08
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("google_id", sa.String(255), unique=True, nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("picture", sa.Text(), nullable=True),
        sa.Column("gmail_connected", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.add_column("gmail_tokens", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_gmail_tokens_user_id",
        "gmail_tokens",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_gmail_tokens_user_id", "gmail_tokens", type_="foreignkey")
    op.drop_column("gmail_tokens", "user_id")
    op.drop_table("users")
