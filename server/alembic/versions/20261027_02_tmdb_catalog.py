"""Add shared provider catalog cards for incremental client sync."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261027_02"
down_revision: Union[str, None] = "20261027_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "provider_catalog_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=60), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("provider_id", sa.String(length=120), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("updated_at_ms", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "category", "provider_id", name="uq_provider_catalog_item"),
    )
    op.create_index("ix_provider_catalog_items_provider", "provider_catalog_items", ["provider"])
    op.create_index("ix_provider_catalog_items_updated_at_ms", "provider_catalog_items", ["updated_at_ms"])


def downgrade() -> None:
    op.drop_index("ix_provider_catalog_items_updated_at_ms", table_name="provider_catalog_items")
    op.drop_index("ix_provider_catalog_items_provider", table_name="provider_catalog_items")
    op.drop_table("provider_catalog_items")
