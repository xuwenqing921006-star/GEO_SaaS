"""Freeze legacy channel rows and normalize the art industry code.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-28
"""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATALOG_VERSION = "2026.07.27-1"
VERIFIED_ON = "2026-07-27"


def _channel(
    channel_id: str,
    name: str,
    official_url: str,
    ownership: str,
    access: str,
    cost: str,
    ecosystem_tags: list[str],
    supported_content_types: list[str],
    client_requirements: list[str],
    risks: list[str],
    priority: str,
) -> dict[str, object]:
    return {
        "id": channel_id,
        "name": name,
        "official_url": official_url,
        "ownership": ownership,
        "access": access,
        "cost": cost,
        "ecosystem_tags": ecosystem_tags,
        "supported_content_types": supported_content_types,
        "client_requirements": client_requirements,
        "risks": risks,
        "verified_on": VERIFIED_ON,
        "priority": priority,
        "active": True,
    }


LEGACY_CHANNEL_SNAPSHOTS = {
    item["id"]: item
    for item in (
        _channel(
            "sohu",
            "搜狐号",
            "https://mp.sohu.com/",
            "operator_publishable",
            "public_web",
            "free",
            ["公开网页", "综合资讯"],
            ["企业事实", "服务指南", "常见问题"],
            ["授权可公开的企业资料"],
            ["发布后仍需逐篇核验公开访问状态"],
            "P0",
        ),
        _channel(
            "baijia",
            "百家号",
            "https://baijiahao.baidu.com/",
            "operator_publishable",
            "public_web",
            "free",
            ["百度搜索生态", "公开网页"],
            ["企业事实", "服务说明", "常见问题"],
            ["授权可公开的企业资料"],
            ["不得编造评价、榜单或效果承诺"],
            "P0",
        ),
        _channel(
            "toutiao",
            "头条号",
            "https://mp.toutiao.com/",
            "operator_publishable",
            "mixed",
            "free",
            ["字节内容生态", "图文与视频"],
            ["本地指南", "问答文章", "图文"],
            ["授权可公开的企业资料"],
            ["平台内分发与公开网页访问状态可能不同"],
            "P0",
        ),
        _channel(
            "zhihu",
            "知乎机构号",
            "https://www.zhihu.com/org/signup",
            "operator_publishable",
            "public_web",
            "free",
            ["问答内容", "公开网页"],
            ["选择指南", "专业问答", "避坑说明"],
            ["机构资料授权", "遵守机构号认证要求"],
            ["内容应直接回答问题，避免广告式堆砌"],
            "P0",
        ),
        _channel(
            "wechat",
            "微信公众号",
            "https://mp.weixin.qq.com/",
            "operator_publishable",
            "mixed",
            "free",
            ["微信内容生态", "长图文"],
            ["企业介绍", "服务指南", "案例说明"],
            ["授权可公开的企业资料"],
            ["搜索与外部抓取可见性需发布后单独核验"],
            "P1",
        ),
        _channel(
            "bilibili",
            "哔哩哔哩",
            "https://member.bilibili.com/creator/home",
            "operator_publishable",
            "mixed",
            "free",
            ["视频生态", "知识内容"],
            ["讲解视频", "案例展示", "知识科普"],
            ["视频或图文素材使用授权"],
            ["需要把长文改编为视频脚本或专栏格式"],
            "P1",
        ),
        _channel(
            "xiaohongshu",
            "小红书",
            "https://creator.xiaohongshu.com/",
            "operator_publishable",
            "mostly_in_app",
            "free",
            ["生活决策", "图文与短视频"],
            ["本地攻略", "场景问答", "图文笔记"],
            ["图片或视频素材使用授权"],
            ["以平台内访问为主，不能等同于公开网页收录"],
            "P1",
        ),
        _channel(
            "douyin",
            "抖音",
            "https://creator.douyin.com/",
            "operator_publishable",
            "mostly_in_app",
            "free",
            ["字节内容生态", "短视频"],
            ["口播脚本", "场景解答", "案例视频"],
            ["视频素材与出镜授权"],
            ["以平台内访问为主，需制作适合短视频的信息表达"],
            "P1",
        ),
        _channel(
            "baidu_maps",
            "百度地图商户",
            "https://map.baidu.com/",
            "client_required",
            "public_web",
            "optional_paid",
            ["本地实体", "百度生态"],
            ["地址", "营业信息", "服务范围"],
            ["客户主体认证", "地址、电话与营业信息核验"],
            ["主体资料和门店信息变更需客户配合"],
            "P0",
        ),
        _channel(
            "amap",
            "高德地图商户",
            "https://ditu.amap.com/",
            "client_required",
            "public_web",
            "optional_paid",
            ["本地实体", "地图生态"],
            ["地址", "营业信息", "服务范围"],
            ["客户主体认证", "地址、电话与营业信息核验"],
            ["主体资料和门店信息变更需客户配合"],
            "P1",
        ),
        _channel(
            "baidu_marketing",
            "百度营销",
            "https://e.baidu.com/",
            "partner_cooperation",
            "mixed",
            "paid",
            ["百度生态", "正式广告"],
            ["品牌说明", "服务落地页", "本地推广"],
            ["客户主体资质", "预算与广告授权"],
            ["属于付费推广，不等同于自然收录或模型推荐"],
            "P2",
        ),
        _channel(
            "oceanengine",
            "巨量引擎",
            "https://www.oceanengine.com/",
            "partner_cooperation",
            "mixed",
            "paid",
            ["字节商业生态", "正式广告"],
            ["品牌说明", "短视频广告", "本地推广"],
            ["客户主体资质", "预算与广告授权"],
            ["属于付费推广，不等同于自然收录或模型推荐"],
            "P2",
        ),
    )
}


