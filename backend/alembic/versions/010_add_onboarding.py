"""Sprint 6: Add onboarding fields to users and user_role_interests table."""

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column("users", sa.Column("onboarding_complete", sa.Boolean, server_default=sa.text("false")))
    op.add_column("users", sa.Column("preferred_locations", sa.JSON, nullable=True))
    op.add_column("users", sa.Column("preferred_remote_type", sa.Text, nullable=True))
    op.add_column("users", sa.Column("target_salary_min", sa.Integer, nullable=True))
    op.add_column("users", sa.Column("target_salary_max", sa.Integer, nullable=True))

    op.create_table(
        "user_role_interests",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("umbrella_id", sa.Uuid(), sa.ForeignKey("role_umbrellas.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("user_id", "umbrella_id", name="uq_user_role_interest"),
    )


def downgrade():
    op.drop_table("user_role_interests")
    op.drop_column("users", "target_salary_max")
    op.drop_column("users", "target_salary_min")
    op.drop_column("users", "preferred_remote_type")
    op.drop_column("users", "preferred_locations")
    op.drop_column("users", "onboarding_complete")
