"""Add simplified GEO workflow fields.

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "diagnostic_runs",
        sa.Column(
            "platform_results",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "diagnostic_runs",
        sa.Column(
            "monitoring_sample_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    op.add_column(
        "strategy_items",
        sa.Column("main_keyword", sa.String(length=300), nullable=True),
    )
    op.add_column(
        "strategy_items",
        sa.Column("user_intent", sa.String(length=300), nullable=True),
    )
    op.add_column(
        "strategy_items",
        sa.Column(
            "selected",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "ix_strategy_items_selected",
        "strategy_items",
        ["selected"],
    )
    op.execute(
        """
        UPDATE strategy_items
        SET main_keyword = text,
            user_intent = CASE
                WHEN kind = 'keyword' THEN '了解相关服务'
                ELSE NULL
            END
        WHERE kind = 'keyword'
        """
    )

    op.add_column(
        "content_briefs",
        sa.Column("keyword_strategy_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "content_briefs",
        sa.Column("keyword_type", sa.String(length=30), nullable=True),
    )
    op.create_index(
        "ix_content_briefs_keyword_strategy_id",
        "content_briefs",
        ["keyword_strategy_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_content_briefs_keyword_strategy_id",
        table_name="content_briefs",
    )
    op.drop_column("content_briefs", "keyword_type")
    op.drop_column("content_briefs", "keyword_strategy_id")
    op.drop_index("ix_strategy_items_selected", table_name="strategy_items")
    op.drop_column("strategy_items", "selected")
    op.drop_column("strategy_items", "user_intent")
    op.drop_column("strategy_items", "main_keyword")
    op.drop_column("diagnostic_runs", "monitoring_sample_count")
    op.drop_column("diagnostic_runs", "platform_results")
