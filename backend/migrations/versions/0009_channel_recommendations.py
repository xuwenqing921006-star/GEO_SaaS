"""Add persisted channel recommendations.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "channel_recommendations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("channel_id", sa.String(length=100), nullable=False),
        sa.Column("catalog_version", sa.String(length=30), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("fit_score", sa.Integer(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("recommended_content_types", sa.JSON(), nullable=False),
        sa.Column("required_actions", sa.JSON(), nullable=False),
        sa.Column("caveat", sa.Text(), nullable=False),
        sa.Column("source_brief_ids", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "client_id",
            "channel_id",
            name="uq_channel_recommendations_client_channel",
        ),
    )
    op.create_index(
        "ix_channel_recommendations_client_id",
        "channel_recommendations",
        ["client_id"],
    )
    op.create_index(
        "ix_channel_recommendations_channel_id",
        "channel_recommendations",
        ["channel_id"],
    )
    op.create_index(
        "ix_channel_recommendations_active",
        "channel_recommendations",
        ["active"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_channel_recommendations_active",
        table_name="channel_recommendations",
    )
    op.drop_index(
        "ix_channel_recommendations_channel_id",
        table_name="channel_recommendations",
    )
    op.drop_index(
        "ix_channel_recommendations_client_id",
        table_name="channel_recommendations",
    )
    op.drop_table("channel_recommendations")
