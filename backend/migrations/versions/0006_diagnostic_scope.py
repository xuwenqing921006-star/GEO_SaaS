"""Persist diagnostic scope and monitoring window.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_SCOPE = ["entity", "evidence", "content", "source", "visibility"]


def upgrade() -> None:
    op.add_column(
        "diagnostic_runs",
        sa.Column("scope", sa.JSON(), nullable=True),
    )
    op.add_column(
        "diagnostic_runs",
        sa.Column("monitoring_window_days", sa.Integer(), nullable=True),
    )
    diagnostic_runs = sa.table(
        "diagnostic_runs",
        sa.column("scope", sa.JSON()),
        sa.column("monitoring_window_days", sa.Integer()),
    )
    op.execute(
        diagnostic_runs.update().values(
            scope=DEFAULT_SCOPE,
            monitoring_window_days=30,
        ),
    )
    op.alter_column("diagnostic_runs", "scope", nullable=False)
    op.alter_column(
        "diagnostic_runs",
        "monitoring_window_days",
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("diagnostic_runs", "monitoring_window_days")
    op.drop_column("diagnostic_runs", "scope")
