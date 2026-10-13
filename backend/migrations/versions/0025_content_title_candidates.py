"""Persist alternative article titles for editorial selection.

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "content_versions",
        sa.Column("title_candidates", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("content_versions", "title_candidates")
