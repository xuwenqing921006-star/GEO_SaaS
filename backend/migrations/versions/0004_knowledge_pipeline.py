"""Add protected knowledge and job pipeline.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "materials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "client_id",
            sa.Uuid(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(150), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False, unique=True),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("authorization_status", sa.String(30), nullable=False),
        sa.Column("extraction_status", sa.String(30), nullable=False),
        sa.Column("extraction_error", sa.String(500)),
        sa.Column("page_count", sa.Integer()),
        sa.Column("fragment_count", sa.Integer(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.create_index("ix_materials_client_id", "materials", ["client_id"])
    op.create_index("ix_materials_category", "materials", ["category"])
    op.create_index("ix_materials_extraction_status", "materials", ["extraction_status"])

    op.create_table(
        "material_fragments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "material_id",
            sa.Uuid(),
            sa.ForeignKey("materials.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page", sa.Integer()),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("extraction_method", sa.String(20), nullable=False),
        sa.Column("sensitivity_tags", sa.JSON(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_material_fragments_material_id",
        "material_fragments",
        ["material_id"],
    )

    op.create_table(
        "facts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "client_id",
            sa.Uuid(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("key", sa.String(150), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.Date()),
        sa.Column("valid_until", sa.Date()),
        sa.Column("confirmation_note", sa.String(1000)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("client_id", "key", name="uq_facts_client_key"),
    )
    op.create_index("ix_facts_client_id", "facts", ["client_id"])
    op.create_index("ix_facts_category", "facts", ["category"])
    op.create_index("ix_facts_status", "facts", ["status"])

    op.create_table(
        "evidence",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "client_id",
            sa.Uuid(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "material_id",
            sa.Uuid(),
            sa.ForeignKey("materials.id", ondelete="SET NULL"),
        ),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("source_label", sa.String(200), nullable=False),
        sa.Column("source_url", sa.String(2000)),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.Date(), nullable=False),
        sa.Column("authorization_status", sa.String(30), nullable=False),
    )
    op.create_index("ix_evidence_client_id", "evidence", ["client_id"])
    op.create_index("ix_evidence_material_id", "evidence", ["material_id"])

    op.create_table(
        "fact_evidence",
        sa.Column(
            "fact_id",
            sa.Uuid(),
            sa.ForeignKey("facts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "evidence_id",
            sa.Uuid(),
            sa.ForeignKey("evidence.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "fact_conflicts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "client_id",
            sa.Uuid(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fact_key", sa.String(150), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("candidates", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("resolved_value", sa.Text()),
        sa.Column("resolution_note", sa.String(1000)),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.create_index("ix_fact_conflicts_client_id", "fact_conflicts", ["client_id"])
    op.create_index("ix_fact_conflicts_status", "fact_conflicts", ["status"])

    op.create_table(
        "knowledge_profiles",
        sa.Column(
            "client_id",
            sa.Uuid(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("services", sa.JSON(), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("prohibited_claims", sa.JSON(), nullable=False),
        sa.Column("external_presences", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "client_id",
            sa.Uuid(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "material_id",
            sa.Uuid(),
            sa.ForeignKey("materials.id", ondelete="CASCADE"),
        ),
        sa.Column("job_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "client_id",
            "job_type",
            "idempotency_key",
            name="uq_jobs_client_type_idempotency",
        ),
    )
    op.create_index("ix_jobs_client_id", "jobs", ["client_id"])
    op.create_index("ix_jobs_material_id", "jobs", ["material_id"])
    op.create_index("ix_jobs_job_type", "jobs", ["job_type"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index(
        "uq_jobs_active_material_extract",
        "jobs",
        ["material_id"],
        unique=True,
        postgresql_where=sa.text(
            "material_id IS NOT NULL AND job_type = 'material_extract' "
            "AND status IN ('queued', 'running')",
        ),
    )


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("knowledge_profiles")
    op.drop_table("fact_conflicts")
    op.drop_table("fact_evidence")
    op.drop_table("evidence")
    op.drop_table("facts")
    op.drop_table("material_fragments")
    op.drop_table("materials")
