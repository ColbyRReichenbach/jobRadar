"""Sprint 11: Add alerts table and first_response_days to applications."""

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column("applications", sa.Column("first_response_days", sa.Integer, nullable=True))
    op.create_table(
        "alerts",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("user_id", sa.Text, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("alert_type", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=True),
        sa.Column("action_url", sa.Text, nullable=True),
        sa.Column("read", sa.Boolean, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade():
    op.drop_table("alerts")
    op.drop_column("applications", "first_response_days")
