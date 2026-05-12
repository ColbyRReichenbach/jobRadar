"""add retrieval foundation tables

Revision ID: 052_retrieval_foundation
Revises: 051_action_candidates_traces
Create Date: 2026-05-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "052_retrieval_foundation"
down_revision = "051_action_candidates_traces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_knowledge_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("search_document_id", sa.Uuid(), nullable=True),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("subtitle", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["search_document_id"], ["search_documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "source_type", "source_id", name="uq_user_knowledge_documents_user_source"),
    )
    op.create_index(
        "ix_user_knowledge_documents_search_document",
        "user_knowledge_documents",
        ["search_document_id"],
    )
    op.create_index("ix_user_knowledge_documents_source", "user_knowledge_documents", ["source_type", "source_id"])
    op.create_index(
        "ix_user_knowledge_documents_user_type_indexed",
        "user_knowledge_documents",
        ["user_id", "source_type", "indexed_at"],
    )

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["user_knowledge_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_document_index"),
    )
    op.create_index("ix_document_chunks_content_hash", "document_chunks", ["content_hash"])
    op.create_index("ix_document_chunks_user_document", "document_chunks", ["user_id", "document_id"])
    op.create_index("ix_document_chunks_user_source", "document_chunks", ["user_id", "source_type", "source_id"])

    op.create_table(
        "retrieval_traces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("surface", sa.Text(), nullable=False, server_default="retrieval"),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("normalized_query", sa.Text(), nullable=False),
        sa.Column("retriever_version", sa.Text(), nullable=False),
        sa.Column("source_types", sa.JSON(), nullable=True),
        sa.Column("filters_json", sa.JSON(), nullable=True),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("returned_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("selected_chunk_ids", sa.JSON(), nullable=True),
        sa.Column("scores_json", sa.JSON(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="ok"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_retrieval_traces_surface_created", "retrieval_traces", ["surface", "created_at"])
    op.create_index("ix_retrieval_traces_user_created", "retrieval_traces", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_retrieval_traces_user_created", table_name="retrieval_traces")
    op.drop_index("ix_retrieval_traces_surface_created", table_name="retrieval_traces")
    op.drop_table("retrieval_traces")

    op.drop_index("ix_document_chunks_user_source", table_name="document_chunks")
    op.drop_index("ix_document_chunks_user_document", table_name="document_chunks")
    op.drop_index("ix_document_chunks_content_hash", table_name="document_chunks")
    op.drop_table("document_chunks")

    op.drop_index("ix_user_knowledge_documents_user_type_indexed", table_name="user_knowledge_documents")
    op.drop_index("ix_user_knowledge_documents_source", table_name="user_knowledge_documents")
    op.drop_index("ix_user_knowledge_documents_search_document", table_name="user_knowledge_documents")
    op.drop_table("user_knowledge_documents")
