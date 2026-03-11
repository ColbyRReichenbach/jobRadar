"""Sprint 9: Add warm_connections table."""

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        "warm_connections",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("company_domain", sa.Text, nullable=False),
        sa.Column("contact_email", sa.Text, nullable=False),
        sa.Column("contact_name", sa.Text, nullable=True),
        sa.Column("email_count", sa.Integer, server_default=sa.text("1")),
        sa.Column("last_interaction_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade():
    op.drop_table("warm_connections")
