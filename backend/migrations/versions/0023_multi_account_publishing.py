"""Add isolated multi-account publishing targets.

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-04
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "publishing_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("channel_id", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
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
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "channel_id",
            "display_name",
            name="uq_publishing_accounts_channel_display_name",
        ),
    )
    op.create_index(
        "ix_publishing_accounts_channel_id",
        "publishing_accounts",
        ["channel_id"],
    )
    op.create_index(
        "ix_publishing_accounts_connection_status",
        "publishing_accounts",
        ["connection_status"],
    )
    op.add_column(
        "content_publications",
        sa.Column("publishing_account_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_content_publications_publishing_account_id",
        "content_publications",
        "publishing_accounts",
        ["publishing_account_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_content_publications_publishing_account_id",
        "content_publications",
        ["publishing_account_id"],
    )
    op.drop_constraint(
        "uq_content_publications_document_version",
        "content_publications",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_content_publications_document_version_account",
        "content_publications",
        ["document_id", "version_id", "publishing_account_id"],
    )

    connection = op.get_bind()
    legacy_configs = connection.execute(
        sa.text(
            "SELECT channel_id, enabled, connection_status, account_name, "
            "last_checked_at, last_error, version, updated_at "
            "FROM publishing_channel_configs"
        )
    ).mappings()
    for row in legacy_configs:
        account_id = uuid4()
        connection.execute(
            sa.text(
                "INSERT INTO publishing_accounts "
                "(id, channel_id, display_name, enabled, connection_status, "
                "account_name, last_checked_at, last_error, version, created_at, updated_at) "
                "VALUES (:id, :channel_id, :display_name, :enabled, :connection_status, "
                ":account_name, :last_checked_at, :last_error, :version, :created_at, :updated_at)"
            ),
            {
                "id": account_id,
                "channel_id": row["channel_id"],
                "display_name": row["account_name"] or "默认账号",
                "enabled": row["enabled"],
                "connection_status": row["connection_status"],
                "account_name": row["account_name"],
                "last_checked_at": row["last_checked_at"],
                "last_error": row["last_error"],
                "version": row["version"],
                "created_at": row["updated_at"] or datetime.now(UTC),
                "updated_at": row["updated_at"] or datetime.now(UTC),
            },
        )
        connection.execute(
            sa.text(
                "UPDATE content_publications SET publishing_account_id = :account_id "
                "WHERE channel_id = :channel_id AND publishing_account_id IS NULL"
            ),
            {"account_id": account_id, "channel_id": row["channel_id"]},
        )


def downgrade() -> None:
    op.drop_constraint(
        "uq_content_publications_document_version_account",
        "content_publications",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_content_publications_document_version",
        "content_publications",
        ["document_id", "version_id"],
    )
    op.drop_index(
        "ix_content_publications_publishing_account_id",
        table_name="content_publications",
    )
    op.drop_constraint(
        "fk_content_publications_publishing_account_id",
        "content_publications",
        type_="foreignkey",
    )
    op.drop_column("content_publications", "publishing_account_id")
    op.drop_index(
        "ix_publishing_accounts_connection_status",
        table_name="publishing_accounts",
    )
    op.drop_index("ix_publishing_accounts_channel_id", table_name="publishing_accounts")
    op.drop_table("publishing_accounts")
