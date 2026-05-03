"""add search documents

Revision ID: 042
Revises: 041
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa


revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("subtitle", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("keywords", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "source_type", "source_id", name="uq_search_documents_user_source"),
    )
    op.create_index(
        "ix_search_documents_user_type_indexed",
        "search_documents",
        ["user_id", "source_type", "indexed_at"],
    )
    op.create_index("ix_search_documents_user_indexed", "search_documents", ["user_id", "indexed_at"])
    op.create_index("ix_search_documents_source", "search_documents", ["source_type", "source_id"])


def downgrade() -> None:
    op.drop_index("ix_search_documents_source", table_name="search_documents")
    op.drop_index("ix_search_documents_user_indexed", table_name="search_documents")
    op.drop_index("ix_search_documents_user_type_indexed", table_name="search_documents")
    op.drop_table("search_documents")
