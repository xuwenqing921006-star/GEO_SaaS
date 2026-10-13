"""Add sampled AI visibility monitoring closed loop.

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "monitoring_question_sets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("frozen", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "questions",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_monitoring_question_sets_client_id",
        "monitoring_question_sets",
        ["client_id"],
    )
    op.create_index(
        "ix_monitoring_question_sets_frozen",
        "monitoring_question_sets",
        ["frozen"],
    )

    op.create_table(
        "monitoring_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("question_set_id", sa.Uuid(), nullable=False),
        sa.Column("question_set_version", sa.Integer(), nullable=False),
        sa.Column("question_snapshot", sa.JSON(), nullable=False),
        sa.Column("platform_ids", sa.JSON(), nullable=False),
        sa.Column("api_sample_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="queued",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["question_set_id"],
            ["monitoring_question_sets.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_monitoring_batches_client_id",
        "monitoring_batches",
        ["client_id"],
    )
    op.create_index(
        "ix_monitoring_batches_question_set_id",
        "monitoring_batches",
        ["question_set_id"],
    )
    op.create_index(
        "ix_monitoring_batches_status",
        "monitoring_batches",
        ["status"],
    )

    op.create_table(
        "monitoring_samples",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("platform_id", sa.String(length=50), nullable=False),
        sa.Column("platform_name", sa.String(length=100), nullable=False),
        sa.Column("collection_mode", sa.String(length=30), nullable=False),
        sa.Column("question_id", sa.String(length=100), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("question_family", sa.String(length=50), nullable=False),
        sa.Column(
            "is_brand_query",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="not_executed",
        ),
        sa.Column("raw_answer", sa.Text(), nullable=True),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["monitoring_batches.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "batch_id",
            "platform_id",
            "question_id",
            "attempt",
            name="uq_monitoring_samples_batch_platform_question_attempt",
        ),
    )
    for column in (
        "batch_id",
        "client_id",
        "platform_id",
        "collection_mode",
        "question_id",
        "question_family",
        "status",
        "asked_at",
    ):
        op.create_index(
            f"ix_monitoring_samples_{column}",
            "monitoring_samples",
            [column],
        )

    op.create_table(
        "monitoring_evaluations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sample_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("brand_found", sa.Boolean(), nullable=False),
        sa.Column("correctly_associated", sa.Boolean(), nullable=False),
        sa.Column("recommended", sa.Boolean(), nullable=False),
        sa.Column("recommendation_supported", sa.Boolean(), nullable=True),
        sa.Column("facts_accurate", sa.Boolean(), nullable=False),
        sa.Column(
            "source_visible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("mentioned_name", sa.String(length=200), nullable=True),
        sa.Column("reasons", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column(
            "incorrect_facts",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "visible_sources",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column(
            "evaluator",
            sa.String(length=20),
            nullable=False,
            server_default="system",
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["sample_id"],
            ["monitoring_samples.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sample_id", name="uq_monitoring_evaluations_sample_id"),
    )
    op.create_index(
        "ix_monitoring_evaluations_sample_id",
        "monitoring_evaluations",
        ["sample_id"],
    )
    op.create_index(
        "ix_monitoring_evaluations_client_id",
        "monitoring_evaluations",
        ["client_id"],
    )

    op.create_table(
        "monitoring_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_id", sa.Uuid(), nullable=False),
        sa.Column("action_type", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("target_level", sa.String(length=2), nullable=False),
        sa.Column("target_page", sa.String(length=3), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="open",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["evaluation_id"],
            ["monitoring_evaluations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("client_id", "evaluation_id", "action_type", "status"):
        op.create_index(
            f"ix_monitoring_feedback_{column}",
            "monitoring_feedback",
            [column],
        )


def downgrade() -> None:
    op.drop_table("monitoring_feedback")
    op.drop_table("monitoring_evaluations")
    op.drop_table("monitoring_samples")
    op.drop_table("monitoring_batches")
    op.drop_table("monitoring_question_sets")
