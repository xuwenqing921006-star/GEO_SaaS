"""Expand provider settings to the five automatic diagnostic platforms.

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-29
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_provider_settings_provider",
        "provider_settings",
        type_="check",
    )
    op.create_check_constraint(
        "ck_provider_settings_provider",
        "provider_settings",
        "provider IN ('qwen', 'deepseek', 'doubao', 'yuanbao', 'kimi')",
    )
    provider_settings = sa.table(
        "provider_settings",
        sa.column("provider", sa.String()),
        sa.column("enabled", sa.Boolean()),
        sa.column("base_url", sa.String()),
        sa.column("workspace_id", sa.String()),
        sa.column("writer_model", sa.String()),
        sa.column("reviewer_model", sa.String()),
        sa.column("fallback_model", sa.String()),
        sa.column("daily_budget_cny_fen", sa.Integer()),
        sa.column("timeout_seconds", sa.Integer()),
        sa.column("encrypted_api_key", sa.LargeBinary()),
        sa.column("secret_suffix", sa.String()),
        sa.column("last_tested_at", sa.DateTime(timezone=True)),
        sa.column("last_test_status", sa.String()),
        sa.column("version", sa.Integer()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    common = {
        "enabled": False,
        "workspace_id": None,
        "reviewer_model": None,
        "fallback_model": None,
        "daily_budget_cny_fen": 3_000,
        "timeout_seconds": 60,
        "encrypted_api_key": None,
        "secret_suffix": None,
        "last_tested_at": None,
        "last_test_status": "not_tested",
        "version": 1,
        "updated_at": datetime.now(UTC),
    }
    op.bulk_insert(
        provider_settings,
        [
            {
                **common,
                "provider": "doubao",
                "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                "writer_model": None,
            },
            {
                **common,
                "provider": "yuanbao",
                "base_url": "https://tokenhub.tencentmaas.com/v1",
                "writer_model": "hy3",
            },
            {
                **common,
                "provider": "kimi",
                "base_url": "https://api.moonshot.cn/v1",
                "writer_model": "kimi-k2.6",
            },
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM provider_settings WHERE provider IN ('doubao', 'yuanbao', 'kimi')")
    )
    op.drop_constraint(
        "ck_provider_settings_provider",
        "provider_settings",
        type_="check",
    )
    op.create_check_constraint(
        "ck_provider_settings_provider",
        "provider_settings",
        "provider IN ('qwen', 'deepseek')",
    )
