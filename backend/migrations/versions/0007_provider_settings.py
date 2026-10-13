"""Add encrypted provider settings and model usage.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_settings",
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("workspace_id", sa.String(length=200), nullable=True),
        sa.Column("writer_model", sa.String(length=100), nullable=True),
        sa.Column("reviewer_model", sa.String(length=100), nullable=True),
        sa.Column("fallback_model", sa.String(length=100), nullable=True),
        sa.Column("daily_budget_cny_fen", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("encrypted_api_key", sa.LargeBinary(), nullable=True),
        sa.Column("secret_suffix", sa.String(length=4), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_status", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provider IN ('qwen', 'deepseek')",
            name="ck_provider_settings_provider",
        ),
        sa.PrimaryKeyConstraint("provider"),
    )
    op.create_table(
        "runtime_settings",
        sa.Column("singleton_key", sa.Integer(), nullable=False),
        sa.Column(
            "default_client_monthly_budget_cny_fen",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "singleton_key = 1",
            name="ck_runtime_settings_singleton_key",
        ),
        sa.PrimaryKeyConstraint("singleton_key"),
    )
    op.create_table(
        "model_usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("purpose", sa.String(length=50), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_cny_fen", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("fallback_reason", sa.String(length=100), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column("output_hash", sa.String(length=64), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_model_usage_client_id",
        "model_usage",
        ["client_id"],
        unique=False,
    )
    op.create_index(
        "ix_model_usage_provider_day",
        "model_usage",
        ["provider", "usage_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_model_usage_provider_day", table_name="model_usage")
    op.drop_index("ix_model_usage_client_id", table_name="model_usage")
    op.drop_table("model_usage")
    op.drop_table("runtime_settings")
    op.drop_table("provider_settings")
