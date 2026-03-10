"""Sprint 7: Add listing_alive, listing_last_checked, listing_died_at to applications."""

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column("applications", sa.Column("listing_alive", sa.Boolean, server_default=sa.text("true")))
    op.add_column("applications", sa.Column("listing_last_checked", sa.DateTime(timezone=True), nullable=True))
    op.add_column("applications", sa.Column("listing_died_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("applications", "listing_died_at")
    op.drop_column("applications", "listing_last_checked")
    op.drop_column("applications", "listing_alive")
