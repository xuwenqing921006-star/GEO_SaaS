"""Add versioned prompt templates and generation metadata.

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("template_text", sa.Text(), nullable=False),
        sa.Column("default_text", sa.Text(), nullable=False),
        sa.Column("editable", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("variable_keys", sa.JSON(), nullable=False),
        sa.Column("required_fact_keys", sa.JSON(), nullable=False),
        sa.Column("contact_policy", sa.String(length=30), nullable=True),
        sa.Column("channel_id", sa.String(length=80), nullable=True),
        sa.Column("source_url", sa.String(length=2000), nullable=True),
        sa.Column("verified_at", sa.Date(), nullable=True),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_prompt_templates_code"),
    )
    op.create_index(
        "ix_prompt_templates_code",
        "prompt_templates",
        ["code"],
        unique=True,
    )
    op.create_index(
        "ix_prompt_templates_category",
        "prompt_templates",
        ["category"],
    )
    op.create_index(
        "ix_prompt_templates_active",
        "prompt_templates",
        ["active"],
    )
    op.create_index(
        "ix_prompt_templates_contact_policy",
        "prompt_templates",
        ["contact_policy"],
    )
    op.create_index(
        "ix_prompt_templates_channel_id",
        "prompt_templates",
        ["channel_id"],
    )

    op.create_table(
        "prompt_template_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("template_text", sa.Text(), nullable=False),
        sa.Column("contact_policy", sa.String(length=30), nullable=True),
        sa.Column("change_note", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["prompt_templates.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "template_id",
            "version_number",
            name="uq_prompt_template_versions_number",
        ),
    )
    op.create_index(
        "ix_prompt_template_versions_template_id",
        "prompt_template_versions",
        ["template_id"],
    )

    op.add_column(
        "strategy_items",
        sa.Column("recommended_content_type", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "content_briefs",
        sa.Column("prompt_template_code", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "content_briefs",
        sa.Column("prompt_template_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "content_briefs",
        sa.Column("target_channel_id", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "content_briefs",
        sa.Column("contact_policy", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "content_versions",
        sa.Column("prompt_template_code", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "content_versions",
        sa.Column("prompt_template_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "content_versions",
        sa.Column("target_channel_id", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "content_versions",
        sa.Column("contact_policy", sa.String(length=30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("content_versions", "contact_policy")
    op.drop_column("content_versions", "target_channel_id")
    op.drop_column("content_versions", "prompt_template_version")
    op.drop_column("content_versions", "prompt_template_code")
    op.drop_column("content_briefs", "contact_policy")
    op.drop_column("content_briefs", "target_channel_id")
    op.drop_column("content_briefs", "prompt_template_version")
    op.drop_column("content_briefs", "prompt_template_code")
    op.drop_column("strategy_items", "recommended_content_type")
    op.drop_index(
        "ix_prompt_template_versions_template_id",
        table_name="prompt_template_versions",
    )
    op.drop_table("prompt_template_versions")
    op.drop_index("ix_prompt_templates_channel_id", table_name="prompt_templates")
    op.drop_index("ix_prompt_templates_contact_policy", table_name="prompt_templates")
    op.drop_index("ix_prompt_templates_active", table_name="prompt_templates")
    op.drop_index("ix_prompt_templates_category", table_name="prompt_templates")
    op.drop_index("ix_prompt_templates_code", table_name="prompt_templates")
    op.drop_table("prompt_templates")
