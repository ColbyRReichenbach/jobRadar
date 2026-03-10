"""Add salary intelligence columns to applications.

Revision ID: 016
Revises: 015
"""

from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("applications", sa.Column("salary_min", sa.Integer, nullable=True))
    op.add_column("applications", sa.Column("salary_max", sa.Integer, nullable=True))
    op.add_column("applications", sa.Column("salary_currency", sa.Text, nullable=True))
    op.add_column("applications", sa.Column("salary_period", sa.Text, nullable=True))


def downgrade():
    op.drop_column("applications", "salary_min")
    op.drop_column("applications", "salary_max")
    op.drop_column("applications", "salary_currency")
    op.drop_column("applications", "salary_period")
