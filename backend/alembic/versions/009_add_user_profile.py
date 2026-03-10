"""Sprint 5: Add user_profiles table and match_score to applications."""

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("user_id", sa.Text, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("raw_text", sa.Text, nullable=True),
        sa.Column("skills", sa.JSON, nullable=True),
        sa.Column("education", sa.JSON, nullable=True),
        sa.Column("experience_years", sa.Integer, nullable=True),
        sa.Column("tools", sa.JSON, nullable=True),
        sa.Column("certifications", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.add_column("applications", sa.Column("match_score", sa.Integer, nullable=True))


def downgrade():
    op.drop_column("applications", "match_score")
    op.drop_table("user_profiles")
