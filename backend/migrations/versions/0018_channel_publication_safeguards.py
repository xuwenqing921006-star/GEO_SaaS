# ruff: noqa: RUF001

"""Strengthen channel-specific publishing safeguards.

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-29
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_TEXTS = {
    code: (
        f"将文章适配为{name}可读的结构。默认不主动写入手机号、微信号"
        "或二维码；发布前根据平台当前规则人工复核。"
    )
    for code, name in {
        "channel_sohu": "搜狐号",
        "channel_baijia": "百家号",
        "channel_toutiao": "头条号",
        "channel_wechat": "微信公众号",
        "channel_bilibili": "哔哩哔哩",
    }.items()
}

OLD_DESCRIPTIONS = {
    code: f"适配{name}可读结构，发布前人工复核联系方式与平台规则。"
    for code, name in {
        "channel_sohu": "搜狐号",
        "channel_baijia": "百家号",
        "channel_toutiao": "头条号",
        "channel_wechat": "微信公众号",
        "channel_bilibili": "哔哩哔哩",
    }.items()
}

NEW_RULES = {
    "channel_sohu": {
        "description": "避免地域搜索词式标题、营销软文、重复堆词和正文联系方式。",
        "text": (
            "改成搜狐号企业资讯或实用知识稿。标题不要使用“地域+服务+哪家好/怎么选”"
            "等搜索词式结构，不要堆叠地域词、品牌词或近义关键词。正文先提供独立的信息"
            "价值，再把企业作为一个已核验示例少量提及；不得写成推荐、报名、预约、咨询、"
            "售卖或营销软文。删除手机号、微信号、二维码、外链和其他导流表达。"
        ),
        "policy": "omit",
        "source_url": "https://www.sohu.com/a/22708302_119436",
    },
    "channel_baijia": {
        "description": "强调事实准确和题文一致，删除推广联系方式与站外导流。",
        "text": (
            "改成百家号可独立阅读的信息文章。标题与正文必须一致，不夸张、不虚构，"
            "不使用价格促销、排名或效果承诺。企业名称只在解释事实时出现，避免硬性推荐。"
            "删除手机号、微信号、二维码、公众号、第三方网址和引导联系表达。"
        ),
        "policy": "omit",
        "source_url": (
            "https://smartprogram.baidu.com/opensourcedocs/introduction/auditing_baijiahao/"
        ),
    },
    "channel_toutiao": {
        "description": "先提供用户价值，删除商业招揽、联系方式与联合推广式表达。",
        "text": (
            "改成头条号信息图文，开头直接说明读者能获得的判断方法。不得出现商业招揽、"
            "课程促销、报名承诺、联合推广或重复品牌曝光。删除电话、微信、QQ、群、"
            "公众号、二维码、站外链接和引导私下联系的表达。"
        ),
        "policy": "omit",
        "source_url": "https://www.toutiao.com/article/6186894733417054722/",
    },
    "channel_wechat": {
        "description": "适配公众号长文，发布前复核导流、外链和行业资质。",
        "text": (
            "改成公众号长文，增加简短导读、清晰段落和核验清单。避免诱导分享、"
            "夸张标题、虚假承诺和伪装系统按钮；联系方式和外链发布前按账号能力复核。"
        ),
        "policy": "manual_review",
        "source_url": None,
    },
    "channel_bilibili": {
        "description": "强调知识价值，避免广告、过度营销和无关导流。",
        "text": (
            "改成有实际知识价值的专栏或视频文稿，先解释方法、事实和限制，再少量说明"
            "企业示例。不要发布广告、过度营销、诱导点击或未经许可的互相推广；"
            "联系方式发布前人工复核。"
        ),
        "policy": "manual_review",
        "source_url": "https://link.bilibili.com/h5/im/im-specification",
    },
}


def upgrade() -> None:
    connection = op.get_bind()
    now = datetime.now(UTC)
    for code, rule in NEW_RULES.items():
        row = (
            connection.execute(
                sa.text(
                    "SELECT id, current_version, template_text, default_text "
                    "FROM prompt_templates WHERE code = :code",
                ),
                {"code": code},
            )
            .mappings()
            .one_or_none()
        )
        if row is None or (
            row["template_text"] != OLD_TEXTS[code] or row["default_text"] != OLD_TEXTS[code]
        ):
            continue
        version_number = int(row["current_version"]) + 1
        connection.execute(
            sa.text(
                "INSERT INTO prompt_template_versions "
                "(id, template_id, version_number, template_text, contact_policy, "
                "change_note, created_at) "
                "VALUES (:id, :template_id, :version_number, :template_text, "
                ":contact_policy, :change_note, :created_at)",
            ),
            {
                "id": uuid4(),
                "template_id": row["id"],
                "version_number": version_number,
                "template_text": rule["text"],
                "contact_policy": rule["policy"],
                "change_note": "T-029 平台发文规范与联系方式策略更新",
                "created_at": now,
            },
        )
        connection.execute(
            sa.text(
                "UPDATE prompt_templates SET description = :description, "
                "template_text = :template_text, default_text = :template_text, "
                "contact_policy = :contact_policy, "
                "default_contact_policy = :contact_policy, source_url = :source_url, "
                "verified_at = :verified_at, current_version = :current_version, "
                "version = version + 1, updated_at = :updated_at WHERE id = :id",
            ),
            {
                "id": row["id"],
                "description": rule["description"],
                "template_text": rule["text"],
                "contact_policy": rule["policy"],
                "source_url": rule["source_url"],
                "verified_at": date(2026, 7, 29),
                "current_version": version_number,
                "updated_at": now,
            },
        )


def downgrade() -> None:
    connection = op.get_bind()
    now = datetime.now(UTC)
    for code, rule in NEW_RULES.items():
        row = (
            connection.execute(
                sa.text(
                    "SELECT id, current_version, template_text FROM prompt_templates "
                    "WHERE code = :code",
                ),
                {"code": code},
            )
            .mappings()
            .one_or_none()
        )
        if row is None or row["template_text"] != rule["text"] or int(row["current_version"]) <= 1:
            continue
        rollback_version = int(row["current_version"]) + 1
        connection.execute(
            sa.text(
                "INSERT INTO prompt_template_versions "
                "(id, template_id, version_number, template_text, contact_policy, "
                "change_note, created_at) "
                "VALUES (:id, :template_id, :version_number, :template_text, "
                "'manual_review', :change_note, :created_at)",
            ),
            {
                "id": uuid4(),
                "template_id": row["id"],
                "version_number": rollback_version,
                "template_text": OLD_TEXTS[code],
                "change_note": "T-029 回滚至升级前渠道规则",
                "created_at": now,
            },
        )
        connection.execute(
            sa.text(
                "UPDATE prompt_templates SET description = :description, "
                "template_text = :template_text, "
                "default_text = :template_text, contact_policy = 'manual_review', "
                "default_contact_policy = 'manual_review', source_url = NULL, "
                "verified_at = NULL, current_version = :current_version, "
                "version = version + 1, updated_at = :updated_at WHERE id = :id",
            ),
            {
                "id": row["id"],
                "description": OLD_DESCRIPTIONS[code],
                "template_text": OLD_TEXTS[code],
                "current_version": rollback_version,
                "updated_at": now,
            },
        )
