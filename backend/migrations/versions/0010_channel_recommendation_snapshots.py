"""Add immutable per-brief channel recommendation snapshots.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_channel_recommendations_client_channel",
        "channel_recommendations",
        type_="unique",
    )
    op.add_column(
        "channel_recommendations",
        sa.Column("generation_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "channel_recommendations",
        sa.Column("brief_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "channel_recommendations",
        sa.Column("content_document_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "channel_recommendations",
        sa.Column(
            "channel_snapshot",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        "channel_recommendations",
        sa.Column(
            "brief_snapshot",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    for name in (
        "required_adaptation",
        "account_positioning",
        "authorization_note",
        "cost_note",
        "risk_note",
    ):
        op.add_column(
            "channel_recommendations",
            sa.Column(name, sa.Text(), nullable=False, server_default=""),
        )
    op.add_column(
        "channel_recommendations",
        sa.Column(
            "target_ecosystems",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.create_foreign_key(
        "fk_channel_recommendations_brief_id",
        "channel_recommendations",
        "content_briefs",
        ["brief_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_channel_recommendations_content_document_id",
        "channel_recommendations",
        "content_documents",
        ["content_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_channel_recommendations_generation_id",
        "channel_recommendations",
        ["generation_id"],
    )
    op.create_index(
        "ix_channel_recommendations_brief_id",
        "channel_recommendations",
        ["brief_id"],
    )
    op.create_index(
        "ix_channel_recommendations_content_document_id",
        "channel_recommendations",
        ["content_document_id"],
    )
    op.create_unique_constraint(
        "uq_channel_recommendations_generation_brief_channel",
        "channel_recommendations",
        ["client_id", "generation_id", "brief_id", "channel_id"],
    )
    op.execute("UPDATE channel_recommendations SET active = false")


def downgrade() -> None:
    # The former schema allowed only one row per client/channel. Preserve the most
    # recent row for each pair before restoring that constraint.
    op.execute(
        """
        DELETE FROM channel_recommendations
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY client_id, channel_id
                        ORDER BY active DESC, generated_at DESC, id DESC
                    ) AS row_rank
                FROM channel_recommendations
            ) AS ranked
            WHERE row_rank > 1
        )
        """,
    )
    op.drop_constraint(
        "uq_channel_recommendations_generation_brief_channel",
        "channel_recommendations",
        type_="unique",
    )
    op.drop_index(
        "ix_channel_recommendations_content_document_id",
        table_name="channel_recommendations",
    )
    op.drop_index(
        "ix_channel_recommendations_brief_id",
        table_name="channel_recommendations",
    )
    op.drop_index(
        "ix_channel_recommendations_generation_id",
        table_name="channel_recommendations",
    )
    op.drop_constraint(
        "fk_channel_recommendations_content_document_id",
        "channel_recommendations",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_channel_recommendations_brief_id",
        "channel_recommendations",
        type_="foreignkey",
    )
    op.drop_column("channel_recommendations", "target_ecosystems")
    op.drop_column("channel_recommendations", "risk_note")
    op.drop_column("channel_recommendations", "cost_note")
    op.drop_column("channel_recommendations", "authorization_note")
    op.drop_column("channel_recommendations", "account_positioning")
    op.drop_column("channel_recommendations", "required_adaptation")
    op.drop_column("channel_recommendations", "channel_snapshot")
    op.drop_column("channel_recommendations", "brief_snapshot")
    op.drop_column("channel_recommendations", "content_document_id")
    op.drop_column("channel_recommendations", "brief_id")
    op.drop_column("channel_recommendations", "generation_id")
    op.create_unique_constraint(
        "uq_channel_recommendations_client_channel",
        "channel_recommendations",
        ["client_id", "channel_id"],
    )
