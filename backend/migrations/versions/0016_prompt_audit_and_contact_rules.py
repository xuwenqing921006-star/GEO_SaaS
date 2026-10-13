# ruff: noqa: RUF001

"""Complete prompt audit snapshots and channel contact safeguards.

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-29
"""

import re
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CONTENT_FORM_BY_KEYWORD_TYPE = {
    "local_service": "local_presence",
    "brand": "entity_profile",
    "recommendation": "local_recommendation",
    "scenario": "scenario_solution",
    "service_detail": "service_explainer",
    "comparison": "comparison",
    "transaction": "price_guide",
    "trust": "entity_profile",
}


def _fact_value(connection: Connection, client_id: object, key: str) -> str:
    value = connection.execute(
        sa.text(
            "SELECT value FROM facts "
            "WHERE client_id = :client_id AND key = :key "
            "AND status IN ('confirmed', 'client_provided', 'external_source', 'inferred') "
            "ORDER BY updated_at DESC LIMIT 1",
        ),
        {"client_id": client_id, "key": key},
    ).scalar_one_or_none()
    return str(value or "").strip()


def _missing_keyword_payload(
    keyword_type: str,
    *,
    brand: str,
    district: str,
    service: str,
) -> tuple[str, str, str, int]:
    values = {
        "local_service": (
            f"{district}{service}",
            f"{district}{service}机构有哪些",
            "寻找本地服务机构",
            1,
        ),
        "brand": (
            brand,
            f"{brand}的企业信息和主营业务是什么",
            "核验企业身份与主营业务",
            1,
        ),
        "recommendation": (
            f"{district}{service}",
            f"{district}{service}请推荐一家时应先核实什么",
            "获得有依据的推荐候选",
            1,
        ),
        "scenario": (
            service,
            f"哪些需求适合咨询{district}{service}",
            "按实际需求匹配服务",
            2,
        ),
        "service_detail": (
            service,
            f"{district}{service}通常包括哪些服务内容",
            "了解具体服务内容",
            2,
        ),
        "comparison": (
            f"{district}{service}",
            f"比较{district}{service}机构要看哪些信息",
            "比较机构公开信息",
            2,
        ),
        "transaction": (
            f"{district}{service}",
            f"{district}{service}费用和咨询流程怎么了解",
            "了解费用构成与咨询流程",
            2,
        ),
        "trust": (
            brand,
            f"{brand}的企业信息和服务范围怎么核实",
            "核验企业身份与服务范围",
            2,
        ),
    }
    return values[keyword_type]


def _primary_service(value: str) -> str:
    compact = re.sub(r"\s+", "", value)
    primary = re.split(r"[、,，;；]", compact, maxsplit=1)[0].strip()
    if "：" in primary:
        category, detail = primary.split("：", 1)
        if detail and len(detail) <= 12:
            return detail
        return f"{category}服务"
    if ":" in primary:
        category, detail = primary.split(":", 1)
        if detail and len(detail) <= 12:
            return detail
        return f"{category}服务"
    return primary[:24] or "主营服务"


