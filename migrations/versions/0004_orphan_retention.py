"""Persist orphan payload deadline independently of lease lifetime."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "fetch_attempts", sa.Column("payload_expires_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade():
    op.drop_column("fetch_attempts", "payload_expires_at")
