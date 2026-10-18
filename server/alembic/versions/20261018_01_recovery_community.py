"""Add secure account recovery and member discussion board.

Revision ID: 20261018_01
Revises: b89b2c319270
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261018_01"
down_revision: Union[str, None] = "b89b2c319270"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "password_reset_challenges",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_password_reset_challenges_account_id", "password_reset_challenges", ["account_id"])

    op.create_table(
        "community_posts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("hidden", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_community_posts_account_id", "community_posts", ["account_id"])
    op.create_index("ix_community_posts_category", "community_posts", ["category"])
    op.create_index("ix_community_posts_hidden", "community_posts", ["hidden"])
    op.create_index("ix_community_posts_created_at", "community_posts", ["created_at"])

    op.create_table(
        "community_replies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("post_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("hidden", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["post_id"], ["community_posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_community_replies_post_id", "community_replies", ["post_id"])
    op.create_index("ix_community_replies_account_id", "community_replies", ["account_id"])
    op.create_index("ix_community_replies_hidden", "community_replies", ["hidden"])
    op.create_index("ix_community_replies_created_at", "community_replies", ["created_at"])

    op.create_table(
        "community_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("reporter_id", sa.String(length=36), nullable=False),
        sa.Column("post_id", sa.String(length=36), nullable=True),
        sa.Column("reply_id", sa.String(length=36), nullable=True),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reviewed_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["post_id"], ["community_posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reply_id"], ["community_replies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reporter_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_community_reports_reporter_id", "community_reports", ["reporter_id"])
    op.create_index("ix_community_reports_post_id", "community_reports", ["post_id"])
    op.create_index("ix_community_reports_reply_id", "community_reports", ["reply_id"])
    op.create_index("ix_community_reports_status", "community_reports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_community_reports_status", table_name="community_reports")
    op.drop_index("ix_community_reports_reply_id", table_name="community_reports")
    op.drop_index("ix_community_reports_post_id", table_name="community_reports")
    op.drop_index("ix_community_reports_reporter_id", table_name="community_reports")
    op.drop_table("community_reports")
    op.drop_index("ix_community_replies_created_at", table_name="community_replies")
    op.drop_index("ix_community_replies_hidden", table_name="community_replies")
    op.drop_index("ix_community_replies_account_id", table_name="community_replies")
    op.drop_index("ix_community_replies_post_id", table_name="community_replies")
    op.drop_table("community_replies")
    op.drop_index("ix_community_posts_created_at", table_name="community_posts")
    op.drop_index("ix_community_posts_hidden", table_name="community_posts")
    op.drop_index("ix_community_posts_category", table_name="community_posts")
    op.drop_index("ix_community_posts_account_id", table_name="community_posts")
    op.drop_table("community_posts")
    op.drop_index("ix_password_reset_challenges_account_id", table_name="password_reset_challenges")
    op.drop_table("password_reset_challenges")
