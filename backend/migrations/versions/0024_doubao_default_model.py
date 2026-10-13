"""Set the default Doubao model for three-platform diagnostics.

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DOUBAO_DEFAULT_MODEL = "doubao-seed-2-0-lite-260215"


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE provider_settings SET writer_model = :model, version = version + 1 "
            "WHERE provider = 'doubao' AND writer_model IS NULL"
        ).bindparams(model=DOUBAO_DEFAULT_MODEL),
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE provider_settings SET writer_model = NULL, version = version + 1 "
            "WHERE provider = 'doubao' AND writer_model = :model"
        ).bindparams(model=DOUBAO_DEFAULT_MODEL),
    )