def upgrade() -> None:
    op.add_column(
        "prompt_templates",
        sa.Column("default_contact_policy", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "strategy_bundles",
        sa.Column("prompt_template_code", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "strategy_bundles",
        sa.Column("prompt_template_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "content_briefs",
        sa.Column("prompt_layers_snapshot", sa.JSON(), nullable=True),
    )
    op.add_column(
        "content_briefs",
        sa.Column("contact_allowed_urls", sa.JSON(), nullable=True),
    )
    op.add_column(
        "content_versions",
        sa.Column("prompt_layers_snapshot", sa.JSON(), nullable=True),
    )
    op.add_column(
        "content_versions",
        sa.Column("contact_allowed_urls", sa.JSON(), nullable=True),
    )
    op.add_column(
        "content_versions",
        sa.Column("contact_sanitization_report", sa.JSON(), nullable=True),
    )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE prompt_templates "
            "SET default_contact_policy = contact_policy "
            "WHERE default_contact_policy IS NULL",
        ),
    )
    for keyword_type, content_form in CONTENT_FORM_BY_KEYWORD_TYPE.items():
        connection.execute(
            sa.text(
                "UPDATE strategy_items "
                "SET recommended_content_type = :content_form "
                "WHERE kind = 'keyword' AND keyword_type = :keyword_type "
                "AND recommended_content_type IS NULL",
            ),
            {"content_form": content_form, "keyword_type": keyword_type},
        )

    bundles = (
        connection.execute(
            sa.text(
                "SELECT b.id, b.client_id, c.standard_name "
                "FROM strategy_bundles b JOIN clients c ON c.id = b.client_id",
            ),
        )
        .mappings()
        .all()
    )
    now = datetime.now(UTC)
    for bundle in bundles:
        existing_types = {
            str(row[0])
            for row in connection.execute(
                sa.text(
                    "SELECT DISTINCT keyword_type FROM strategy_items "
                    "WHERE bundle_id = :bundle_id AND kind = 'keyword' "
                    "AND active = true AND keyword_type IS NOT NULL",
                ),
                {"bundle_id": bundle["id"]},
            )
        }
        district = _fact_value(connection, bundle["client_id"], "location.service_area") or "本地"
        service = _primary_service(
            _fact_value(connection, bundle["client_id"], "service.promotion_focus")
            or _fact_value(connection, bundle["client_id"], "service.primary")
            or "主营服务",
        )
        brand = str(bundle["standard_name"])
        for keyword_type in CONTENT_FORM_BY_KEYWORD_TYPE.keys() - existing_types:
            main_keyword, text, intent, priority = _missing_keyword_payload(
                keyword_type,
                brand=brand,
                district=district,
                service=service,
            )
            connection.execute(
                sa.text(
                    "INSERT INTO strategy_items "
                    "(id, bundle_id, client_id, kind, text, family, keyword_type, "
                    "provenance, target_level, priority, rationale, main_keyword, "
                    "user_intent, recommended_content_type, locked, selected, active, version) "
                    "VALUES (:id, :bundle_id, :client_id, 'keyword', :text, NULL, "
                    ":keyword_type, 'system_migration_t027', :target_level, :priority, "
                    ":rationale, :main_keyword, :user_intent, :content_form, "
                    "false, false, true, 1)",
                ),
                {
                    "id": uuid4(),
                    "bundle_id": bundle["id"],
                    "client_id": bundle["client_id"],
                    "text": text,
                    "keyword_type": keyword_type,
                    "target_level": (
                        "L3"
                        if keyword_type == "recommendation"
                        else "L2"
                        if keyword_type in {"brand", "trust"}
                        else "L1"
                    ),
                    "priority": priority,
                    "rationale": (
                        f"系统按当前企业事实补齐“{keyword_type}”意图覆盖；"
                        f"迁移时间 {now.isoformat()}，不代表搜索热度或平台排名。"
                    ),
                    "main_keyword": main_keyword,
                    "user_intent": intent,
                    "content_form": CONTENT_FORM_BY_KEYWORD_TYPE[keyword_type],
                },
            )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "DELETE FROM strategy_items WHERE provenance = 'system_migration_t027'",
        ),
    )
    op.drop_column("content_versions", "contact_sanitization_report")
    op.drop_column("content_versions", "contact_allowed_urls")
    op.drop_column("content_versions", "prompt_layers_snapshot")
    op.drop_column("content_briefs", "contact_allowed_urls")
    op.drop_column("content_briefs", "prompt_layers_snapshot")
    op.drop_column("strategy_bundles", "prompt_template_version")
    op.drop_column("strategy_bundles", "prompt_template_code")
    op.drop_column("prompt_templates", "default_contact_policy")
