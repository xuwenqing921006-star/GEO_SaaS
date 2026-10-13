"""Harden monitoring metrics, actions, and evaluation integrity.

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "monitoring_samples",
        sa.Column(
            "question_priority",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.alter_column(
        "monitoring_evaluations",
        "facts_accurate",
        existing_type=sa.Boolean(),
        nullable=True,
    )

    op.create_table(
        "optimization_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("action_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_type",
            "source_id",
            "action_type",
            name="uq_optimization_actions_source_action",
        ),
    )
    for column in (
        "client_id",
        "source_type",
        "source_id",
        "action_type",
        "target_page",
        "status",
    ):
        op.create_index(
            f"ix_optimization_actions_{column}",
            "optimization_actions",
            [column],
        )

    op.add_column(
        "monitoring_feedback",
        sa.Column("converted_record_type", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "monitoring_feedback",
        sa.Column("converted_record_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_monitoring_feedback_converted_record",
        "monitoring_feedback",
        "optimization_actions",
        ["converted_record_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_monitoring_feedback_converted_record_id",
        "monitoring_feedback",
        ["converted_record_id"],
    )
    op.execute(
        """
        DELETE FROM monitoring_feedback AS duplicate
        USING monitoring_feedback AS keeper
        WHERE duplicate.evaluation_id = keeper.evaluation_id
          AND duplicate.action_type = keeper.action_type
          AND (
              duplicate.created_at > keeper.created_at
              OR (
                  duplicate.created_at = keeper.created_at
                  AND duplicate.id::text > keeper.id::text
              )
          )
        """
    )
    op.create_unique_constraint(
        "uq_monitoring_feedback_evaluation_action",
        "monitoring_feedback",
        ["evaluation_id", "action_type"],
    )
    op.execute(
        """
        INSERT INTO optimization_actions (
            id, client_id, source_type, source_id, action_type, title, reason,
            target_level, target_page, status, created_at
        )
        SELECT
            id, client_id, 'monitoring_evaluation', evaluation_id, action_type,
            '历史监测改进动作', reason, target_level, target_page, status, created_at
        FROM monitoring_feedback
        """
    )
    op.execute(
        """
        UPDATE monitoring_feedback
        SET converted_record_type = 'optimization_action',
            converted_record_id = id
        """
    )
    op.alter_column(
        "monitoring_feedback",
        "converted_record_type",
        existing_type=sa.String(length=40),
        nullable=False,
    )
    op.alter_column(
        "monitoring_feedback",
        "converted_record_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_monitoring_feedback_evaluation_action",
        "monitoring_feedback",
        type_="unique",
    )
    op.drop_index(
        "ix_monitoring_feedback_converted_record_id",
        table_name="monitoring_feedback",
    )
    op.drop_constraint(
        "fk_monitoring_feedback_converted_record",
        "monitoring_feedback",
        type_="foreignkey",
    )
    op.drop_column("monitoring_feedback", "converted_record_id")
    op.drop_column("monitoring_feedback", "converted_record_type")
    op.drop_table("optimization_actions")
    op.execute(
        """
        UPDATE monitoring_evaluations
        SET facts_accurate = false
        WHERE facts_accurate IS NULL
        """
    )
    op.alter_column(
        "monitoring_evaluations",
        "facts_accurate",
        existing_type=sa.Boolean(),
        nullable=False,
    )
    op.drop_column("monitoring_samples", "question_priority")
