"""Add role_umbrellas table and umbrella_id FK on applications

Revision ID: 007
Revises: 006
Create Date: 2026-03-09
"""
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "role_umbrellas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=True),
        sa.Column("typical_skills", sa.JSON(), nullable=True),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.ForeignKeyConstraint(["parent_id"], ["role_umbrellas.id"]),
    )
    op.add_column("applications", sa.Column("umbrella_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_app_umbrella", "applications", "role_umbrellas", ["umbrella_id"], ["id"])


def downgrade():
    op.drop_constraint("fk_app_umbrella", "applications", type_="foreignkey")
    op.drop_column("applications", "umbrella_id")
    op.drop_table("role_umbrellas")
