"""Add Wenxin/Qianfan as a diagnostic provider.

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("provider_settings") as batch_op:
        batch_op.drop_constraint(
            "ck_provider_settings_provider",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_provider_settings_provider",
            "provider IN ('qwen', 'deepseek', 'doubao', 'wenxin', 'yuanbao', 'kimi')",
        )


def downgrade() -> None:
    op.execute("DELETE FROM provider_settings WHERE provider = 'wenxin'")
    with op.batch_alter_table("provider_settings") as batch_op:
        batch_op.drop_constraint(
            "ck_provider_settings_provider",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_provider_settings_provider",
            "provider IN ('qwen', 'deepseek', 'doubao', 'yuanbao', 'kimi')",
        )
