"""Sprint 8: Add ats_behaviors table."""

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        "ats_behaviors",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("platform", sa.Text, nullable=False),
        sa.Column("metric_name", sa.Text, nullable=False),
        sa.Column("metric_value", sa.Float, server_default=sa.text("0.0")),
        sa.Column("sample_size", sa.Integer, server_default=sa.text("0")),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("platform", "metric_name", name="uq_ats_metric"),
    )


def downgrade():
    op.drop_table("ats_behaviors")
