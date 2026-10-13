"""Add evidence-bound content pipeline.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fact_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("brief_id", sa.Uuid(), nullable=False),
        sa.Column("brief_version", sa.Integer(), nullable=False),
        sa.Column("facts", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("brief_context", sa.JSON(), nullable=False),
        sa.Column("prohibited_claims", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["brief_id"], ["content_briefs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fact_snapshots_client_id", "fact_snapshots", ["client_id"])
    op.create_index("ix_fact_snapshots_brief_id", "fact_snapshots", ["brief_id"])
    op.add_column(
        "model_usage",
        sa.Column("fact_snapshot_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "model_usage",
        sa.Column("prompt_version", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "model_usage",
        sa.Column("pricing_version", sa.String(length=50), nullable=True),
    )
    op.create_index(
        "ix_model_usage_fact_snapshot_id",
        "model_usage",
        ["fact_snapshot_id"],
    )

    op.create_table(
        "content_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("brief_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["brief_id"], ["content_briefs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id", "brief_id", name="uq_content_documents_brief"),
    )
    op.create_index("ix_content_documents_client_id", "content_documents", ["client_id"])
    op.create_index("ix_content_documents_brief_id", "content_documents", ["brief_id"])
    op.create_index("ix_content_documents_status", "content_documents", ["status"])

    op.create_table(
        "content_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        sa.Column("outline_markdown", sa.Text(), nullable=True),
        sa.Column("change_type", sa.String(length=30), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("fact_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column("output_hash", sa.String(length=64), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("fallback_reason", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["content_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["fact_snapshot_id"], ["fact_snapshots.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_content_versions_document_number",
        ),
    )
    op.create_index("ix_content_versions_document_id", "content_versions", ["document_id"])
    op.create_index(
        "ix_content_versions_fact_snapshot_id",
        "content_versions",
        ["fact_snapshot_id"],
    )

    op.create_table(
        "content_quality_checks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("overall_status", sa.String(length=20), nullable=False),
        sa.Column("dimensions", sa.JSON(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["content_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_content_quality_checks_document_version_id",
        "content_quality_checks",
        ["document_version_id"],
    )
    op.create_index(
        "ix_content_quality_checks_overall_status",
        "content_quality_checks",
        ["overall_status"],
    )

    op.create_table(
        "content_channel_variants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("channel_id", sa.String(length=100), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("adaptation_note", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["content_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["content_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "channel_id",
            name="uq_content_channel_variants_document_channel",
        ),
    )
    op.create_index(
        "ix_content_channel_variants_document_id",
        "content_channel_variants",
        ["document_id"],
    )
    op.create_index(
        "ix_content_channel_variants_version_id",
        "content_channel_variants",
        ["version_id"],
    )

    op.create_table(
        "content_exports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("content_version_id", sa.Uuid(), nullable=False),
        sa.Column("format", sa.String(length=20), nullable=False),
        sa.Column("include_sources", sa.Boolean(), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["content_version_id"], ["content_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["document_id"], ["content_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_content_exports_document_id", "content_exports", ["document_id"])
    op.create_index(
        "ix_content_exports_content_version_id",
        "content_exports",
        ["content_version_id"],
    )
    op.create_index("ix_content_exports_status", "content_exports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_content_exports_status", table_name="content_exports")
    op.drop_index("ix_content_exports_content_version_id", table_name="content_exports")
    op.drop_index("ix_content_exports_document_id", table_name="content_exports")
    op.drop_table("content_exports")
    op.drop_index(
        "ix_content_channel_variants_version_id",
        table_name="content_channel_variants",
    )
    op.drop_index(
        "ix_content_channel_variants_document_id",
        table_name="content_channel_variants",
    )
    op.drop_table("content_channel_variants")
    op.drop_index(
        "ix_content_quality_checks_overall_status",
        table_name="content_quality_checks",
    )
    op.drop_index(
        "ix_content_quality_checks_document_version_id",
        table_name="content_quality_checks",
    )
    op.drop_table("content_quality_checks")
    op.drop_index("ix_content_versions_fact_snapshot_id", table_name="content_versions")
    op.drop_index("ix_content_versions_document_id", table_name="content_versions")
    op.drop_table("content_versions")
    op.drop_index("ix_content_documents_status", table_name="content_documents")
    op.drop_index("ix_content_documents_brief_id", table_name="content_documents")
    op.drop_index("ix_content_documents_client_id", table_name="content_documents")
    op.drop_table("content_documents")
    op.drop_index("ix_fact_snapshots_brief_id", table_name="fact_snapshots")
    op.drop_index("ix_fact_snapshots_client_id", table_name="fact_snapshots")
    op.drop_index("ix_model_usage_fact_snapshot_id", table_name="model_usage")
    op.drop_column("model_usage", "prompt_version")
    op.drop_column("model_usage", "pricing_version")
    op.drop_column("model_usage", "fact_snapshot_id")
    op.drop_table("fact_snapshots")