def upgrade() -> None:
    bind = op.get_bind()
    recommendations = sa.table(
        "channel_recommendations",
        sa.column("id", sa.Uuid()),
        sa.column("channel_id", sa.String()),
        sa.column("catalog_version", sa.String()),
        sa.column("source_brief_ids", sa.JSON()),
        sa.column("channel_snapshot", sa.JSON()),
        sa.column("brief_snapshot", sa.JSON()),
    )
    briefs = sa.table(
        "content_briefs",
        sa.column("id", sa.Uuid()),
        sa.column("title", sa.String()),
        sa.column("content_type", sa.String()),
        sa.column("target_keywords", sa.JSON()),
        sa.column("angle", sa.Text()),
        sa.column("version", sa.Integer()),
    )
    rows = bind.execute(
        sa.select(
            recommendations.c.id,
            recommendations.c.channel_id,
            recommendations.c.catalog_version,
            recommendations.c.source_brief_ids,
            recommendations.c.channel_snapshot,
            recommendations.c.brief_snapshot,
        ),
    ).mappings()
    for row in rows:
        values: dict[str, object] = {}
        if not row["channel_snapshot"]:
            snapshot = LEGACY_CHANNEL_SNAPSHOTS.get(row["channel_id"])
            if snapshot is None:
                snapshot = {
                    "id": row["channel_id"],
                    "name": row["channel_id"],
                    "official_url": "",
                    "ownership": "operator_publishable",
                    "access": "mixed",
                    "cost": "free",
                    "ecosystem_tags": ["历史目录"],
                    "supported_content_types": [],
                    "client_requirements": [],
                    "risks": ["历史渠道已不在当前目录，请人工核验"],
                    "verified_on": VERIFIED_ON,
                    "priority": "P2",
                    "active": False,
                }
            values["channel_snapshot"] = snapshot
        if not row["brief_snapshot"]:
            source_ids = row["source_brief_ids"] or []
            brief = None
            if source_ids:
                try:
                    brief_id = UUID(str(source_ids[0]))
                except ValueError:
                    brief_id = None
                if brief_id is not None:
                    brief = (
                        bind.execute(
                            sa.select(
                                briefs.c.id,
                                briefs.c.title,
                                briefs.c.content_type,
                                briefs.c.target_keywords,
                                briefs.c.angle,
                                briefs.c.version,
                            ).where(briefs.c.id == brief_id),
                        )
                        .mappings()
                        .first()
                    )
            values["brief_snapshot"] = (
                {
                    "id": str(brief["id"]),
                    "title": brief["title"],
                    "content_type": brief["content_type"],
                    "target_keywords": brief["target_keywords"] or [],
                    "angle": brief["angle"],
                    "version": brief["version"],
                }
                if brief is not None
                else {
                    "id": None,
                    "title": "历史内容简报",
                    "content_type": None,
                    "target_keywords": [],
                    "angle": "",
                    "version": None,
                }
            )
        if not row["catalog_version"]:
            values["catalog_version"] = CATALOG_VERSION
        if values:
            bind.execute(
                recommendations.update().where(recommendations.c.id == row["id"]).values(**values),
            )
    bind.execute(
        sa.text(
            """
            UPDATE clients
            SET industry_code = 'art_education',
                industry_name = '少儿美术'
            WHERE industry_code = 'art_training'
            """,
        ),
    )


def downgrade() -> None:
    # Frozen historical payloads remain valid on 0010 and should not be erased.
    pass
