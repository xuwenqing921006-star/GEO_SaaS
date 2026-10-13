"""Add independent publication states and Toutiao channel configuration.

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-29
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "content_publications",
        sa.Column("status", sa.String(length=30), nullable=False, server_default="published"),
    )
    op.add_column(
        "content_publications",
        sa.Column("platform_post_id", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "content_publications",
        sa.Column("public_url", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "content_publications",
        sa.Column("error_message", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "content_publications",
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "content_publications",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.alter_column(
        "content_publications",
        "published_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.create_index(
        "ix_content_publications_status",
        "content_publications",
        ["status"],
    )
    op.create_table(
        "publishing_channel_configs",
        sa.Column("channel_id", sa.String(length=80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "connection_status",
            sa.String(length=30),
            nullable=False,
            server_default="disconnected",
        ),
        sa.Column("account_name", sa.String(length=200), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("channel_id"),
    )
    op.create_index(
        "ix_publishing_channel_configs_connection_status",
        "publishing_channel_configs",
        ["connection_status"],
    )
    configs = sa.table(
        "publishing_channel_configs",
        sa.column("channel_id", sa.String()),
        sa.column("enabled", sa.Boolean()),
        sa.column("connection_status", sa.String()),
        sa.column("account_name", sa.String()),
        sa.column("last_checked_at", sa.DateTime(timezone=True)),
        sa.column("last_error", sa.String()),
        sa.column("version", sa.Integer()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        configs,
        [
            {
                "channel_id": "toutiao",
                "enabled": False,
                "connection_status": "disconnected",
                "account_name": None,
                "last_checked_at": None,
                "last_error": None,
                "version": 1,
                "updated_at": datetime.now(UTC),
            },
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_publishing_channel_configs_connection_status",
        table_name="publishing_channel_configs",
    )
    op.drop_table("publishing_channel_configs")
    op.drop_index("ix_content_publications_status", table_name="content_publications")
    op.drop_column("content_publications", "updated_at")
    op.drop_column("content_publications", "submitted_at")
    op.drop_column("content_publications", "error_message")
    op.drop_column("content_publications", "public_url")
    op.drop_column("content_publications", "platform_post_id")
    op.drop_column("content_publications", "status")
    op.alter_column(
        "content_publications",
        "published_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
