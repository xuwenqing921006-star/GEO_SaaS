"""Synchronize required facts for existing content-form prompts.

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE prompt_templates "
        """SET required_fact_keys = CAST('["service", "price"]' AS json) """
        "WHERE code = 'price_guide'",
    )
    op.execute(
        "UPDATE prompt_templates "
        """SET required_fact_keys = CAST('["service", "process"]' AS json) """
        "WHERE code = 'service_process'",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE prompt_templates "
        """SET required_fact_keys = CAST('["service"]' AS json) """
        "WHERE code IN ('price_guide', 'service_process')",
    )
