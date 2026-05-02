"""add copilot tables

Revision ID: 043
Revises: 042
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa


revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "copilot_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_copilot_conversations_user_updated", "copilot_conversations", ["user_id", "updated_at"])

    op.create_table(
        "copilot_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=True),
        sa.Column("suggested_actions", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("model_call_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["copilot_conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_call_id"], ["ai_model_calls.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_copilot_messages_conversation_created", "copilot_messages", ["conversation_id", "created_at"])
    op.create_index("ix_copilot_messages_user_created", "copilot_messages", ["user_id", "created_at"])

    op.create_table(
        "copilot_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["copilot_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "message_id", name="uq_copilot_feedback_user_message"),
    )
    op.create_index("ix_copilot_feedback_user_created", "copilot_feedback", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_copilot_feedback_user_created", table_name="copilot_feedback")
    op.drop_table("copilot_feedback")
    op.drop_index("ix_copilot_messages_user_created", table_name="copilot_messages")
    op.drop_index("ix_copilot_messages_conversation_created", table_name="copilot_messages")
    op.drop_table("copilot_messages")
    op.drop_index("ix_copilot_conversations_user_updated", table_name="copilot_conversations")
    op.drop_table("copilot_conversations")
