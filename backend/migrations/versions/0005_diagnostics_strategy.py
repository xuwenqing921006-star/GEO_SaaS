"""Add explainable diagnostics and strategy planning.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "diagnostic_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "client_id",
            sa.Uuid(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("current_level", sa.String(2), nullable=False),
        sa.Column("scores", sa.JSON(), nullable=False),
        sa.Column("fact_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("fact_snapshot", sa.JSON(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_diagnostic_runs_client_id", "diagnostic_runs", ["client_id"])
    op.create_index("ix_diagnostic_runs_status", "diagnostic_runs", ["status"])

    op.create_table(
        "diagnostic_issues",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "diagnostic_run_id",
            sa.Uuid(),
            sa.ForeignKey("diagnostic_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_id",
            sa.Uuid(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("suggested_action", sa.Text(), nullable=False),
        sa.Column("target_page", sa.String(3), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("note", sa.String(1000)),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_diagnostic_issues_diagnostic_run_id",
        "diagnostic_issues",
        ["diagnostic_run_id"],
    )
    op.create_index("ix_diagnostic_issues_client_id", "diagnostic_issues", ["client_id"])
    op.create_index("ix_diagnostic_issues_category", "diagnostic_issues", ["category"])
    op.create_index("ix_diagnostic_issues_status", "diagnostic_issues", ["status"])

    op.create_table(
        "strategy_bundles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "client_id",
            sa.Uuid(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "diagnostic_run_id",
            sa.Uuid(),
            sa.ForeignKey("diagnostic_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("client_id", name="uq_strategy_bundles_client_id"),
    )
    op.create_index("ix_strategy_bundles_client_id", "strategy_bundles", ["client_id"])
    op.create_index(
        "ix_strategy_bundles_diagnostic_run_id",
        "strategy_bundles",
        ["diagnostic_run_id"],
    )

    op.create_table(
        "strategy_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "bundle_id",
            sa.Uuid(),
            sa.ForeignKey("strategy_bundles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_id",
            sa.Uuid(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("family", sa.String(30)),
        sa.Column("keyword_type", sa.String(30)),
        sa.Column("provenance", sa.String(30), nullable=False),
        sa.Column("target_level", sa.String(2), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("locked", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.create_index("ix_strategy_items_bundle_id", "strategy_items", ["bundle_id"])
    op.create_index("ix_strategy_items_client_id", "strategy_items", ["client_id"])
    op.create_index("ix_strategy_items_kind", "strategy_items", ["kind"])
    op.create_index("ix_strategy_items_family", "strategy_items", ["family"])
    op.create_index("ix_strategy_items_keyword_type", "strategy_items", ["keyword_type"])
    op.create_index("ix_strategy_items_active", "strategy_items", ["active"])

    op.create_table(
        "content_briefs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "bundle_id",
            sa.Uuid(),
            sa.ForeignKey("strategy_bundles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_id",
            sa.Uuid(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("content_type", sa.String(30), nullable=False),
        sa.Column("target_question_ids", sa.JSON(), nullable=False),
        sa.Column("target_keywords", sa.JSON(), nullable=False),
        sa.Column("target_level", sa.String(2), nullable=False),
        sa.Column("audience", sa.Text(), nullable=False),
        sa.Column("angle", sa.Text(), nullable=False),
        sa.Column("required_fact_ids", sa.JSON(), nullable=False),
        sa.Column("required_evidence_ids", sa.JSON(), nullable=False),
        sa.Column("expected_recommendation_reason", sa.Text(), nullable=False),
        sa.Column("prohibited_claims", sa.JSON(), nullable=False),
        sa.Column("retest_questions", sa.JSON(), nullable=False),
        sa.Column("suggested_channel_ids", sa.JSON(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.create_index("ix_content_briefs_bundle_id", "content_briefs", ["bundle_id"])
    op.create_index("ix_content_briefs_client_id", "content_briefs", ["client_id"])
    op.create_index("ix_content_briefs_status", "content_briefs", ["status"])


def downgrade() -> None:
    op.drop_table("content_briefs")
    op.drop_table("strategy_items")
    op.drop_table("strategy_bundles")
    op.drop_table("diagnostic_issues")
    op.drop_table("diagnostic_runs")
