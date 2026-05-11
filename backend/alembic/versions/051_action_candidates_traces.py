"""add action candidates and classifier traces

Revision ID: 051_action_candidates_traces
Revises: 050_expand_email_feedback_labels
Create Date: 2026-05-11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "051_action_candidates_traces"
down_revision = "050_expand_email_feedback_labels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "action_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("target_entity_type", sa.Text(), nullable=False),
        sa.Column("target_entity_id", sa.Text(), nullable=True),
        sa.Column("target_fingerprint", sa.Text(), nullable=False),
        sa.Column("dedupe_key", sa.Text(), nullable=False),
        sa.Column("duplicate_type", sa.Text(), nullable=False, server_default="none"),
        sa.Column("duplicate_matches_json", sa.JSON(), nullable=True),
        sa.Column("policy_decision", sa.Text(), nullable=False, server_default="propose"),
        sa.Column("status", sa.Text(), nullable=False, server_default="proposed"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "source_type",
            "source_id",
            "action_type",
            "dedupe_key",
            name="uq_action_candidates_source_action_dedupe",
        ),
    )
    op.create_index("ix_action_candidates_action_status", "action_candidates", ["action_type", "status", "created_at"])
    op.create_index("ix_action_candidates_user_dedupe", "action_candidates", ["user_id", "dedupe_key"])
    op.create_index("ix_action_candidates_user_status", "action_candidates", ["user_id", "status", "created_at"])

    op.create_table(
        "email_classification_traces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("email_event_id", sa.Uuid(), nullable=True),
        sa.Column("gmail_message_id", sa.Text(), nullable=True),
        sa.Column("classifier_mode", sa.Text(), nullable=False),
        sa.Column("classification", sa.Text(), nullable=True),
        sa.Column("classification_confidence", sa.Float(), nullable=True),
        sa.Column("route", sa.Text(), nullable=True),
        sa.Column("subtype", sa.Text(), nullable=True),
        sa.Column("route_confidence", sa.Float(), nullable=True),
        sa.Column("subtype_confidence", sa.Float(), nullable=True),
        sa.Column("decision_path", sa.Text(), nullable=True),
        sa.Column("threshold_version", sa.Text(), nullable=True),
        sa.Column("policy_version", sa.Text(), nullable=True),
        sa.Column("matched_signals_json", sa.JSON(), nullable=True),
        sa.Column("feature_summary_json", sa.JSON(), nullable=True),
        sa.Column("preflight_status", sa.Text(), nullable=True),
        sa.Column("candidate_source_url_count", sa.Integer(), nullable=True),
        sa.Column("model_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status_update_allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["email_event_id"], ["email_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_email_classification_traces_user_message_mode",
        "email_classification_traces",
        ["user_id", "gmail_message_id", "classifier_mode"],
        unique=True,
    )
    op.create_index(
        "ix_email_classification_traces_email_event",
        "email_classification_traces",
        ["email_event_id", "created_at"],
    )
    op.create_index(
        "ix_email_classification_traces_route_subtype",
        "email_classification_traces",
        ["route", "subtype", "created_at"],
    )
    op.create_index(
        "ix_email_classification_traces_user_created",
        "email_classification_traces",
        ["user_id", "created_at"],
    )

    op.add_column("alerts", sa.Column("action_candidate_id", sa.Uuid(), nullable=True))
    op.add_column("alerts", sa.Column("dedupe_key", sa.Text(), nullable=True))
    op.add_column("alerts", sa.Column("suppression_status", sa.Text(), nullable=False, server_default="active"))
    op.add_column("alerts", sa.Column("duplicate_reason", sa.Text(), nullable=True))
    op.add_column("alerts", sa.Column("duplicate_matches_json", sa.JSON(), nullable=True))
    op.create_foreign_key("fk_alerts_action_candidate", "alerts", "action_candidates", ["action_candidate_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_alerts_user_dedupe", "alerts", ["user_id", "dedupe_key"])
    op.create_index("ix_alerts_action_candidate", "alerts", ["action_candidate_id"])
    op.create_index(
        "ux_alerts_user_dedupe_status",
        "alerts",
        ["user_id", "dedupe_key", "suppression_status"],
        unique=True,
    )

    op.add_column("recommended_actions", sa.Column("action_candidate_id", sa.Uuid(), nullable=True))
    op.add_column("recommended_actions", sa.Column("dedupe_key", sa.Text(), nullable=True))
    op.add_column("recommended_actions", sa.Column("duplicate_reason", sa.Text(), nullable=True))
    op.add_column("recommended_actions", sa.Column("duplicate_matches_json", sa.JSON(), nullable=True))
    op.create_foreign_key(
        "fk_recommended_actions_action_candidate",
        "recommended_actions",
        "action_candidates",
        ["action_candidate_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_recommended_actions_user_dedupe", "recommended_actions", ["user_id", "dedupe_key"])
    op.create_index("ix_recommended_actions_action_candidate", "recommended_actions", ["action_candidate_id"])


def downgrade() -> None:
    op.drop_index("ix_recommended_actions_action_candidate", table_name="recommended_actions")
    op.drop_index("ix_recommended_actions_user_dedupe", table_name="recommended_actions")
    op.drop_constraint("fk_recommended_actions_action_candidate", "recommended_actions", type_="foreignkey")
    op.drop_column("recommended_actions", "duplicate_matches_json")
    op.drop_column("recommended_actions", "duplicate_reason")
    op.drop_column("recommended_actions", "dedupe_key")
    op.drop_column("recommended_actions", "action_candidate_id")

    op.drop_index("ix_alerts_action_candidate", table_name="alerts")
    op.drop_index("ix_alerts_user_dedupe", table_name="alerts")
    op.drop_index("ux_alerts_user_dedupe_status", table_name="alerts")
    op.drop_constraint("fk_alerts_action_candidate", "alerts", type_="foreignkey")
    op.drop_column("alerts", "duplicate_matches_json")
    op.drop_column("alerts", "duplicate_reason")
    op.drop_column("alerts", "suppression_status")
    op.drop_column("alerts", "dedupe_key")
    op.drop_column("alerts", "action_candidate_id")

    op.drop_index("ix_email_classification_traces_user_created", table_name="email_classification_traces")
    op.drop_index("ix_email_classification_traces_route_subtype", table_name="email_classification_traces")
    op.drop_index("ix_email_classification_traces_email_event", table_name="email_classification_traces")
    op.drop_index("ux_email_classification_traces_user_message_mode", table_name="email_classification_traces")
    op.drop_table("email_classification_traces")

    op.drop_index("ix_action_candidates_user_status", table_name="action_candidates")
    op.drop_index("ix_action_candidates_user_dedupe", table_name="action_candidates")
    op.drop_index("ix_action_candidates_action_status", table_name="action_candidates")
    op.drop_table("action_candidates")
