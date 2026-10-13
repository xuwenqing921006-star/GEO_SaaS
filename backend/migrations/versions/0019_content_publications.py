"""Persist external publication facts independently from document workflow state.

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-29
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_publications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("channel_id", sa.String(length=80), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["content_documents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["content_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "version_id",
            name="uq_content_publications_document_version",
        ),
    )
    op.create_index(
        "ix_content_publications_document_id",
        "content_publications",
        ["document_id"],
    )
    op.create_index(
        "ix_content_publications_version_id",
        "content_publications",
        ["version_id"],
    )
    op.create_index(
        "ix_content_publications_published_at",
        "content_publications",
        ["published_at"],
    )
    connection = op.get_bind()
    published_documents = connection.execute(
        sa.text(
            "SELECT d.id AS document_id, d.current_version_id AS version_id, "
            "v.target_channel_id AS channel_id "
            "FROM content_documents d "
            "JOIN content_versions v ON v.id = d.current_version_id "
            "WHERE d.status = 'published'",
        ),
    ).mappings()
    now = datetime.now(UTC)
    for row in published_documents:
        connection.execute(
            sa.text(
                "INSERT INTO content_publications "
                "(id, document_id, version_id, channel_id, published_at) "
                "VALUES (:id, :document_id, :version_id, :channel_id, :published_at)",
            ),
            {
                "id": uuid4(),
                "document_id": row["document_id"],
                "version_id": row["version_id"],
                "channel_id": row["channel_id"],
                "published_at": now,
            },
        )


def downgrade() -> None:
    op.drop_index(
        "ix_content_publications_published_at",
        table_name="content_publications",
    )
    op.drop_index(
        "ix_content_publications_version_id",
        table_name="content_publications",
    )
    op.drop_index(
        "ix_content_publications_document_id",
        table_name="content_publications",
    )
    op.drop_table("content_publications")
