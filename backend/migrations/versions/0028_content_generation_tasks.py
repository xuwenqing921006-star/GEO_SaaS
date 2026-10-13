"""Add persistent content generation tasks.

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_generation_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column(
            "platform_type",
            sa.String(length=30),
            nullable=False,
            server_default="self_media",
        ),
        sa.Column("keyword_snapshots", sa.JSON(), nullable=False),
        sa.Column("channel_ids", sa.JSON(), nullable=False),
        sa.Column("article_count_per_channel", sa.Integer(), nullable=False),
        sa.Column("length", sa.String(length=20), nullable=False),
        sa.Column("content_form_codes", sa.JSON(), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_content_generation_tasks_client_id",
        "content_generation_tasks",
        ["client_id"],
    )
    op.create_index(
        "ix_content_generation_tasks_archived",
        "content_generation_tasks",
        ["archived"],
    )
    with op.batch_alter_table("content_documents") as batch_op:
        batch_op.add_column(sa.Column("generation_task_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_content_documents_generation_task_id",
            "content_generation_tasks",
            ["generation_task_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_content_documents_generation_task_id",
            ["generation_task_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("content_documents") as batch_op:
        batch_op.drop_index("ix_content_documents_generation_task_id")
        batch_op.drop_constraint(
            "fk_content_documents_generation_task_id",
            type_="foreignkey",
        )
        batch_op.drop_column("generation_task_id")
    op.drop_index(
        "ix_content_generation_tasks_archived",
        table_name="content_generation_tasks",
    )
    op.drop_index(
        "ix_content_generation_tasks_client_id",
        table_name="content_generation_tasks",
    )
    op.drop_table("content_generation_tasks")
