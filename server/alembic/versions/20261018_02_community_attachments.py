"""Add server-stored photos to Community discussions.

Revision ID: 20261018_02
Revises: 20261018_01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261018_02"
down_revision: Union[str, None] = "20261018_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "community_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("post_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("image_data", sa.LargeBinary(), nullable=False),
        sa.Column("media_type", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["post_id"], ["community_posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_community_attachments_post_id", "community_attachments", ["post_id"])
    op.create_index("ix_community_attachments_account_id", "community_attachments", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_community_attachments_account_id", table_name="community_attachments")
    op.drop_index("ix_community_attachments_post_id", table_name="community_attachments")
    op.drop_table("community_attachments")
