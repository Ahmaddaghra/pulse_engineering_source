"""Record XML extraction version alongside durable receipts."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "fetch_receipts",
        sa.Column(
            "collection_parser_version",
            sa.String(40),
            nullable=False,
            server_default="xml-metadata-v1",
        ),
    )


def downgrade():
    op.drop_column("fetch_receipts", "collection_parser_version")
