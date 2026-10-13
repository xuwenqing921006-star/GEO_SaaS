"""Add editable keyword profiles and confirmation-based generation tasks.

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("strategy_bundles") as batch_op:
        batch_op.alter_column(
            "diagnostic_run_id",
            existing_type=sa.Uuid(),
            nullable=True,
        )

    op.create_table(
        "keyword_profiles",
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("primary_keyword", sa.String(length=300), nullable=False),
        sa.Column("regions", sa.JSON(), nullable=False),
        sa.Column("secondary_keywords", sa.JSON(), nullable=False),
        sa.Column("keyword_types", sa.JSON(), nullable=False),
        sa.Column("recommended_count", sa.Integer(), nullable=False),
        sa.Column("knowledge_fingerprint", sa.String(length=64), nullable=False),
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
        sa.PrimaryKeyConstraint("client_id"),
    )
    op.create_table(
        "keyword_generations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("primary_keyword", sa.String(length=300), nullable=False),
        sa.Column("regions", sa.JSON(), nullable=False),
        sa.Column("secondary_keywords", sa.JSON(), nullable=False),
        sa.Column("keyword_types", sa.JSON(), nullable=False),
        sa.Column("knowledge_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("generated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("filtered_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confirmed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_keyword_generations_client_id", "keyword_generations", ["client_id"])
    op.create_index("ix_keyword_generations_job_id", "keyword_generations", ["job_id"])
    op.create_index("ix_keyword_generations_status", "keyword_generations", ["status"])
    op.create_index("ix_keyword_generations_archived", "keyword_generations", ["archived"])

    op.create_table(
        "keyword_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("generation_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.String(length=500), nullable=False),
        sa.Column("main_keyword", sa.String(length=300), nullable=False),
        sa.Column("keyword_type", sa.String(length=30), nullable=False),
        sa.Column("user_intent", sa.String(length=300), nullable=False),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("secondary_keyword", sa.String(length=300), nullable=True),
        sa.Column("recommended_content_type", sa.String(length=80), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("confirmed_item_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["confirmed_item_id"],
            ["strategy_items.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["generation_id"],
            ["keyword_generations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "client_id",
            "normalized_text",
            name="uq_keyword_candidates_client_normalized_text",
        ),
    )
    op.create_index("ix_keyword_candidates_generation_id", "keyword_candidates", ["generation_id"])
    op.create_index("ix_keyword_candidates_client_id", "keyword_candidates", ["client_id"])
    op.create_index("ix_keyword_candidates_keyword_type", "keyword_candidates", ["keyword_type"])
    op.create_index("ix_keyword_candidates_selected", "keyword_candidates", ["selected"])
    op.create_index("ix_keyword_candidates_active", "keyword_candidates", ["active"])


def downgrade() -> None:
    op.drop_index("ix_keyword_candidates_active", table_name="keyword_candidates")
    op.drop_index("ix_keyword_candidates_selected", table_name="keyword_candidates")
    op.drop_index("ix_keyword_candidates_keyword_type", table_name="keyword_candidates")
    op.drop_index("ix_keyword_candidates_client_id", table_name="keyword_candidates")
    op.drop_index("ix_keyword_candidates_generation_id", table_name="keyword_candidates")
    op.drop_table("keyword_candidates")
    op.drop_index("ix_keyword_generations_archived", table_name="keyword_generations")
    op.drop_index("ix_keyword_generations_status", table_name="keyword_generations")
    op.drop_index("ix_keyword_generations_job_id", table_name="keyword_generations")
    op.drop_index("ix_keyword_generations_client_id", table_name="keyword_generations")
    op.drop_table("keyword_generations")
    op.drop_table("keyword_profiles")

    # A keyword-only bundle has no diagnostic reference and cannot satisfy the old schema.
    # Refuse the destructive downgrade instead of silently deleting confirmed keywords.
    connection = op.get_bind()
    null_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM strategy_bundles WHERE diagnostic_run_id IS NULL"),
    ).scalar_one()
    if null_count:
        raise RuntimeError(
            "cannot downgrade while keyword-only strategy bundles exist; "
            "run a diagnostic for those clients first",
        )
    with op.batch_alter_table("strategy_bundles") as batch_op:
        batch_op.alter_column(
            "diagnostic_run_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )
