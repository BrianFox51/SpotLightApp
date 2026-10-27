"""Add encrypted versioned provider-secret history."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261027_01"
down_revision: Union[str, None] = "20261018_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "provider_secret_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=60), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=True),
        sa.Column("fingerprint", sa.String(length=16), nullable=True),
        sa.Column("change_note", sa.String(length=500), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "version", name="uq_provider_secret_version"),
    )
    op.create_index(
        "ix_provider_secret_versions_provider",
        "provider_secret_versions",
        ["provider"],
    )


def downgrade() -> None:
    op.drop_index("ix_provider_secret_versions_provider", table_name="provider_secret_versions")
    op.drop_table("provider_secret_versions")
