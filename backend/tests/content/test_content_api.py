# ruff: noqa: RUF001

import asyncio
import base64
import json
import os
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image
from pydantic import SecretStr
from sqlalchemy import select, update

import app.content as content_module
from app.config import Settings
from app.content import PRICING_VERSION, process_content_job
from app.database import (
    ContentBrief,
    ContentDocument,
    ContentQualityCheck,
    Job,
    ModelUsage,
    ProviderSetting,
)
from app.jobs import claim_next_job, process_one_job
from app.providers import ProviderClient, SecretCipher
from app.responses import ApiFailure
from tests.auth.test_auth_api import build_client
from tests.clients.test_clients_api import login
from tests.diagnostics.test_diagnostics_api import (
    create_customer,
    seed_required_facts,
)
from tests.strategy.test_strategy_api import create_diagnostic, generate_strategy


@pytest.mark.unit
def test_batch_input_supports_multiple_target_channels_and_legacy_single_value() -> None:
    keyword_id = uuid4()
    multiple = content_module.BatchCreateDocumentsInput(
        keyword_ids=[keyword_id],
        article_count=2,
        target_channel_ids=["toutiao", "sohu", "toutiao"],
    )
    legacy = content_module.BatchCreateDocumentsInput(
        keyword_ids=[keyword_id],
        article_count=1,
        target_channel_id="toutiao",
    )

    assert multiple.target_channel_ids == ["toutiao", "sohu"]
    assert legacy.target_channel_ids == ["toutiao"]


@pytest.mark.unit
def test_content_v2_writer_context_hides_internal_ids() -> None:
    brief = SimpleNamespace(
        title="即墨区少儿美术培训哪家好",
        content_type="selection_guide",
        target_keywords=["即墨区少儿美术培训", "即墨区少儿美术培训哪家好"],
        retest_questions=["即墨区少儿美术培训哪家好"],
        target_level="L1",
        audience="本地家长",
        angle="先给选择标准，再说明已确认信息",
        expected_recommendation_reason="只说明适用条件",
    )
    snapshot = SimpleNamespace(
        facts=[
            {
                "id": "client:c05353e3-9698-4ef7-87f1-58d89fbbf5fe",
                "key": "standard_name",
                "label": "企业标准名称",
                "value": "青岛莱恩美术教育",
                "category": "identity",
                "version": 1,
            },
            {
                "id": "3d924773-1c94-41da-bcae-07551ba7f069",
                "key": "location.administrative_area",
                "label": "所在地区",
                "value": "山东省青岛市即墨区",
                "category": "location",
                "version": 1,
            },
        ],
        evidence=[
            {
                "id": "5ace8ab1-1111-4111-8111-111111111111",
                "fact_id": "3d924773-1c94-41da-bcae-07551ba7f069",
                "source_type": "upload",
                "source_label": "客户资料采集表",
                "source_url": None,
                "quote": "山东省青岛市即墨区",
                "observed_at": "2026-07-28",
            },
        ],
        prohibited_claims=["全市第一"],
    )

    context = content_module._writer_model_context(brief, snapshot)

    assert "客户资料采集表" in context
    assert "青岛莱恩美术教育" in context
    assert "client:" not in context
    assert "c05353e3-9698-4ef7-87f1-58d89fbbf5fe" not in context
    assert "3d924773-1c94-41da-bcae-07551ba7f069" not in context
    assert '"fact_id"' not in context
    assert '"id"' not in context


@pytest.mark.unit
def test_review_context_does_not_expose_internal_ids_to_the_reviewer() -> None:
    brief = SimpleNamespace(
        title="即墨少儿美术培训机构怎么选",
        content_type="selection_guide",
        target_keywords=["即墨少儿美术培训机构"],
        retest_questions=["即墨少儿美术培训机构怎么选"],
        target_level="L1",
        audience="本地家长",
        angle="客观选择",
        expected_recommendation_reason="真实信息",
    )
    snapshot = SimpleNamespace(
        facts=[
            {
                "id": "client:c05353e3-9698-4ef7-87f1-58d89fbbf5fe",
                "key": "identity.standard_name",
                "label": "企业标准名称",
                "value": "青岛莱恩美术教育",
                "category": "identity",
            },
        ],
        evidence=[
            {
                "id": "5ace8ab1-1111-4111-8111-111111111111",
                "fact_id": "3d924773-1c94-41da-bcae-07551ba7f069",
                "source_label": "客户资料采集表",
                "source_url": None,
                "quote": "青岛莱恩美术教育",
                "observed_at": "2026-07-28",
            },
        ],
        prohibited_claims=["全市第一"],
    )

    context = content_module._model_context(brief, snapshot)

    assert "青岛莱恩美术教育" in context
    assert "客户资料采集表" in context
    assert "c05353e3-9698-4ef7-87f1-58d89fbbf5fe" not in context
    assert "5ace8ab1-1111-4111-8111-111111111111" not in context
    assert "3d924773-1c94-41da-bcae-07551ba7f069" not in context
    assert '"fact_id"' not in context


@pytest.mark.unit
def test_writer_context_filters_risky_marketing_and_uses_conservative_age() -> None:
    brief = SimpleNamespace(
        title="即墨少儿美术培训机构怎么选",
        content_type="selection_guide",
        target_keywords=["即墨少儿美术培训机构"],
        retest_questions=["即墨少儿美术培训机构怎么选"],
        target_level="L1",
        audience="本地家长",
        angle="客观选择",
        expected_recommendation_reason="真实信息",
    )
    snapshot = SimpleNamespace(
        facts=[
            {
                "key": "capability.primary",
                "label": "企业优势",
                "value": (
                    "专注4-16岁少儿美术教育，历经6年时间，累计服务3000余人。"
                    "率先提出教学理念，采用全新模式，以达到最佳学习效果，"
                    "打造全市最专业的平台。自主研发多本美术教材。"
                ),
                "category": "capability",
            },
            {
                "key": "audience.primary",
                "label": "主要服务对象",
                "value": "适合4-18岁少儿美术书法培训，中高考美术培训",
                "category": "audience",
            },
            {
                "key": "identity.founded_at",
                "label": "成立时间",
                "value": "2017",
                "category": "identity",
            },
        ],
        evidence=[],
        prohibited_claims=["全市第一", "最好"],
    )

    context = content_module._writer_model_context(brief, snapshot)

    assert "4-16岁" in context
    assert "4-18岁" not in context
    assert "中高考美术培训" in context
    assert "自主研发多本美术教材" in context
    assert '"value":"2017"' in context
    assert "历经6年" not in context
    assert "累计服务3000余人" not in context
    assert "率先" not in context
    assert "最佳" not in context
    assert "最专业" not in context
    assert "更保守的4-16岁" in context


@pytest.mark.unit
def test_review_context_uses_same_safe_facts_as_writer() -> None:
    brief = SimpleNamespace(
        title="即墨少儿美术培训机构怎么选",
        content_type="selection_guide",
        target_keywords=["即墨少儿美术培训机构"],
        retest_questions=["即墨少儿美术培训机构怎么选"],
        target_level="L1",
        audience="本地家长",
        angle="客观选择",
        expected_recommendation_reason="真实信息",
    )
    snapshot = SimpleNamespace(
        facts=[
            {
                "key": "capability.primary",
                "label": "企业优势",
                "value": "专注4-16岁少儿美术教育，打造全市最专业的平台",
                "category": "capability",
            },
            {
                "key": "audience.primary",
                "label": "主要服务对象",
                "value": "适合4-18岁少儿美术书法培训，中高考美术培训",
                "category": "audience",
            },
        ],
        evidence=[
            {
                "source_label": "客户资料采集表",
                "quote": "全市最专业",
            },
        ],
        prohibited_claims=["全市第一"],
    )

    context = content_module._model_context(brief, snapshot)

    assert "4-16岁" in context
    assert "4-18岁" not in context
    assert "中高考美术培训" in context
    assert "全市最专业" not in context
    assert '"quote"' not in context
    assert "更保守的4-16岁" in context


@pytest.mark.unit
def test_founded_year_fact_supports_natural_year_expression() -> None:
    support = content_module._fact_support_values(
        [
            {
                "key": "identity.founded_at",
                "label": "成立时间",
                "value": "2017",
            },
        ],
    )

    assert "成立于2017年" in support
    assert content_module._pattern_claim_is_supported("成立于2017年", support)


@pytest.mark.unit
def test_regeneration_prompt_uses_quality_findings_without_old_body() -> None:
    brief = SimpleNamespace(
        title="即墨少儿美术培训机构怎么选",
        content_type="selection_guide",
        target_keywords=["即墨少儿美术培训机构"],
        retest_questions=["即墨少儿美术培训机构怎么选"],
        target_level="L1",
        audience="本地家长",
        angle="客观选择",
        expected_recommendation_reason="真实信息",
    )
    snapshot = SimpleNamespace(
        facts=[
            {
                "key": "identity.standard_name",
                "label": "企业标准名称",
                "value": "青岛莱恩美术教育",
                "category": "identity",
            },
        ],
        evidence=[],
        prohibited_claims=[],
    )
    check = cast(
        ContentQualityCheck,
        SimpleNamespace(
            findings=[
                {
                    "severity": "blocking",
                    "category": "natural_language",
                    "message": "旧稿模板化。",
                    "suggested_fix": "更换结构并减少品牌重复。",
                    "fact_id": "internal-id-must-not-appear",
                },
            ],
        ),
    )

    prompt = content_module._regeneration_user_prompt(
        brief,
        snapshot,
        contact_policy="omit",
        revision_instruction="从零重写",
        source_title="旧标题",
        target_channel_id="sohu",
        source_check=check,
    )

    assert "旧稿模板化" in prompt
    assert "更换结构并减少品牌重复" in prompt
    assert "旧正文故意未提供" in prompt
    assert "internal-id-must-not-appear" not in prompt
    assert "目标渠道：sohu" in prompt


@pytest.mark.unit
def test_regeneration_system_prompt_declares_operator_instruction_priority() -> None:
    prompt = content_module._regeneration_system_prompt("选择指南模板")

    assert "运营修改建议的优先级高于内容模板" in prompt
    assert "修改建议要求避免编号式结构" in prompt
    assert prompt.endswith("选择指南模板")


@pytest.mark.unit
def test_prompt_variables_only_render_safe_publishable_facts() -> None:
    brief = SimpleNamespace(
        title="即墨少儿美术培训怎么选",
        content_type="selection_guide",
        target_keywords=["即墨少儿美术培训"],
        retest_questions=["即墨少儿美术培训怎么选"],
        keyword_type="地区主营",
        angle="用户意图：选择判断；差异化角度：实地核验",
        target_channel_id="sohu",
    )
    snapshot = SimpleNamespace(
        facts=[
            {
                "key": "identity.standard_name",
                "label": "企业标准名称",
                "value": "青岛莱恩美术教育",
                "category": "identity",
            },
            {
                "key": "location.service_area",
                "label": "服务区域",
                "value": "即墨区",
                "category": "location",
            },
            {
                "key": "service.primary",
                "label": "核心服务",
                "value": "少儿美术培训",
                "category": "service",
            },
            {
                "key": "capability.summary",
                "label": "企业优势",
                "value": "累计服务3000人，专利局审核通过，课程设置清晰",
                "category": "capability",
            },
            {
                "key": "contact.phone",
                "label": "联系电话",
                "value": "13800138000",
                "category": "contact",
            },
        ],
        evidence=[],
        prohibited_claims=[],
    )

    rendered = content_module._render_prompt_text(
        "{{企业标准名称}}｜{{所在地区}}｜{{主营业务}}｜{{企业事实}}",
        brief,
        snapshot,
    )

    assert "青岛莱恩美术教育" in rendered
    assert "即墨区" in rendered
    assert "少儿美术培训" in rendered
    assert "课程设置清晰" in rendered
    assert "3000" not in rendered
    assert "专利局" not in rendered
    assert "13800138000" not in rendered


@pytest.mark.unit
def test_regeneration_repair_prompt_uses_findings_without_candidate_body() -> None:
    brief = SimpleNamespace(
        title="即墨少儿美术培训机构怎么选",
        content_type="selection_guide",
        target_keywords=["即墨少儿美术培训机构"],
        retest_questions=["即墨少儿美术培训机构怎么选"],
        target_level="L1",
        audience="本地家长",
        angle="客观选择",
        expected_recommendation_reason="真实信息",
    )
    snapshot = SimpleNamespace(
        facts=[
            {
                "key": "identity.standard_name",
                "label": "企业名称",
                "value": "青岛莱恩美术教育",
                "category": "identity",
            },
        ],
        evidence=[],
        prohibited_claims=[],
    )

    prompt = content_module._regeneration_repair_prompt(
        brief,
        snapshot,
        contact_policy="omit",
        revision_instruction="只保留已确认事实",
        target_channel_id="sohu",
        candidate_title="未通过标题",
        findings=[
            {
                "severity": "blocking",
                "category": "fact_consistency",
                "message": "正文推断了师资情况。",
                "suggested_fix": "删除师资推断。",
                "fact_id": "internal-id",
            },
        ],
    )

    assert "未通过标题" in prompt
    assert "正文推断了师资情况" in prompt
    assert "候选正文故意未提供" in prompt
    assert "internal-id" not in prompt


@pytest.mark.unit
def test_operator_revision_layer_is_replaced_and_restored_for_recheck() -> None:
    layers = content_module._with_operator_revision_layer(
        [
            {
                "code": "selection_guide",
                "version_number": 1,
                "applied_as": "content_form",
            },
            {
                "code": "operator_revision",
                "version_number": 1,
                "instruction": "旧建议",
            },
        ],
        "品牌最多出现三次",
    )
    version = SimpleNamespace(
        change_type="regenerated",
        prompt_layers_snapshot=layers,
    )

    assert sum(item["code"] == "operator_revision" for item in layers) == 1
    assert content_module._version_review_requirements(version) == "品牌最多出现三次"
    version.change_type = "edited"
    assert content_module._version_review_requirements(version) is None


@pytest.mark.unit
def test_regeneration_uses_current_prompt_versions_and_preserves_old_snapshot() -> None:
    def template(
        code: str,
        category: str,
        version: int,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            id=uuid4(),
            code=code,
            name=code,
            category=category,
            current_version=version,
            contact_policy="omit" if category == "channel_adapter" else None,
            channel_id="sohu" if category == "channel_adapter" else None,
            source_url=None,
            verified_at=None,
        )

    templates = {
        "writer_guardrail": template("writer_guardrail", "guardrail", 2),
        "writer_base": template("writer_base", "base", 3),
        "keyword_strategy": template("keyword_strategy", "keyword_strategy", 4),
        "selection_guide": template("selection_guide", "content_form", 5),
        "channel_sohu": template("channel_sohu", "channel_adapter", 6),
    }
    old_layers = [
        {
            "code": "writer_base",
            "category": "base",
            "version_number": 1,
            "applied_as": "base",
        },
        {
            "code": "keyword_strategy",
            "category": "keyword_strategy",
            "version_number": 1,
            "applied_as": "upstream_keyword_strategy",
        },
    ]
    source = SimpleNamespace(
        prompt_layers_snapshot=old_layers,
        prompt_template_code="selection_guide",
    )
    brief = SimpleNamespace(
        prompt_layers_snapshot=old_layers,
        prompt_template_code="selection_guide",
    )

    current_layers = content_module._current_regeneration_prompt_layers(
        templates,
        source=source,
        brief=brief,
        channel_template=templates["channel_sohu"],
    )

    assert old_layers[0]["version_number"] == 1
    assert {item["applied_as"]: item["version_number"] for item in current_layers} == {
        "guardrail": 2,
        "base": 3,
        "upstream_keyword_strategy": 4,
        "content_form": 5,
        "channel_adapter": 6,
    }


@pytest.mark.unit
def test_operator_requirements_are_split_into_a_hard_checklist() -> None:
    checklist = content_module._operator_requirement_checklist(
        "品牌最多出现3次。不要推断师资或排课；\n只设3个问题式小标题。",
    )

    assert checklist == [
        "品牌最多出现3次",
        "不要推断师资或排课",
        "只设3个问题式小标题",
    ]


@pytest.mark.unit
def test_review_drops_findings_that_conclude_no_change_is_needed() -> None:
    compliant = content_module.ReviewFindingOutput(
        severity="blocking",
        category="fact_consistency",
        message="正文使用4-16岁，与事实快照一致，故不构成问题。",
        fact_id=None,
        suggested_fix="无需修改。",
    )
    actionable = content_module.ReviewFindingOutput(
        severity="blocking",
        category="natural_language",
        message="品牌名称出现5次，超过最多3次的要求。",
        fact_id=None,
        suggested_fix="减少品牌名称。",
    )

    assert content_module._review_finding_is_actionable(compliant) is False
    assert content_module._review_finding_is_actionable(actionable) is True
    assert (
        content_module._review_finding_is_actionable(
            compliant.model_copy(
                update={"message": "品牌共出现2次，符合最多3次要求，此条无问题，不应报告。"},
            ),
        )
        is False
    )


@pytest.mark.unit
def test_review_parser_accepts_direct_array_and_chinese_field_names() -> None:
    parsed = cast(
        content_module.ReviewModelOutput,
        content_module._parse_model_json(
            json.dumps(
                [
                    {
                        "严重程度": "阻断",
                        "问题类型": "事实准确性",
                        "问题": "正文中的师资数量没有知识库依据。",
                        "修改建议": "删除未经确认的数量。",
                    },
                    {
                        "level": "low",
                        "dimension": "自然度",
                        "description": "有一处表达略显模板化。",
                        "suggestion": "改成更自然的叙述。",
                    },
                ],
                ensure_ascii=False,
            ),
            content_module.ReviewModelOutput,
        ),
    )

    assert len(parsed.findings) == 2
    assert parsed.findings[0].severity == "blocking"
    assert parsed.findings[0].category == "fact_consistency"
    assert parsed.findings[1].severity == "info"
    assert parsed.findings[1].category == "natural_language"


@pytest.mark.unit
def test_review_parser_accepts_common_wrapper_and_alias_fields() -> None:
    parsed = cast(
        content_module.ReviewModelOutput,
        content_module._parse_model_json(
            json.dumps(
                {
                    "data": {
                        "issues": [
                            {
                                "risk_level": "medium",
                                "type": "keyword_relevance",
                                "reason": "文章没有直接回答目标问题。",
                                "recommendation": "在开头给出清晰结论。",
                            },
                        ],
                    },
                },
                ensure_ascii=False,
            ),
            content_module.ReviewModelOutput,
        ),
    )

    assert parsed.findings[0].severity == "warning"
    assert parsed.findings[0].category == "question_relevance"
    assert parsed.findings[0].message == "文章没有直接回答目标问题。"


@pytest.mark.unit
def test_review_parser_still_rejects_payload_without_findings() -> None:
    with pytest.raises(ApiFailure, match="模型返回格式异常"):
        content_module._parse_model_json(
            '{"score": 92, "summary": "整体良好"}',
            content_module.ReviewModelOutput,
        )


@pytest.mark.unit
def test_channel_contact_policy_sanitizes_phone_wechat_and_offsite_links() -> None:
    source = (
        "如需确认课程，可拨打 13812345678。\n"
        "联系微信：lane-art88\n"
        "扫码添加微信领取资料。\n"
        "详情：https://example.com/contact\n"
        "也可以通过平台官方主页继续核验。"
    )

    official_only = content_module._sanitize_contact_content(
        source,
        "official_only",
    )
    verified_official = content_module._sanitize_contact_content(
        source,
        "official_only",
        allowed_urls=["https://example.com/contact"],
    )
    omitted = content_module._sanitize_contact_content(source, "omit")

    assert "13812345678" not in official_only
    assert "lane-art88" not in official_only
    assert "扫码" not in official_only
    assert "https://example.com/contact" not in official_only
    assert "https://example.com/contact" in verified_official
    assert "https://example.com/contact" not in omitted
    assert "平台官方主页" in omitted


@pytest.mark.unit
def test_channel_contact_policy_covers_common_contact_variants_without_text_loss() -> None:
    source = (
        "电话 138-0013-8000，备用 １３８００１３８０００；"
        "全角分隔 １３８－００１３－８０００，点分 138.0013.8000；"
        "V：lane-art88，vx lane_service，微信同号。\n"
        "微 信：lane-art88\n"
        "官网 www.example.com/about。之后再比较服务。\n"
        "不要扫码添加微信，谨防诈骗。\n"
        "![联系二维码](https://img.example.com/qr.png)\n"
        '<img alt="微信二维码" src="https://img.example.com/qr-code.png">'
    )

    cleaned = content_module._sanitize_contact_content(source, "omit")

    assert "138-0013-8000" not in cleaned
    assert "１３８００１３８０００" not in cleaned
    assert "１３８－００１３－８０００" not in cleaned
    assert "138.0013.8000" not in cleaned
    assert "lane-art88" not in cleaned
    assert "lane_service" not in cleaned
    assert "www.example.com" not in cleaned
    assert "之后再比较服务" in cleaned
    assert "谨防诈骗" in cleaned
    assert "![" not in cleaned
    assert "<img" not in cleaned


@pytest.mark.unit
def test_channel_contact_policy_removes_qq_public_account_email_and_dm_guidance() -> None:
    source = (
        "QQ群：12345678\n"
        "公众号：莱恩美术\n"
        "邮箱：sales@example.com\n"
        "私信我领取资料\n"
        "加入学习群：12345678\n"
        "微信公众号莱恩美术\n"
        "可以私信了解详情\n"
        "联系QQ abc123\n"
        "先比较课程安排、师资信息与实际服务边界。"
    )

    cleaned = content_module._sanitize_contact_content(source, "omit")

    assert "12345678" not in cleaned
    assert "公众号" not in cleaned
    assert "sales@example.com" not in cleaned
    assert "私信我" not in cleaned
    assert "加入学习群" not in cleaned
    assert "微信公众号莱恩美术" not in cleaned
    assert "可以私信" not in cleaned
    assert "abc123" not in cleaned
    assert "实际服务边界" in cleaned


@pytest.mark.unit
def test_content_form_required_facts_are_kept_in_article_snapshot_selection() -> None:
    facts = [
        SimpleNamespace(
            key="service.primary",
            label="核心服务",
            value="少儿美术培训",
        ),
        SimpleNamespace(
            key="pricing.standard",
            label="收费说明",
            value="以到店咨询后的最新课程方案为准",
        ),
        SimpleNamespace(
            key="process.consultation",
            label="咨询流程",
            value="先确认年龄与需求，再沟通课程安排",
        ),
        SimpleNamespace(
            key="case.family_choice",
            label="真实案例",
            value="家长根据通勤与孩子兴趣选择课程",
        ),
    ]

    selected = content_module._select_article_facts(
        facts,
        (),
        ("service", "price", "process", "case"),
    )

    assert {fact.key for fact in selected} == {
        "service.primary",
        "pricing.standard",
        "process.consultation",
        "case.family_choice",
    }


@pytest.mark.unit
def test_required_fact_groups_are_reserved_before_article_snapshot_limit() -> None:
    facts = [
        SimpleNamespace(
            key=f"service.option_{index}",
            label=f"服务项目 {index}",
            value=f"服务 {index}",
        )
        for index in range(18)
    ]
    price = SimpleNamespace(
        key="pricing.standard",
        label="收费说明",
        value="以当前方案为准",
    )
    facts.append(price)

    selected = content_module._select_article_facts(
        facts,
        (),
        ("service", "price"),
    )

    assert len(selected) == 15
    assert price in selected
    assert any(fact.key.startswith("service.") for fact in selected)


@pytest.mark.unit
def test_export_sources_cannot_reintroduce_omitted_contact_details() -> None:
    version = SimpleNamespace(
        title="即墨少儿美术怎么选",
        body_markdown="正文只保留服务信息。",
        contact_policy="omit",
        contact_allowed_urls=[],
    )
    snapshot = SimpleNamespace(
        facts=[
            {
                "key": "contact.public",
                "label": "联系电话",
                "value": "13800138000",
                "category": "contact",
            },
            {
                "key": "service.primary",
                "label": "主营业务",
                "value": "少儿美术培训",
                "category": "service",
            },
        ],
        evidence=[
            {
                "source_label": "客户资料",
                "observed_at": "2026-07-29",
                "source_url": "https://unverified.example/contact",
                "quote": "微信 lane-art88，电话 13800138000",
            },
        ],
    )

    exported = content_module._render_export(
        version,
        snapshot,
        format_name="markdown",
        include_sources=True,
    ).decode()

    assert "少儿美术培训" in exported
    assert "13800138000" not in exported
    assert "lane-art88" not in exported
    assert "unverified.example" not in exported


@pytest.mark.unit
def test_content_v2_cleans_internal_source_markers_from_public_markdown() -> None:
    body = (
        "## 机构信息\n\n"
        "青岛莱恩美术教育位于即墨区 "
        "[来源: client:c05353e3-9698-4ef7-87f1-58d89fbbf5fe]。\n\n"
        "不作效果承诺 [来源: prohibited_claims]。"
    )

    cleaned = content_module._clean_generated_markdown(body)

    assert "[来源:" not in cleaned
    assert "client:" not in cleaned
    assert "prohibited_claims" not in cleaned
    assert "青岛莱恩美术教育位于即墨区。" in cleaned


@pytest.mark.unit
def test_content_v2_cleans_dangling_markdown_separator() -> None:
    cleaned = content_module._clean_generated_markdown(
        "正文最后一段。\n\n*\n\n资料来源：青岛莱恩美术教育提供的公开教学资料。",
    )

    assert "\n*\n" not in cleaned
    assert cleaned.endswith("资料来源：青岛莱恩美术教育提供的公开教学资料。")


@pytest.mark.unit
def test_content_v2_cleans_fullwidth_source_markers_and_internal_fields() -> None:
    body = (
        "莱恩美术位于即墨区【来源：fact_id=internal】。\n"
        "fact_id=internal；evidence_id=source-1；client_id=client-1"
    )

    cleaned = content_module._clean_generated_markdown(body)

    assert "来源" not in cleaned
    assert "fact_id" not in cleaned
    assert "evidence_id" not in cleaned
    assert "client_id" not in cleaned
    assert "莱恩美术位于即墨区。" in cleaned


@pytest.mark.unit
def test_content_v2_quality_blocks_internal_ids_and_keyword_stuffing_only() -> None:
    keyword = "即墨区少儿美术培训"
    brief = SimpleNamespace(
        title="即墨区少儿美术培训怎么选",
        target_keywords=[keyword],
        retest_questions=["即墨区少儿美术培训怎么选"],
    )
    snapshot = SimpleNamespace(
        facts=[
            {
                "id": "client:test",
                "key": "standard_name",
                "label": "企业标准名称",
                "value": "青岛莱恩美术教育",
            },
            {
                "id": "location:test",
                "key": "location.administrative_area",
                "label": "所在地区",
                "value": "山东省青岛市即墨区",
            },
            {
                "id": "service:test",
                "key": "service.primary",
                "label": "核心服务",
                "value": "少儿美术培训",
            },
            {
                "id": "audience:test",
                "key": "audience.primary",
                "label": "主要服务对象",
                "value": "4—16 岁少儿",
            },
        ],
        evidence=[{"source_label": "客户资料采集表"}],
        prohibited_claims=[],
    )
    content = (
        "# 即墨区少儿美术培训怎么选\n\n"
        "青岛莱恩美术教育位于山东省青岛市即墨区，提供少儿美术培训。"
        + f"{keyword}。" * 9
        + " [来源: client:c05353e3-9698-4ef7-87f1-58d89fbbf5fe]"
    )

    overall, _, findings = content_module._quality_result(content, snapshot, brief)
    messages = [str(item["message"]) for item in findings]

    assert overall == "blocked"
    assert any("内部" in message and "来源" in message for message in messages)
    assert any("关键词" in message and "重复" in message for message in messages)
    assert not any(
        "主要服务对象" in message and "未按快照原值出现" in message for message in messages
    )


def content_quality_fixture() -> tuple[SimpleNamespace, SimpleNamespace]:
    brief = SimpleNamespace(
        title="即墨少儿美术培训怎么选",
        target_keywords=["即墨少儿美术培训"],
        retest_questions=["即墨少儿美术培训怎么选"],
    )
    snapshot = SimpleNamespace(
        facts=[
            {
                "id": "client:test",
                "key": "standard_name",
                "label": "企业标准名称",
                "value": "青岛莱恩文化艺术培训学校有限公司",
            },
            {
                "id": "client:short",
                "key": "short_name",
                "label": "企业简称",
                "value": "莱恩美术",
            },
            {
                "id": "location:test",
                "key": "location.service_area",
                "label": "服务区域",
                "value": "即墨区及周边区域",
            },
            {
                "id": "service:test",
                "key": "service.primary",
                "label": "核心服务",
                "value": "少儿美术培训、成人美术与作品集辅导",
            },
        ],
        evidence=[{"source_label": "客户资料采集表"}],
        prohibited_claims=[],
    )
    return brief, snapshot


@pytest.mark.unit
def test_content_v2_quality_allows_chinese_lists_and_structural_counts() -> None:
    brief, snapshot = content_quality_fixture()
    content = (
        "# 即墨少儿美术培训怎么选\n\n"
        "莱恩美术在即墨区提供少儿美术培训。咨询前先问清3个问题：\n"
        "1、课程内容\n2、上课安排\n3、费用规则"
    )

    overall, _, findings = content_module._quality_result(content, snapshot, brief)

    assert overall != "blocked"
    assert not any("数字或数量主张" in str(item["message"]) for item in findings)


@pytest.mark.unit
def test_content_v2_quality_blocks_unsupported_free_trial_claim() -> None:
    brief, snapshot = content_quality_fixture()
    content = (
        "# 即墨少儿美术体验课怎么选\n\n"
        "莱恩美术在即墨区提供少儿美术培训。体验课通常不收费，"
        "家长只需要承担少量材料费。"
    )

    overall, _, findings = content_module._quality_result(content, snapshot, brief)

    assert overall == "blocked"
    assert any(
        item["category"] == "fact_consistency" and "费用" in str(item["message"])
        for item in findings
    )


@pytest.mark.unit
def test_content_v2_quality_allows_fee_questions_without_making_claims() -> None:
    brief, snapshot = content_quality_fixture()
    content = (
        "# 即墨少儿美术体验课怎么选\n\n"
        "莱恩美术在即墨区提供少儿美术培训。咨询时可以确认体验课是否收费，"
        "以及材料费如何计算。"
    )

    overall, _, findings = content_module._quality_result(content, snapshot, brief)

    assert overall != "blocked"
    assert not any("费用政策" in str(item["message"]) for item in findings)


@pytest.mark.unit
def test_content_v2_quality_warns_common_promotional_claims() -> None:
    brief, snapshot = content_quality_fixture()
    content = (
        "# 即墨少儿美术培训怎么选\n\n"
        "莱恩美术在即墨区提供少儿美术培训，"
        "是一家值得信赖的专业机构，也是当地家长的首选。"
    )

    overall, _, findings = content_module._quality_result(content, snapshot, brief)

    assert overall == "warning"
    assert any(
        item["category"] == "natural_language" and item["severity"] == "warning"
        for item in findings
    )


@pytest.mark.unit
def test_content_v2_quality_accepts_natural_core_fact_phrasing() -> None:
    brief, snapshot = content_quality_fixture()
    content = (
        "# 即墨少儿美术培训怎么选\n\n"
        "莱恩美术在即墨区提供少儿美术培训。"
        "家长可以结合孩子年龄、课程安排和试听情况再做决定。"
    )

    overall, _, findings = content_module._quality_result(content, snapshot, brief)

    assert overall == "passed"
    assert not any(item["category"] == "fact_consistency" for item in findings)


@pytest.mark.unit
def test_channel_quality_blocks_repetitive_promotional_article() -> None:
    _, snapshot = content_quality_fixture()
    version = SimpleNamespace(
        target_channel_id="toutiao",
        title="在即墨给孩子选美术班，先看这五个标准再决定",
        body_markdown=(
            "与其直接问哪家好，不如先看几个标准。"
            + "莱恩美术在即墨区提供少儿美术培训。" * 7
            + "家长可以逐项咨询课程、教师沟通和试听反馈。" * 45
        ),
    )

    findings = content_module._platform_quality_findings(version, snapshot)

    assert any(
        item["severity"] == "blocking" and item["category"] == "platform_low_quality"
        for item in findings
    )
    assert any("模板" in str(item["message"]) for item in findings)
    assert any("企业名称" in str(item["message"]) for item in findings)


@pytest.mark.unit
def test_channel_quality_accepts_substantial_neutral_information() -> None:
    _, snapshot = content_quality_fixture()
    body = (
        "家长第一次了解课程时，可以先明确孩子当前更需要兴趣体验、基础训练，还是长期学习安排。"
        "这个判断会影响咨询时应该问什么，也能减少只比较宣传词带来的误差。"
        "\n\n## 先把需求说清楚\n\n"
        + "咨询时可分别了解课堂任务、反馈方式和阶段安排，并让机构说明哪些信息现在能够确认。" * 12
        + "\n\n## 用一次试听核对实际感受\n\n"
        + "试听后可以记录孩子是否听懂要求、是否愿意继续完成任务，以及教师如何回应不同节奏。" * 12
        + "\n\n莱恩美术位于即墨区，提供少儿美术培训，可作为了解本地课程时核验的一个对象。"
    )
    version = SimpleNamespace(
        target_channel_id="toutiao",
        title="第一次带孩子试听美术课，可以重点记录什么",
        body_markdown=body,
    )

    assert content_module._platform_quality_findings(version, snapshot) == []


@pytest.mark.unit
def test_toutiao_quality_blocks_direct_conversion_and_soft_advertising() -> None:
    _, snapshot = content_quality_fixture()
    body = (
        "孩子第一次接触美术课程时，可以先观察是否愿意表达自己的想法，以及能否理解课堂任务。"
        "记录这些具体表现，比只比较宣传口号更容易找到真实需求。"
        "\n\n## 先观察课堂反馈\n\n"
        + "家长可以记录孩子完成任务时遇到的困难、教师给出的反馈和课后仍愿意继续尝试的内容。" * 9
        + "\n\n## 再核对长期安排\n\n"
        + "时间安排、接送距离和家庭节奏会影响长期坚持，判断时需要把这些实际条件一起考虑。" * 9
        + "\n\n莱恩美术课程体系完善，值得家长优先选择，欢迎到店试听并报名咨询。"
    )

    findings = content_module._platform_quality_findings_for_content(
        title="孩子第一次学画画，家长可以观察哪些课堂反馈",
        body_markdown=body,
        target_channel_id="toutiao",
        fallback_reason=None,
        snapshot=snapshot,
    )

    assert any(item["category"] == "platform_advertising" for item in findings)
    assert any("直接转化" in str(item["message"]) for item in findings)
    assert any("软文推介" in str(item["message"]) for item in findings)


@pytest.mark.unit
def test_toutiao_quality_blocks_sensational_title_and_thin_structure() -> None:
    _, snapshot = content_quality_fixture()
    body = (
        "孩子第一次学画画时，可以记录课堂任务、反馈方式和完成过程。"
        "这些观察能帮助家长判断当前安排是否匹配实际需求。" * 25
    )

    findings = content_module._platform_quality_findings_for_content(
        title="家长必看！即墨这家美术机构太厉害了",
        body_markdown=body,
        target_channel_id="toutiao",
        fallback_reason=None,
        snapshot=snapshot,
    )

    assert any("诱导或夸张" in str(item["message"]) for item in findings)
    assert any("有效内容部分不足" in str(item["message"]) for item in findings)


@pytest.mark.unit
def test_netease_quality_blocks_advertorial_language_and_brand_title() -> None:
    _, snapshot = content_quality_fixture()
    body = (
        "挑选课程前，可以先观察孩子当前的书写习惯和需要提升的方向。" * 25
        + "青岛莱恩美术教育提供线上咨询和试听课，家长可以到店了解课程体系。"
        + "该机构的服务范围覆盖多类课程。"
    )

    findings = content_module._platform_quality_findings_for_content(
        title="青岛莱恩美术教育硬笔书法课程怎么选",
        body_markdown=body,
        target_channel_id="netease",
        fallback_reason=None,
        snapshot=snapshot,
    )

    assert any(item["category"] == "platform_advertising" for item in findings)
    assert any("标题出现企业或品牌名称" in str(item["message"]) for item in findings)
    assert any("消费转化" in str(item["message"]) for item in findings)
    assert any("重复机构曝光" in str(item["message"]) for item in findings)


@pytest.mark.unit
def test_yidian_quality_blocks_advertorial_language_and_brand_title() -> None:
    _, snapshot = content_quality_fixture()
    body = (
        "给孩子安排课外练习时，可以先观察当前需要解决的问题，再记录孩子是否愿意持续完成。" * 35
        + "青岛莱恩美术教育提供课程咨询和报名服务，欢迎添加微信领取试听福利。"
    )

    findings = content_module._platform_quality_findings_for_content(
        title="青岛莱恩美术教育少儿美术课程值得推荐吗",
        body_markdown=body,
        target_channel_id="yidian",
        fallback_reason=None,
        snapshot=snapshot,
    )

    assert any(item["category"] == "platform_advertising" for item in findings)
    assert any("标题出现企业或品牌名称" in str(item["message"]) for item in findings)
    assert any("商业营销" in str(item["message"]) for item in findings)


@pytest.mark.unit
def test_yidian_reference_policy_keeps_one_neutral_source_note() -> None:
    _, snapshot = content_quality_fixture()
    body = (
        "## 先看日常表现\n\n"
        + "孩子刚开始接触书写练习时，可以分别观察握笔、运笔和完成任务时的反应。" * 12
        + "\n\n## 再记录变化\n\n"
        + "记录练习前后容易卡住的环节，比急着判断进步更能帮助调整练习安排。" * 12
        + "\n\n## 最后复盘过程\n\n"
        + "复盘时重点比较任务完成的过程和稳定性，避免只用一次书写结果下结论。" * 12
        + "青岛莱恩美术教育提供多种课程，欢迎咨询报名。"
        + "该机构的课程体系也可以进一步了解。"
    )

    cleaned = content_module._apply_enterprise_reference_policy(
        body,
        snapshot,
        target_channel_id="yidian",
    )
    findings = content_module._platform_quality_findings_for_content(
        title="孩子练字时，先观察哪些实际问题",
        body_markdown=cleaned,
        target_channel_id="yidian",
        fallback_reason=None,
        snapshot=snapshot,
    )

    assert cleaned.count("青岛莱恩文化艺术培训学校有限公司") == 1
    assert "该机构" not in cleaned
    assert "咨询报名" not in cleaned
    assert cleaned.endswith(
        "资料参考：青岛莱恩文化艺术培训学校有限公司提供的公开信息。",
    )
    assert findings == []


@pytest.mark.unit
def test_netease_quality_accepts_knowledge_article_with_one_neutral_source_note() -> None:
    _, snapshot = content_quality_fixture()
    body = (
        "硬笔书写练习可以拆成观察、示范和复盘三个环节。" * 35
        + "不同阶段需要记录的问题并不相同，重点是识别握笔、结构与书写节奏的变化。"
        + "本文的本地教学观察样本由莱恩美术提供，文中方法属于一般性知识说明。"
    )

    findings = content_module._platform_quality_findings_for_content(
        title="孩子练字时，如何记录真正需要改进的问题",
        body_markdown=body,
        target_channel_id="netease",
        fallback_reason=None,
        snapshot=snapshot,
    )

    assert findings == []


@pytest.mark.unit
def test_netease_reference_policy_removes_brand_pitch_and_keeps_one_attribution() -> None:
    _, snapshot = content_quality_fixture()
    body = (
        "孩子写字时出现勾腕，可以先观察纸张角度、坐姿和运笔方向。" * 30
        + "青岛莱恩美术教育提供多种课程，家长可到店试听。"
        + "该机构的课程体系也可以进一步了解。"
        + "如果持续疼痛，应咨询医疗或康复专业人士。\n\n*"
    )

    cleaned = content_module._apply_enterprise_reference_policy(
        body,
        snapshot,
        target_channel_id="netease",
    )
    findings = content_module._platform_quality_findings_for_content(
        title="孩子写字勾腕时，可以先检查哪些动作",
        body_markdown=cleaned,
        target_channel_id="netease",
        fallback_reason=None,
        snapshot=snapshot,
    )

    assert cleaned.count("青岛莱恩文化艺术培训学校有限公司") == 1
    assert "该机构" not in cleaned
    assert "到店试听" not in cleaned
    assert not cleaned.rstrip().endswith("*")
    assert "咨询医疗或康复专业人士" in cleaned
    assert cleaned.endswith(
        "资料来源：青岛莱恩文化艺术培训学校有限公司提供的公开教学资料。",
    )
    assert findings == []


@pytest.mark.unit
def test_netease_quality_blocks_unsourced_precision_and_medical_causation() -> None:
    _, snapshot = content_quality_fixture()
    body = (
        "硬笔书写可以先从可观察的握笔和运笔动作开始记录。" * 35
        + "每天练习10-15分钟，桌面应高出2-3厘米。"
        + "错误姿势会导致手指变形，根源在于手部小肌肉发育不足。"
        + "如果决定选择专业指导，可以了解机构提供的硬笔书法课程。"
        + "资料来源：青岛莱恩美术教育提供的公开教学资料。"
    )

    findings = content_module._platform_quality_findings_for_content(
        title="孩子写字勾腕时，可以先观察哪些动作",
        body_markdown=body,
        target_channel_id="netease",
        fallback_reason=None,
        snapshot=snapshot,
    )

    assert any("精确训练参数" in str(item["message"]) for item in findings)
    assert any("医学或发育因果" in str(item["message"]) for item in findings)
    assert any("机构推介" in str(item["message"]) for item in findings)


@pytest.mark.unit
def test_netease_generation_does_not_require_advertorial_service_introduction() -> None:
    brief, snapshot = content_quality_fixture()
    brief.target_keywords = ["即墨硬笔书法怎么选"]
    body = content_module._apply_enterprise_reference_policy(
        (
            "了解即墨硬笔书法训练时，可以先观察书写姿势、运笔节奏和纠错记录。" * 30
            + "这些信息比简单罗列课程更能说明练习是否针对实际问题。"
        ),
        snapshot,
        target_channel_id="netease",
    )

    findings = content_module._generation_repair_findings(
        title="练习硬笔书法时，怎样判断纠错是否有效",
        body=body,
        target_channel_id="netease",
        fallback_reason=None,
        snapshot=snapshot,
        brief=brief,
    )

    assert not any(item["category"] == "entity_clarity" for item in findings)


@pytest.mark.unit
def test_generation_cleanup_limits_enterprise_mentions_before_quality_check() -> None:
    _, snapshot = content_quality_fixture()
    body = (
        "第一次带孩子试听美术课，可以先记录孩子是否理解课堂要求，以及老师如何回应。"
        "莱恩美术可以作为本地核验对象。"
        "咨询莱恩美术时可以了解课程安排。"
        "到莱恩美术试听时可以观察课堂互动。"
        "莱恩美术的公开信息需要逐项核实。"
        "最终是否选择莱恩美术，仍应结合孩子的实际感受。"
        + "家长还可以记录课堂任务、反馈方式、阶段安排和请假规则，再比较是否适合长期学习。"
        * 14
    )

    cleaned = content_module._limit_enterprise_mentions(
        body,
        snapshot,
        max_mentions=2,
    )
    findings = content_module._platform_quality_findings_for_content(
        title="第一次带孩子试听美术课，可以重点记录什么",
        body_markdown=cleaned,
        target_channel_id="toutiao",
        fallback_reason=None,
        snapshot=snapshot,
    )

    assert cleaned.count("莱恩美术") <= 2
    assert "该机构" in cleaned
    assert not any("企业名称" in str(item["message"]) for item in findings)


@pytest.mark.unit
def test_initial_generation_repair_collects_publish_blockers_and_high_value_warnings() -> None:
    brief, snapshot = content_quality_fixture()
    findings = content_module._generation_repair_findings(
        title="即墨少儿美术培训全面解析",
        body=("莱恩美术是即墨区最好的少儿美术培训机构。此外，莱恩美术值得信赖，是当地家长的首选。"),
        target_channel_id="toutiao",
        fallback_reason=None,
        snapshot=snapshot,
        brief=brief,
    )

    assert any(item["severity"] == "blocking" for item in findings)
    assert any(item["category"] == "natural_language" for item in findings)
    assert all("suggested_fix" in item for item in findings)


@pytest.mark.unit
def test_generation_final_gate_rejects_remaining_blockers_instead_of_saving_them() -> None:
    findings = [
        {
            "severity": "blocking",
            "category": "fact_consistency",
            "message": "正文包含知识库未支持的数字事实。",
            "suggested_fix": "删除未确认数字。",
        },
        {
            "severity": "warning",
            "category": "natural_language",
            "message": "表达仍可更自然。",
            "suggested_fix": "调整句式。",
        },
    ]

    with pytest.raises(ApiFailure) as caught:
        content_module._assert_publishable_generation(findings)

    assert caught.value.code == 42202
    assert caught.value.retryable is True
    assert "半成品不会保存" in caught.value.message


@pytest.mark.unit
def test_generation_final_gate_rejects_actionable_quality_warnings() -> None:
    with pytest.raises(ApiFailure) as caught:
        content_module._assert_publishable_generation(
            [
                {
                    "severity": "warning",
                    "category": "natural_language",
                    "message": "表达仍有模板化痕迹。",
                    "suggested_fix": "调整句式。",
                },
            ],
        )

    assert caught.value.retryable is True


@pytest.mark.unit
def test_generation_final_gate_allows_non_actionable_suggestions() -> None:
    content_module._assert_publishable_generation(
        [
            {
                "severity": "warning",
                "category": "stylistic_preference",
                "message": "运营人员可以按个人偏好调整标点。",
                "suggested_fix": "可选调整。",
            },
        ],
    )


@pytest.mark.unit
def test_advisory_best_wording_is_not_misclassified_as_absolute_promotion() -> None:
    assert not content_module._contains_asserted_prohibited_phrase(
        "第一次咨询时最好先问清课程安排，再判断是否适合孩子。",
        "最好",
    )
    assert not content_module._contains_asserted_prohibited_phrase(
        "家长最好不要只看作品效果，也要观察孩子是否愿意表达。",
        "最好",
    )
    assert content_module._contains_asserted_prohibited_phrase(
        "这就是即墨最好的少儿美术机构。",
        "最好",
    )


@pytest.mark.unit
def test_generation_naturalizer_removes_known_template_and_promotion_phrases() -> None:
    cleaned = content_module._naturalize_markdown(
        (
            "此外，这不仅仅是选择一家专业机构，还要追求最佳学习效果。"
            "家长最好先问清课程安排，机构不能保证效果。"
        ),
        protected_values=[],
        content_type="selection_guide",
        intensity="standard",
    )

    assert not any(phrase in cleaned for phrase in content_module.AI_STYLE_PATTERNS)
    assert "最好" not in cleaned
    assert "保证效果" not in cleaned
    assert "建议先问清课程安排" in cleaned


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generation_candidate_check_includes_cross_document_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief, snapshot = content_quality_fixture()

    async def duplicate_finding(*args: object, **kwargs: object) -> dict[str, object]:
        del args, kwargs
        return {
            "severity": "blocking",
            "category": "duplicate_content",
            "message": "与历史文章高度相似。",
            "suggested_fix": "更换角度。",
        }

    monkeypatch.setattr(
        content_module,
        "_cross_document_similarity_finding",
        duplicate_finding,
    )
    findings = await content_module._generation_candidate_findings(
        cast(object, SimpleNamespace()),
        cast(object, SimpleNamespace()),
        title="第一次带孩子试听美术课，可以重点记录什么",
        body=(
            "家长第一次了解课程时，可以先明确孩子当前更需要兴趣体验、基础训练，"
            "还是长期学习安排。咨询时可分别了解课堂任务、反馈方式和阶段安排。" * 12
        ),
        target_channel_id="toutiao",
        fallback_reason=None,
        snapshot=snapshot,
        brief=brief,
    )

    assert any(item["category"] == "duplicate_content" for item in findings)


@pytest.mark.unit
def test_writer_prompt_prioritizes_reader_value_over_enterprise_promotion() -> None:
    assert "大部分篇幅" in content_module.DRAFT_SYSTEM_PROMPT
    assert "企业信息" in content_module.DRAFT_SYSTEM_PROMPT
    assert "不能写成报名、咨询或推荐软文" in content_module.DRAFT_SYSTEM_PROMPT
    assert "一次成稿" in content_module.DRAFT_SYSTEM_PROMPT
    assert "只返回已经通过全部检查的最终稿" in content_module.DRAFT_SYSTEM_PROMPT
    assert "先在内部完成事实映射" in content_module.DRAFT_SYSTEM_PROMPT


@pytest.mark.unit
def test_writer_context_frontloads_machine_publishability_contract() -> None:
    brief, snapshot = content_quality_fixture()
    brief.target_channel_id = "toutiao"
    brief.content_type = "selection_guide"
    brief.audience = "本地家长"
    brief.angle = "从试听观察切入"
    brief.expected_recommendation_reason = "帮助家长核验是否匹配"
    snapshot.facts.extend(
        [
            {
                "id": "audience:test",
                "key": "audience.primary",
                "label": "服务年龄",
                "value": "4-16岁",
            },
            {
                "id": "price:test",
                "key": "pricing.note",
                "label": "费用说明",
                "value": "费用以到店咨询为准",
            },
        ],
    )

    context = json.loads(
        content_module._writer_model_context(brief, snapshot, contact_policy="omit"),
    )
    contract = context["publishability_contract"]

    assert contract["target_channel"] == "toutiao"
    assert contract["minimum_body_characters"] == 600
    assert contract["maximum_title_characters"] == 38
    assert contract["maximum_enterprise_mentions"] == 2
    assert contract["maximum_enterprise_share"] == "15%"
    assert "4-16岁" in contract["allowed_enterprise_numeric_claims"]
    assert contract["contact_policy"] == "omit"
    assert any("费用" in item for item in contract["allowed_fee_statements"])
    assert any("生成前" in item for item in contract["mandatory_preflight"])
    assert contract["generation_mode"] == "single_pass_final_only"
    assert contract["numeric_claim_policy"]["mode"] == "whitelist_only"
    assert contract["fee_claim_policy"]["mode"] == "whitelist_only"
    assert contract["minimum_substantive_sections"] == 3
    assert {
        "fact_whitelist",
        "numeric_whitelist",
        "fee_whitelist",
        "channel_quality",
        "natural_language",
    }.issubset(
        {item["rule_id"] for item in contract["hard_constraints"]},
    )
    assert "toutiao_no_batch_low_quality" in {
        item["rule_id"] for item in contract["hard_constraints"]
    }
    assert context["confirmed_facts"][0]["reference"] == "F01"
    assert context["generation_protocol"]["output"] == "final_article_only"
    assert context["generation_protocol"]["internal_steps"][-1].startswith(
        "只返回通过全部硬约束",
    )


@pytest.mark.unit
def test_generation_selects_a_publishable_title_candidate_before_quality_gate() -> None:
    body = (
        "家长带孩子试听美术课时，可以观察孩子是否愿意参与课堂，也可以记录老师"
        "如何回应孩子的问题。试听结束后，再结合接送距离和长期学习目标做判断。"
    )
    selected = content_module._select_publishable_title_candidate(
        "即墨区少儿美术培训机构哪家好先看这几点再决定并全面解析课程",
        [
            {
                "title": "即墨少儿美术先看这几点再决定",
                "title_type": "local_decision",
            },
            {
                "title": "带孩子试听美术课，可以观察什么？",
                "title_type": "scenario",
            },
        ],
        body,
    )

    assert selected == "带孩子试听美术课，可以观察什么？"


@pytest.mark.unit
def test_content_quality_accepts_question_intent_suffix_without_keyword_stuffing() -> None:
    brief, snapshot = content_quality_fixture()
    brief.target_keywords = ["即墨区少儿美术培训请推荐一家"]
    content = (
        "# 在即墨给孩子选美术班，可以先这样判断\n\n"
        "在即墨区选择少儿美术培训，家长可以先看课程是否匹配孩子需求，"
        "再结合接送距离和实际体验做决定。"
    )

    overall, _, findings = content_module._quality_result(content, snapshot, brief)

    assert overall != "blocked"
    assert not any(item["category"] == "question_relevance" for item in findings)


@pytest.mark.unit
def test_content_quality_accepts_semantic_keyword_elements_without_exact_phrase() -> None:
    brief, snapshot = content_quality_fixture()
    brief.target_keywords = ["即墨区少儿美术培训机构"]
    content = (
        "# 在即墨区给孩子选美术班，先想清楚这几点\n\n"
        "即墨区的美术培训机构各有侧重。家长可以结合孩子年龄、"
        "接送距离和实际体验进行判断。"
    )

    overall, _, findings = content_module._quality_result(content, snapshot, brief)

    assert overall != "blocked"
    assert not any(item["category"] == "question_relevance" for item in findings)
    assert "不要求逐字复现完整关键词" in content_module.DRAFT_SYSTEM_PROMPT


@pytest.mark.unit
def test_content_quality_accepts_long_scenario_question_when_core_terms_are_covered() -> None:
    brief, snapshot = content_quality_fixture()
    brief.target_keywords = [
        "孩子写字勾腕、翻腕、力气重，在即墨哪里可以纠正硬笔书法姿势？",
    ]
    content = (
        "# 孩子写字勾腕时，可以先检查哪些动作\n\n"
        "孩子写字出现勾腕、翻腕和用力过重时，可以先观察纸张角度、坐姿与运笔方向。"
        "在即墨了解硬笔书法训练时，应重点核对是否会记录姿势变化，并根据具体问题纠正。"
    )

    _, _, findings = content_module._quality_result(content, snapshot, brief)

    assert not any(item["category"] == "question_relevance" for item in findings)


@pytest.mark.unit
def test_content_quality_still_warns_when_core_service_is_missing() -> None:
    brief, snapshot = content_quality_fixture()
    brief.target_keywords = ["即墨区少儿美术培训机构"]
    content = (
        "# 在即墨区给孩子选兴趣班，可以先看接送距离\n\n家长可以先了解上课时间，再决定是否到店体验。"
    )

    _, _, findings = content_module._quality_result(content, snapshot, brief)

    assert any(item["category"] == "question_relevance" for item in findings)


@pytest.mark.unit
def test_content_v2_quality_ignores_referential_one_company_wording() -> None:
    brief, snapshot = content_quality_fixture()
    content = (
        "# 即墨少儿美术培训怎么选\n\n"
        "在即墨区寻找少儿美术培训机构，可以先比较课程与接送距离，"
        "再从附近校区中选择一家进行实地了解。"
    )

    _, _, findings = content_module._quality_result(content, snapshot, brief)

    assert not any("数字或数量主张" in str(item["message"]) for item in findings)
    assert not any(item["category"] == "question_relevance" for item in findings)


@pytest.mark.unit
def test_numeric_claims_keep_actual_single_store_claims() -> None:
    claims = content_module._numeric_claims("该机构在即墨区设有一家直营校区。")

    assert [item.text for item in claims] == ["一家"]


@pytest.mark.unit
def test_numeric_claims_ignore_age_word_but_capture_post_unit_bound() -> None:
    claims = content_module._numeric_claims(
        "这一年龄段重视兴趣培养，16岁以上的服务范围需单独确认。",
    )

    assert [item.text for item in claims] == ["16岁以上"]
    assert claims[0].relation == "lower"


@pytest.mark.unit
def test_numeric_claims_capture_ranges_with_units_on_both_endpoints() -> None:
    claims = content_module._numeric_claims(
        "少儿服务面向从4岁到16岁的孩子，这是一家本地机构。",
    )

    assert len(claims) == 1
    assert claims[0].start == "4"
    assert claims[0].end == "16"
    assert claims[0].unit == "岁"
    assert claims[0].relation == "range"


@pytest.mark.unit
def test_content_v2_quality_accepts_supported_numeric_wording_variants() -> None:
    brief, base_snapshot = content_quality_fixture()
    snapshot = SimpleNamespace(
        facts=[
            *base_snapshot.facts,
            {
                "id": "capability:test",
                "key": "capability.primary",
                "label": "企业优势",
                "value": ("莱恩美术在即墨区设有五家直营校区，累计服务学员人数超过3000余人。"),
            },
        ],
        evidence=base_snapshot.evidence,
        prohibited_claims=base_snapshot.prohibited_claims,
    )
    content = (
        "# 即墨少儿美术培训怎么选\n\n"
        "青岛莱恩文化艺术培训学校有限公司在即墨区提供少儿美术培训。"
        "已确认资料显示，莱恩美术在即墨区拥有5家直营校区，"
        "累计服务学员超过3000人，可概括为已服务数千名学员。"
    )

    overall, _, findings = content_module._quality_result(content, snapshot, brief)

    assert overall == "passed"
    assert not any("3000" in str(item["message"]) for item in findings)
    assert not any("数千名" in str(item["message"]) for item in findings)
    assert not any("拥有5家" in str(item["message"]) for item in findings)


@pytest.mark.unit
def test_content_quality_allows_general_age_stage_guidance() -> None:
    brief, base_snapshot = content_quality_fixture()
    snapshot = SimpleNamespace(
        facts=[
            *base_snapshot.facts,
            {
                "id": "audience:test",
                "key": "audience.primary",
                "label": "主要服务对象",
                "value": "适合4-18岁少儿美术书法培训",
            },
        ],
        evidence=base_snapshot.evidence,
        prohibited_claims=base_snapshot.prohibited_claims,
    )
    content = (
        "# 即墨少儿美术培训怎么选\n\n"
        "莱恩美术在即墨区提供少儿美术培训。"
        "一般来说，4-6岁可关注兴趣和材料体验，7-12岁可关注基础表达，"
        "13岁以上可以结合个人兴趣或学习目标继续了解。"
    )

    overall, _, findings = content_module._quality_result(content, snapshot, brief)

    assert overall != "blocked"
    assert not any("4-6岁" in str(item["message"]) for item in findings)
    assert not any("7-12岁" in str(item["message"]) for item in findings)
    assert not any("13岁以上" in str(item["message"]) for item in findings)


@pytest.mark.unit
def test_age_claim_context_does_not_match_suffix_of_another_age() -> None:
    content = (
        "如果孩子现在6岁，但以后可能想走美术特长生路线，可以先了解课程衔接。"
        "青岛莱恩美术教育公开的主要服务对象是4到16岁少儿。"
    )
    claim = next(item for item in content_module._numeric_claims(content) if item.text == "6岁")

    contexts = content_module._claim_contexts(content, claim)

    assert contexts == ["如果孩子现在6岁，但以后可能想走美术特长生路线，可以先了解课程衔接"]
    assert content_module._numeric_claim_is_general_age_guidance(
        content,
        claim,
        enterprise_names=["青岛莱恩美术教育", "莱恩美术"],
    )


@pytest.mark.unit
def test_content_quality_blocks_unsupported_client_age_segments() -> None:
    brief, base_snapshot = content_quality_fixture()
    snapshot = SimpleNamespace(
        facts=[
            *base_snapshot.facts,
            {
                "id": "audience:test",
                "key": "audience.primary",
                "label": "主要服务对象",
                "value": "适合4-18岁少儿美术书法培训",
            },
        ],
        evidence=base_snapshot.evidence,
        prohibited_claims=base_snapshot.prohibited_claims,
    )
    content = (
        "# 即墨少儿美术培训怎么选\n\n"
        "莱恩美术在即墨区提供少儿美术培训。"
        "莱恩美术为4-6岁开设兴趣启蒙课程，为7-12岁安排技法基础课程，"
        "并为13岁以上学员设置进阶课程。"
    )

    overall, _, findings = content_module._quality_result(content, snapshot, brief)
    messages = [str(item["message"]) for item in findings]

    assert overall == "blocked"
    assert any(
        "4-6岁" in message
        and "7-12岁" in message
        and "13岁以上" in message
        and "知识库当前确认的年龄范围为：4-18岁" in message
        for message in messages
    )


@pytest.mark.unit
def test_content_quality_allows_outside_age_range_as_consultation_caution() -> None:
    brief, base_snapshot = content_quality_fixture()
    snapshot = SimpleNamespace(
        facts=[
            *base_snapshot.facts,
            {
                "id": "audience:test",
                "key": "audience.primary",
                "label": "主要服务对象",
                "value": "适合4-16岁少儿美术书法培训",
            },
        ],
        evidence=base_snapshot.evidence,
        prohibited_claims=base_snapshot.prohibited_claims,
    )
    content = (
        "# 在即墨给孩子选美术班，可以先这样判断\n\n"
        "莱恩美术在即墨区提供少儿美术培训，主要面向4至16岁少儿。"
        "如果孩子年龄在4岁以下或16岁以上，需要单独和机构沟通是否能够提供服务。"
    )

    overall, _, findings = content_module._quality_result(content, snapshot, brief)

    assert overall != "blocked"
    assert not any("4岁以下" in str(item["message"]) for item in findings)
    assert not any("16岁以上" in str(item["message"]) for item in findings)


@pytest.mark.unit
def test_content_v2_quality_does_not_treat_negated_superlative_as_a_claim() -> None:
    brief, snapshot = content_quality_fixture()
    content = (
        "# 即墨少儿美术培训怎么选\n\n"
        "少儿美术课程没有绝对的最好。莱恩美术在即墨区提供少儿美术培训，"
        "家长可以结合孩子年龄、课程安排和试听情况再做决定。"
    )

    overall, _, findings = content_module._quality_result(content, snapshot, brief)

    assert overall == "passed"
    assert not any("最好" in str(item["message"]) for item in findings)


@pytest.mark.unit
def test_content_v2_quality_allows_advisory_best_wording() -> None:
    brief, snapshot = content_quality_fixture()
    content = (
        "# 即墨少儿美术培训怎么选\n\n"
        "莱恩美术在即墨区提供少儿美术培训。"
        "出发前最好通过地图再次确认校区位置。"
    )

    overall, _, findings = content_module._quality_result(content, snapshot, brief)

    assert overall == "passed"
    assert not any("最好" in str(item["message"]) for item in findings)


@pytest.mark.unit
def test_sohu_fallback_title_avoids_local_search_capture_pattern() -> None:
    title = content_module._channel_variant_title(
        "即墨少儿美术培训：如何根据孩子年龄与目标匹配课程",
        "sohu",
    )

    assert title == "如何根据孩子年龄与目标匹配课程"
    assert "即墨" not in title
    assert "哪家好" not in title


@pytest.mark.unit
def test_title_candidates_keep_distinct_reader_value_angles() -> None:
    brief, snapshot = content_quality_fixture()
    candidates = content_module._normalize_title_candidates(
        "孩子刚开始学画画，先把兴趣和目标分开看",
        [
            {
                "title": "孩子刚开始学画画，先把兴趣和目标分开看",
                "title_type": "professional",
            },
            {
                "title": "即墨少儿美术培训怎么选？",
                "title_type": "qa",
            },
            {
                "title": "即墨少儿美术培训先看这5点再决定",
                "title_type": "local_decision",
            },
        ],
        brief=brief,
        snapshot=snapshot,
    )

    assert candidates[0]["title"] == "孩子刚开始学画画，先把兴趣和目标分开看"
    assert len(candidates) >= 3
    assert len({item["title_type"] for item in candidates}) >= 2
    assert all("先看这5点再决定" not in item["title"] for item in candidates)


@pytest.mark.unit
def test_platform_quality_blocks_title_body_mismatch() -> None:
    _brief, snapshot = content_quality_fixture()
    version = SimpleNamespace(
        title="孩子学画时如何理解色彩冷暖关系",
        body_markdown="即墨本地服务信息。" * 80,
        target_channel_id="sohu",
        fallback_reason=None,
    )

    findings = content_module._platform_quality_findings(version, snapshot)

    assert any("标题与正文" in str(item["message"]) for item in findings)


@pytest.mark.unit
def test_content_v2_provides_twenty_distinct_article_angles() -> None:
    angles = [
        content_module._article_angle_blueprint(sequence, "local_service")[:2]
        for sequence in range(1, 21)
    ]

    assert len(set(angles)) == 20


@pytest.mark.unit
def test_content_v2_fixed_mock_uses_the_selected_article_angle() -> None:
    snapshot = SimpleNamespace(
        facts=[
            {"key": "standard_name", "value": "莱恩美术"},
            {"key": "service.primary", "value": "少儿美术培训"},
            {"key": "location.service_area", "value": "即墨区"},
            {"key": "audience.primary", "value": "本地家庭"},
        ],
    )
    first = SimpleNamespace(
        title="即墨少儿美术培训怎么选",
        target_keywords=["即墨少儿美术培训"],
        angle="差异化角度：选择标准。",
        audience="本地家庭",
    )
    second = SimpleNamespace(
        title="即墨少儿美术培训怎么选",
        target_keywords=["即墨少儿美术培训"],
        angle="差异化角度：咨询清单。",
        audience="本地家庭",
    )

    first_body = content_module._build_fixed_mock_draft(first, snapshot, "outline")
    second_body = content_module._build_fixed_mock_draft(second, snapshot, "outline")

    assert first_body != second_body
    assert "选择标准" in first_body
    assert "咨询清单" in second_body


def run_content_worker(client, tmp_path: Path) -> None:
    settings = Settings(
        app_env="test",
        db_password=SecretStr("unused"),
        storage_root=tmp_path,
        model_execution_mode="fixed_mock",
        publishing_execution_mode="fixed_mock",
    )
    processed = asyncio.run(process_one_job(client.app.state.session_factory, settings))
    assert processed is True


def upload_enterprise_images(
    client,
    csrf: str,
    client_id: str,
    *,
    count: int = 1,
) -> None:
    files: list[tuple[str, tuple[str, bytes, str]]] = []
    colors = ("#3977e8", "#54a6eb", "#72c6b2")
    for index in range(count):
        output = BytesIO()
        Image.new("RGB", (1200, 800), colors[index % len(colors)]).save(
            output,
            format="PNG",
        )
        files.append(
            ("files", (f"企业图片-{index + 1}.png", output.getvalue(), "image/png")),
        )
    uploaded = client.post(
        f"/api/v1/clients/{client_id}/materials",
        headers={"X-CSRF-Token": csrf},
        data={"category": "image", "authorization_status": "authorized"},
        files=files,
    )
    assert uploaded.status_code == 201


def prepare_brief(client, csrf: str, client_id: str, tmp_path: Path) -> dict[str, object]:
    seed_required_facts(client, csrf, client_id)
    diagnostic_id = create_diagnostic(client, csrf, client_id, tmp_path)
    strategy = generate_strategy(client, csrf, client_id, diagnostic_id, tmp_path)
    return strategy["briefs"][0]


def prepare_keyword_strategy(
    client,
    csrf: str,
    client_id: str,
    tmp_path: Path,
) -> dict[str, object]:
    seed_required_facts(client, csrf, client_id)
    diagnostic_id = create_diagnostic(client, csrf, client_id, tmp_path)
    strategy = generate_strategy(client, csrf, client_id, diagnostic_id, tmp_path)
    return next(item for item in strategy["items"] if item["kind"] == "keyword")


@pytest.mark.integration
def test_selected_keywords_create_batch_ai_articles_and_support_publish_archive(
    tmp_path: Path,
) -> None:
    with build_client(
        tmp_path,
        model_execution_mode="fixed_mock",
        publishing_execution_mode="fixed_mock",
    ) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf)
        upload_enterprise_images(client, csrf, client_id, count=3)
        keyword = prepare_keyword_strategy(client, csrf, client_id, tmp_path)
        assert keyword["selected"] is False
        initial_toutiao_account = client.post(
            "/api/v1/publishing/channels/toutiao/accounts",
            headers={"X-CSRF-Token": csrf},
            json={"display_name": "头条默认账号"},
        )
        assert initial_toutiao_account.status_code == 201
        initial_toutiao_account_data = initial_toutiao_account.json()["data"]
        initial_test = client.post(
            f"/api/v1/publishing/accounts/{initial_toutiao_account_data['id']}/test",
            headers={"X-CSRF-Token": csrf},
        )
        assert initial_test.status_code == 200
        initial_connected = initial_test.json()["data"]
        initial_enabled = client.patch(
            f"/api/v1/publishing/accounts/{initial_toutiao_account_data['id']}",
            headers={"X-CSRF-Token": csrf},
            json={"version": initial_connected["version"], "enabled": True},
        )
        assert initial_enabled.status_code == 200

        missing_price = client.post(
            f"/api/v1/clients/{client_id}/documents/batch",
            headers={"X-CSRF-Token": csrf},
            json={
                "keyword_ids": [keyword["id"]],
                "article_count": 1,
                "length": "medium",
                "style": "auto",
                "content_form": "price_guide",
            },
        )
        assert missing_price.status_code == 422
        assert "真实价格或收费说明" in missing_price.json()["message"]

        batch = client.post(
            f"/api/v1/clients/{client_id}/documents/batch",
            headers={"X-CSRF-Token": csrf},
            json={
                "keyword_ids": [keyword["id"]],
                "article_count": 2,
                "length": "medium",
                "style": "auto",
                "content_form": "selection_guide",
                "target_channel_ids": ["toutiao"],
            },
        )
        assert batch.status_code == 201
        batch_payload = batch.json()["data"]
        created = batch_payload["items"]
        assert len(created) == 2
        assert all(item["keyword"] == keyword["text"] for item in created)
        assert all(item["keyword_type"] == keyword["keyword_type"] for item in created)
        assert all(item["status"] == "brief" for item in created)

        application = cast(FastAPI, client.app)

        async def batch_briefs() -> list[ContentBrief]:
            async with application.state.session_factory() as database:
                return list(
                    (
                        await database.scalars(
                            select(ContentBrief)
                            .join(
                                ContentDocument,
                                ContentDocument.brief_id == ContentBrief.id,
                            )
                            .where(
                                ContentDocument.id.in_(
                                    [UUID(str(item["id"])) for item in created],
                                ),
                            ),
                        )
                    ).all(),
                )

        briefs = asyncio.run(batch_briefs())
        assert len({brief.angle for brief in briefs}) == 2
        assert all("第 " not in brief.title for brief in briefs)
        assert all("差异化角度" in brief.angle for brief in briefs)
        assert all(brief.prompt_template_code == "selection_guide" for brief in briefs)
        assert all(brief.prompt_template_version == 1 for brief in briefs)
        assert all(brief.target_channel_id == "toutiao" for brief in briefs)
        assert all(brief.contact_policy == "omit" for brief in briefs)
        assert all(len(brief.prompt_layers_snapshot or []) == 5 for brief in briefs)
        assert all(
            {str(item["applied_as"]) for item in brief.prompt_layers_snapshot or []}
            == {
                "guardrail",
                "base",
                "upstream_keyword_strategy",
                "content_form",
                "channel_adapter",
            }
            for brief in briefs
        )

        run_content_worker(client, tmp_path)
        run_content_worker(client, tmp_path)
        documents = client.get(
            f"/api/v1/clients/{client_id}/documents",
        ).json()["data"]["items"]
        assert len(documents) == 2
        assert all(item["current_version"] for item in documents)
        assert all(len(item["current_version"]["image_material_ids"]) == 2 for item in documents)
        for item in documents:
            prepared_root = (
                tmp_path / "publishing" / "prepared" / "toutiao" / item["current_version"]["id"]
            )
            assert (prepared_root / "cover.jpg").is_file()
            assert (prepared_root / "body-1.jpg").is_file()
            assert (prepared_root / "body-2.jpg").is_file()
        assert all(
            len(item["current_version"]["prompt_layers_snapshot"]) == 5 for item in documents
        )

        async def rendered_prompt_layers(document_id: str) -> str:
            async with application.state.session_factory() as database:
                stored_document = await database.get(
                    ContentDocument,
                    UUID(document_id),
                )
                assert stored_document is not None
                stored_version = await database.get(
                    content_module.ContentVersion,
                    stored_document.current_version_id,
                )
                stored_brief = await database.get(
                    ContentBrief,
                    stored_document.brief_id,
                )
                assert stored_version is not None
                assert stored_brief is not None
                stored_snapshot = await database.get(
                    content_module.FactSnapshot,
                    stored_version.fact_snapshot_id,
                )
                assert stored_snapshot is not None
                return await content_module._prompt_layer_instructions(
                    database,
                    brief=stored_brief,
                    snapshot=stored_snapshot,
                    layer_refs=stored_version.prompt_layers_snapshot or [],
                )

        rendered_layers = asyncio.run(rendered_prompt_layers(documents[0]["id"]))
        assert rendered_layers.startswith("【最高优先级系统保护规则】")
        assert "【上游关键词策略依据】" in rendered_layers
        assert "不要重新生成关键词" in rendered_layers
        assert rendered_layers.rstrip().endswith(
            "发生冲突时必须以系统保护规则为准。",
        )
        assert rendered_layers.index("改成头条号原创信息图文") < rendered_layers.index(
            "【不可覆盖声明】",
        )

        publishable = next(item for item in documents if item["status"] == "checked")
        duplicate = next(item for item in documents if item["id"] != publishable["id"])

        async def mark_batch_articles_ready() -> None:
            async with application.state.session_factory() as database:
                await database.execute(
                    update(ContentDocument)
                    .where(
                        ContentDocument.generation_task_id == UUID(batch_payload["task"]["id"]),
                        ContentDocument.current_version_id.is_not(None),
                    )
                    .values(status="checked"),
                )
                await database.commit()

        asyncio.run(mark_batch_articles_ready())
        task_detail = client.get(
            f"/api/v1/content-generation-tasks/{batch_payload['task']['id']}",
        )
        assert task_detail.status_code == 200
        confirmed = client.post(
            f"/api/v1/content-generation-tasks/{batch_payload['task']['id']}/confirm",
            headers={"X-CSRF-Token": csrf},
            json={"version": task_detail.json()["data"]["version"]},
        )
        assert confirmed.status_code == 200, confirmed.text

        async def set_duplicate_status(status: str) -> None:
            async with application.state.session_factory() as database:
                await database.execute(
                    update(ContentDocument)
                    .where(ContentDocument.id == UUID(duplicate["id"]))
                    .values(status=status),
                )
                await database.commit()

        asyncio.run(set_duplicate_status("blocked"))

        edited_publishable = client.patch(
            f"/api/v1/documents/{publishable['id']}",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": publishable["version"],
                "title": f"{publishable['current_version']['title']} 13800138000",
                "body_markdown": (
                    f"{publishable['current_version']['body_markdown']}\n\n联系微信：lane-art88"
                ),
                "save_reason": "验证渠道规则与生成快照继承",
            },
        )
        assert edited_publishable.status_code == 200
        publishable = edited_publishable.json()["data"]
        assert "13800138000" not in publishable["current_version"]["title"]
        assert "lane-art88" not in publishable["current_version"]["body_markdown"]
        assert publishable["current_version"]["contact_policy"] == "omit"
        assert len(publishable["current_version"]["prompt_layers_snapshot"]) == 5
        assert publishable["status"] == "checked", [
            (item["category"], item["message"]) for item in publishable["latest_check"]["findings"]
        ]

        publishing_channels = client.get("/api/v1/publishing/channels").json()["data"]["items"]
        toutiao_accounts = next(item for item in publishing_channels if item["id"] == "toutiao")[
            "accounts"
        ]
        if toutiao_accounts:
            toutiao_account = toutiao_accounts[0]
        else:
            toutiao_account = client.post(
                "/api/v1/publishing/channels/toutiao/accounts",
                headers={"X-CSRF-Token": csrf},
                json={"display_name": "头条默认账号"},
            ).json()["data"]
        tested_channel = client.post(
            f"/api/v1/publishing/accounts/{toutiao_account['id']}/test",
            headers={"X-CSRF-Token": csrf},
        )
        assert tested_channel.status_code == 200
        channel = tested_channel.json()["data"]
        assert channel["connection_status"] == "connected"
        enabled_channel = client.patch(
            f"/api/v1/publishing/accounts/{toutiao_account['id']}",
            headers={"X-CSRF-Token": csrf},
            json={"enabled": True, "version": channel["version"]},
        )
        assert enabled_channel.status_code == 200
        assert enabled_channel.json()["data"]["enabled"] is True

        publish = client.post(
            f"/api/v1/documents/{publishable['id']}/publish",
            headers={
                "X-CSRF-Token": csrf,
                "Idempotency-Key": str(uuid4()),
            },
            json={
                "version": publishable["version"],
                "account_ids": [toutiao_account["id"]],
            },
        )
        assert publish.status_code == 202, publish.text
        run_content_worker(client, tmp_path)
        publishable = client.get(
            f"/api/v1/documents/{publishable['id']}",
        ).json()["data"]
        assert publishable["generation_status"] == "generated"
        assert publishable["publication_status"] == "published"
        assert (
            publishable["latest_publication"]["document_version_id"]
            == (publishable["current_version"]["id"])
        )
        assert publishable["latest_publication"]["status"] == "published"
        assert publishable["current_version_published"] is True

        asyncio.run(set_duplicate_status("checked"))
        copied_duplicate = client.patch(
            f"/api/v1/documents/{publishable['id']}",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": publishable["version"],
                "title": "复制另一篇正文后的版本",
                "body_markdown": duplicate["current_version"]["body_markdown"],
                "save_reason": "验证人工编辑后重新执行跨文章重复检查",
            },
        )
        assert copied_duplicate.status_code == 200
        copied_duplicate_data = copied_duplicate.json()["data"]
        assert copied_duplicate_data["status"] == "blocked"
        assert copied_duplicate_data["latest_publication"] is None
        assert copied_duplicate_data["current_version_published"] is False
        assert any(
            item["category"] == "duplicate_content" and item["severity"] == "blocking"
            for item in copied_duplicate_data["latest_check"]["findings"]
        )
        republish_duplicate = client.post(
            f"/api/v1/documents/{publishable['id']}/publish",
            headers={
                "X-CSRF-Token": csrf,
                "Idempotency-Key": str(uuid4()),
            },
            json={
                "version": copied_duplicate_data["version"],
                "account_ids": [toutiao_account["id"]],
            },
        )
        assert republish_duplicate.status_code == 422
        assert "可发布标准" in republish_duplicate.json()["message"]

        archived = client.delete(
            f"/api/v1/documents/{duplicate['id']}",
            headers={"X-CSRF-Token": csrf},
            params={"version": duplicate["version"]},
        )
        assert archived.status_code == 200
        archived_document = archived.json()["data"]
        assert archived_document["status"] == "archived"

        default_listing = client.get(
            f"/api/v1/clients/{client_id}/documents",
        ).json()["data"]["items"]
        assert all(item["id"] != duplicate["id"] for item in default_listing)
        deleted_listing = client.get(
            f"/api/v1/clients/{client_id}/documents",
            params={"status": "archived"},
        ).json()["data"]["items"]
        assert [item["id"] for item in deleted_listing] == [duplicate["id"]]

        restored = client.post(
            f"/api/v1/documents/{duplicate['id']}/restore",
            headers={"X-CSRF-Token": csrf},
            json={"version": archived_document["version"]},
        )
        assert restored.status_code == 200
        assert restored.json()["data"]["status"] == "blocked"
        restored_listing = client.get(
            f"/api/v1/clients/{client_id}/documents",
        ).json()["data"]["items"]
        assert any(item["id"] == duplicate["id"] for item in restored_listing)


@pytest.mark.integration
def test_regenerate_document_from_operator_instruction_and_target_channel(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf)
        upload_enterprise_images(client, csrf, client_id)
        brief = prepare_brief(client, csrf, client_id, tmp_path)
        created = client.post(
            f"/api/v1/clients/{client_id}/documents",
            headers={"X-CSRF-Token": csrf},
            json={"brief_id": brief["id"], "title": brief["title"]},
        ).json()["data"]
        run_content_worker(client, tmp_path)
        generated = client.get(
            f"/api/v1/documents/{created['id']}",
        ).json()["data"]
        blocked = client.patch(
            f"/api/v1/documents/{created['id']}",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": generated["version"],
                "title": "莱恩美术全市第一",
                "body_markdown": "# 推广稿\n\n莱恩美术最好，欢迎加微信报名。",
                "save_reason": "构造待修正版本",
            },
        ).json()["data"]
        assert blocked["status"] == "blocked"

        missing_instruction = client.post(
            f"/api/v1/documents/{created['id']}/operations",
            headers={
                "X-CSRF-Token": csrf,
                "Idempotency-Key": str(uuid4()),
            },
            json={
                "operation": "regenerate",
                "source_version_id": blocked["current_version"]["id"],
                "target_channel_id": "sohu",
            },
        )
        assert missing_instruction.status_code == 400

        accepted = client.post(
            f"/api/v1/documents/{created['id']}/operations",
            headers={
                "X-CSRF-Token": csrf,
                "Idempotency-Key": str(uuid4()),
            },
            json={
                "operation": "regenerate",
                "source_version_id": blocked["current_version"]["id"],
                "revision_instruction": ("删除推广语和联系方式，改成搜狐号可发布的客观选择指南"),
                "target_channel_id": "sohu",
            },
        )
        assert accepted.status_code == 202
        run_content_worker(client, tmp_path)

        regenerated = client.get(
            f"/api/v1/documents/{created['id']}",
        ).json()["data"]
        assert regenerated["current_version"]["change_type"] == "regenerated"
        assert regenerated["current_version"]["target_channel_id"] == "sohu"
        assert regenerated["current_version"]["contact_policy"] == "omit"
        assert "最好" not in regenerated["current_version"]["body_markdown"]
        assert "微信" not in regenerated["current_version"]["body_markdown"]
        assert regenerated["current_version"]["prompt_layers_snapshot"]

        generic_accepted = client.post(
            f"/api/v1/documents/{created['id']}/operations",
            headers={
                "X-CSRF-Token": csrf,
                "Idempotency-Key": str(uuid4()),
            },
            json={
                "operation": "regenerate",
                "source_version_id": regenerated["current_version"]["id"],
                "revision_instruction": "保留客观信息，重新生成通用稿",
                "target_channel_id": None,
            },
        )
        assert generic_accepted.status_code == 202
        run_content_worker(client, tmp_path)
        generic = client.get(
            f"/api/v1/documents/{created['id']}",
        ).json()["data"]
        assert generic["current_version"]["change_type"] == "regenerated"
        assert generic["current_version"]["target_channel_id"] is None
        assert generic["current_version"]["contact_policy"] == "manual_review"


@pytest.mark.integration
def test_batch_generation_rejects_a_stale_latest_diagnostic(tmp_path: Path) -> None:
    with build_client(tmp_path, model_execution_mode="fixed_mock") as client:
        csrf = login(client)
        client_id = create_customer(client, csrf)
        keyword = prepare_keyword_strategy(client, csrf, client_id, tmp_path)
        selected = client.patch(
            f"/api/v1/strategy-items/{keyword['id']}",
            headers={"X-CSRF-Token": csrf},
            json={"version": keyword["version"], "selected": True},
        )
        assert selected.status_code == 200
        keyword = selected.json()["data"]

        facts = client.get(
            f"/api/v1/clients/{client_id}/facts",
        ).json()["data"]["items"]
        service_fact = next(item for item in facts if item["key"] == "service.primary")
        edited = client.patch(
            f"/api/v1/facts/{service_fact['id']}",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": service_fact["version"],
                "value": "少儿美术与书法培训",
            },
        )
        assert edited.status_code == 200

        response = client.post(
            f"/api/v1/clients/{client_id}/documents/batch",
            headers={"X-CSRF-Token": csrf},
            json={
                "keyword_ids": [keyword["id"]],
                "article_count": 1,
                "length": "medium",
                "style": "auto",
                "content_form": "selection_guide",
                "target_channel_id": None,
            },
        )

        assert response.status_code == 422
        assert response.json()["message"] == "企业资料已经更新，请先重新运行 GEO 诊断"


@pytest.mark.integration
def test_ai_first_content_versions_quality_gate_and_exports(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf)
        brief = prepare_brief(client, csrf, client_id, tmp_path)

        created = client.post(
            f"/api/v1/clients/{client_id}/documents",
            headers={"X-CSRF-Token": csrf},
            json={"brief_id": brief["id"], "title": brief["title"]},
        )
        assert created.status_code == 201
        assert created.json()["data"]["status"] == "brief"
        document_id = created.json()["data"]["id"]
        assert created.json()["data"]["current_version"] is None

        run_content_worker(client, tmp_path)
        generated = client.get(f"/api/v1/documents/{document_id}").json()["data"]
        assert generated["status"] == "checked"
        assert generated["current_version"]["change_type"] == "generated"
        assert generated["current_version"]["provider"] == "rules"
        assert generated["current_version"]["model"] == "fixed-mock-v1"
        assert len(generated["current_version"]["title_candidates"]) >= 3
        assert (
            generated["current_version"]["title_candidates"][0]["title"]
            == generated["current_version"]["title"]
        )
        assert "莱恩美术" in generated["current_version"]["body_markdown"]
        assert "少儿美术培训" in generated["current_version"]["body_markdown"]
        assert "[来源:" not in generated["current_version"]["body_markdown"]
        assert "事实快照" not in generated["current_version"]["body_markdown"]
        assert "AI 平台" not in generated["current_version"]["body_markdown"]
        assert "GEO" not in generated["current_version"]["body_markdown"]
        assert generated["latest_check"]["overall_status"] != "blocked"
        generated_version = generated["current_version"]

        unsupported_claim = client.patch(
            f"/api/v1/documents/{document_id}",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": generated["version"],
                "title": f"{generated['title']}，成立于2010年并拥有100名教师",
                "body_markdown": generated_version["body_markdown"],
                "save_reason": "验证标题无依据数字阻断",
            },
        )
        assert unsupported_claim.status_code == 200
        unsupported = unsupported_claim.json()["data"]
        assert unsupported["status"] == "blocked"
        assert any(
            "2010年" in item["message"] and "100名" in item["message"]
            for item in unsupported["latest_check"]["findings"]
        )

        edited = client.patch(
            f"/api/v1/documents/{document_id}",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": unsupported["version"],
                "title": generated["title"],
                "body_markdown": "# 被改坏的内容\n\n莱恩美术最好。",
                "save_reason": "验证事实阻断",
            },
        )
        assert edited.status_code == 200
        blocked = edited.json()["data"]
        assert blocked["status"] == "blocked"
        assert blocked["latest_check"]["overall_status"] == "blocked"
        assert any(item["category"] == "compliance" for item in blocked["latest_check"]["findings"])
        blocked_export = client.post(
            f"/api/v1/documents/{document_id}/operations",
            headers={
                "X-CSRF-Token": csrf,
                "Idempotency-Key": str(uuid4()),
            },
            json={
                "operation": "export",
                "source_version_id": blocked["current_version"]["id"],
                "format": "markdown",
                "include_sources": True,
            },
        )
        assert blocked_export.status_code == 422

        restored = client.post(
            (f"/api/v1/documents/{document_id}/versions/{generated_version['id']}/restore"),
            headers={"X-CSRF-Token": csrf},
            json={
                "document_version": blocked["version"],
                "reason": "恢复事实正确的 AI 初稿",
            },
        )
        assert restored.status_code == 201
        restored_data = restored.json()["data"]
        assert restored_data["current_version"]["change_type"] == "restored"
        assert restored_data["latest_check"]["overall_status"] != "blocked"

        versions = client.get(
            f"/api/v1/documents/{document_id}/versions",
        ).json()["data"]
        assert versions["total"] == 4
        assert [item["version_number"] for item in versions["items"]] == [4, 3, 2, 1]

        export_jobs: list[str] = []
        for format_name in ("markdown", "docx"):
            accepted = client.post(
                f"/api/v1/documents/{document_id}/operations",
                headers={
                    "X-CSRF-Token": csrf,
                    "Idempotency-Key": str(uuid4()),
                },
                json={
                    "operation": "export",
                    "source_version_id": restored_data["current_version"]["id"],
                    "format": format_name,
                    "include_sources": True,
                },
            )
            assert accepted.status_code == 202
            export_jobs.append(accepted.json()["data"]["job_id"])
            run_content_worker(client, tmp_path)

        downloads = []
        for job_id in export_jobs:
            job = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
            assert job["status"] == "succeeded"
            assert job["result_resource_type"] == "export"
            response = client.get(
                f"/api/v1/exports/{job['result_resource_id']}/download",
            )
            assert response.status_code == 200
            downloads.append(response)
        assert "莱恩美术".encode() in downloads[0].content
        assert "text/markdown" in downloads[0].headers["content-type"]
        assert downloads[1].content.startswith(b"PK")
        assert "wordprocessingml.document" in downloads[1].headers["content-type"]


@pytest.mark.integration
def test_generated_article_has_previewable_and_downloadable_cover(tmp_path: Path) -> None:
    with build_client(tmp_path, model_execution_mode="fixed_mock") as client:
        csrf = login(client)
        client_id = create_customer(client, csrf)
        brief = prepare_brief(client, csrf, client_id, tmp_path)
        created = client.post(
            f"/api/v1/clients/{client_id}/documents",
            headers={"X-CSRF-Token": csrf},
            json={"brief_id": brief["id"], "title": brief["title"]},
        )
        assert created.status_code == 201
        document_id = created.json()["data"]["id"]
        run_content_worker(client, tmp_path)
        generated = client.get(f"/api/v1/documents/{document_id}").json()["data"]
        version_id = generated["current_version"]["id"]

        style_payloads: list[bytes] = []
        for style in ("azure", "sunrise", "mint"):
            preview = client.get(
                f"/api/v1/documents/{document_id}/versions/{version_id}/cover",
                params={"style": style},
            )
            assert preview.status_code == 200
            assert preview.headers["content-type"] == "image/png"
            assert preview.content.startswith(b"\x89PNG\r\n\x1a\n")
            style_payloads.append(preview.content)

        assert len(set(style_payloads)) == 3
        downloaded = client.get(
            f"/api/v1/documents/{document_id}/versions/{version_id}/cover",
            params={"style": "azure", "download": "true"},
        )
        assert downloaded.status_code == 200
        assert "attachment" in downloaded.headers["content-disposition"]
        assert downloaded.headers["content-disposition"].endswith(".png")

        invalid_style = client.get(
            f"/api/v1/documents/{document_id}/versions/{version_id}/cover",
            params={"style": "unknown"},
        )
        assert invalid_style.status_code == 400
        missing_version = client.get(
            f"/api/v1/documents/{document_id}/versions/{uuid4()}/cover",
        )
        assert missing_version.status_code == 404


@pytest.mark.integration
def test_document_create_rejects_unowned_brief_and_manual_blank_draft(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        first_id = create_customer(client, csrf)
        brief = prepare_brief(client, csrf, first_id, tmp_path)
        second_id = str(uuid4())
        rejected = client.post(
            f"/api/v1/clients/{second_id}/documents",
            headers={"X-CSRF-Token": csrf},
            json={"brief_id": brief["id"], "title": brief["title"]},
        )
        assert rejected.status_code == 422

        created = client.post(
            f"/api/v1/clients/{first_id}/documents",
            headers={"X-CSRF-Token": csrf},
            json={"brief_id": brief["id"], "title": brief["title"]},
        )
        document = created.json()["data"]
        manual = client.patch(
            f"/api/v1/documents/{document['id']}",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": document["version"],
                "title": document["title"],
                "body_markdown": "人工空白草稿",
                "save_reason": "不应允许",
            },
        )
        assert manual.status_code == 422

        run_content_worker(client, tmp_path)
        assert (
            client.get(
                f"/api/v1/clients/{first_id}/documents",
            ).json()["data"]["total"]
            == 1
        )


@pytest.mark.integration
def test_recheck_updates_quality_without_rewriting_article_version(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path, publishing_execution_mode="fixed_mock") as client:
        csrf = login(client)
        client_id = create_customer(client, csrf)
        brief = prepare_brief(client, csrf, client_id, tmp_path)
        created = client.post(
            f"/api/v1/clients/{client_id}/documents",
            headers={"X-CSRF-Token": csrf},
            json={"brief_id": brief["id"], "title": brief["title"]},
        ).json()["data"]
        run_content_worker(client, tmp_path)
        generated = client.get(
            f"/api/v1/documents/{created['id']}",
        ).json()["data"]
        adapted = client.post(
            f"/api/v1/documents/{created['id']}/operations",
            headers={
                "X-CSRF-Token": csrf,
                "Idempotency-Key": str(uuid4()),
            },
            json={
                "operation": "channel_variant",
                "source_version_id": generated["current_version"]["id"],
                "channel_ids": ["toutiao"],
            },
        )
        assert adapted.status_code == 202
        run_content_worker(client, tmp_path)
        generated = client.get(
            f"/api/v1/documents/{created['id']}",
        ).json()["data"]
        publishing_channels = client.get("/api/v1/publishing/channels").json()["data"]["items"]
        toutiao_accounts = next(item for item in publishing_channels if item["id"] == "toutiao")[
            "accounts"
        ]
        toutiao_account = (
            toutiao_accounts[0]
            if toutiao_accounts
            else client.post(
                "/api/v1/publishing/channels/toutiao/accounts",
                headers={"X-CSRF-Token": csrf},
                json={"display_name": "复检测试账号"},
            ).json()["data"]
        )
        tested_account = client.post(
            f"/api/v1/publishing/accounts/{toutiao_account['id']}/test",
            headers={"X-CSRF-Token": csrf},
        ).json()["data"]
        client.patch(
            f"/api/v1/publishing/accounts/{toutiao_account['id']}",
            headers={"X-CSRF-Token": csrf},
            json={"enabled": True, "version": tested_account["version"]},
        )
        published_response = client.post(
            f"/api/v1/documents/{created['id']}/publish",
            headers={
                "X-CSRF-Token": csrf,
                "Idempotency-Key": str(uuid4()),
            },
            json={
                "version": generated["version"],
                "account_ids": [toutiao_account["id"]],
            },
        )
        assert published_response.status_code == 202
        run_content_worker(client, tmp_path)
        published = client.get(
            f"/api/v1/documents/{created['id']}",
        ).json()["data"]
        source_version = published["current_version"]
        versions_before = client.get(
            f"/api/v1/documents/{created['id']}/versions?page=1&page_size=100",
        ).json()["data"]["items"]
        checks_before = client.get(
            f"/api/v1/documents/{created['id']}/quality-checks?page=1&page_size=100",
        ).json()["data"]["items"]

        accepted = client.post(
            f"/api/v1/documents/{created['id']}/operations",
            headers={
                "X-CSRF-Token": csrf,
                "Idempotency-Key": str(uuid4()),
            },
            json={
                "operation": "check",
                "source_version_id": source_version["id"],
            },
        )
        assert accepted.status_code == 202
        run_content_worker(client, tmp_path)

        rechecked = client.get(
            f"/api/v1/documents/{created['id']}",
        ).json()["data"]
        versions_after = client.get(
            f"/api/v1/documents/{created['id']}/versions?page=1&page_size=100",
        ).json()["data"]["items"]
        checks_after = client.get(
            f"/api/v1/documents/{created['id']}/quality-checks?page=1&page_size=100",
        ).json()["data"]["items"]
        assert rechecked["current_version"]["id"] == source_version["id"]
        assert rechecked["current_version"]["body_markdown"] == source_version["body_markdown"]
        assert rechecked["status"] == "published"
        assert rechecked["current_version_published"] is True
        assert len(versions_after) == len(versions_before)
        assert len(checks_after) == len(checks_before) + 1
        assert checks_after[0]["document_version_id"] == source_version["id"]


@pytest.mark.integration
def test_channel_variants_are_checked_and_exportable(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf)
        upload_enterprise_images(client, csrf, client_id, count=2)
        brief = prepare_brief(client, csrf, client_id, tmp_path)
        created = client.post(
            f"/api/v1/clients/{client_id}/documents",
            headers={"X-CSRF-Token": csrf},
            json={"brief_id": brief["id"], "title": brief["title"]},
        ).json()["data"]
        run_content_worker(client, tmp_path)
        generated = client.get(
            f"/api/v1/documents/{created['id']}",
        ).json()["data"]
        channel_ids = ["baijia", "sohu", "toutiao", "penguin"]

        accepted = client.post(
            f"/api/v1/documents/{created['id']}/operations",
            headers={
                "X-CSRF-Token": csrf,
                "Idempotency-Key": str(uuid4()),
            },
            json={
                "operation": "channel_variant",
                "source_version_id": generated["current_version"]["id"],
                "channel_ids": channel_ids,
            },
        )
        assert accepted.status_code == 202
        run_content_worker(client, tmp_path)

        adapted = client.get(
            f"/api/v1/documents/{created['id']}",
        ).json()["data"]
        assert adapted["current_version"]["change_type"] == "channel_variant"
        assert adapted["latest_check"]["overall_status"] != "blocked"
        assert {item["channel_id"] for item in adapted["channel_variants"]} == set(
            channel_ids,
        )
        versions = client.get(
            f"/api/v1/documents/{created['id']}/versions?page=1&page_size=100",
        ).json()["data"]["items"]
        versions_by_id = {
            item["id"]: item for item in versions if item["change_type"] == "channel_variant"
        }
        variants_by_channel = {
            item["channel_id"]: versions_by_id[item["version_id"]]
            for item in adapted["channel_variants"]
        }
        variant_bodies = [
            variants_by_channel[channel_id]["body_markdown"] for channel_id in channel_ids
        ]
        assert len(set(variant_bodies)) == 4
        assert any("本地信息速览" in item for item in variant_bodies)
        assert any("快速摘要" in item for item in variant_bodies)
        assert any("从一个具体问题说起" in item for item in variant_bodies)
        assert all("30 秒" not in item for item in variant_bodies)
        assert variants_by_channel["toutiao"]["title"].startswith(
            "即墨区少儿美术培训怎么选？",
        )
        assert "核验指南怎么" not in variants_by_channel["toutiao"]["title"]
        assert all(
            "三十秒速读" not in (item["title"] + item["body_markdown"])
            for item in variants_by_channel.values()
        )
        assert all(
            "先看结论与判断依据" not in item["title"] for item in variants_by_channel.values()
        )
        assert all(len(item["title_candidates"]) >= 3 for item in variants_by_channel.values())
        checks = client.get(
            f"/api/v1/documents/{created['id']}/quality-checks?page=1&page_size=100",
        ).json()["data"]["items"]
        checks_by_version = {item["document_version_id"]: item for item in checks}
        assert all(
            checks_by_version[item["id"]]["overall_status"] != "blocked"
            for item in variants_by_channel.values()
        )
        for _channel_id, version in variants_by_channel.items():
            export = client.post(
                f"/api/v1/documents/{created['id']}/operations",
                headers={
                    "X-CSRF-Token": csrf,
                    "Idempotency-Key": str(uuid4()),
                },
                json={
                    "operation": "export",
                    "source_version_id": version["id"],
                    "format": "markdown",
                    "include_sources": True,
                },
            )
            assert export.status_code == 202
            run_content_worker(client, tmp_path)
            job = client.get(
                f"/api/v1/jobs/{export.json()['data']['job_id']}",
            ).json()["data"]
            assert job["status"] == "succeeded"
            downloaded = client.get(
                f"/api/v1/exports/{job['result_resource_id']}/download",
            )
            assert downloaded.status_code == 200
            rendered = downloaded.content.decode()
            assert rendered.startswith(f"# {version['title']}")
            assert "本次适配渠道：" not in rendered

        baijia = variants_by_channel["baijia"]
        before_edit = client.get(
            f"/api/v1/documents/{created['id']}",
        ).json()["data"]
        edited = client.patch(
            f"/api/v1/documents/{created['id']}",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": before_edit["version"],
                "title": "即墨区少儿美术培训怎么选？渠道校对版",
                "body_markdown": (
                    baijia["body_markdown"] + "\n\n发布前请再次核对企业最新公开信息。"
                ),
                "save_reason": "运营人员校对百家号渠道成品",
                "source_version_id": baijia["id"],
                "channel_id": "baijia",
            },
        )
        assert edited.status_code == 200
        edited_data = edited.json()["data"]
        assert edited_data["current_version"]["provider"] == "user"
        assert edited_data["current_version"]["change_type"] == "channel_variant"
        assert (
            next(
                item for item in edited_data["channel_variants"] if item["channel_id"] == "baijia"
            )["version_id"]
            == edited_data["current_version"]["id"]
        )

        repeated = client.post(
            f"/api/v1/documents/{created['id']}/operations",
            headers={
                "X-CSRF-Token": csrf,
                "Idempotency-Key": str(uuid4()),
            },
            json={
                "operation": "channel_variant",
                "source_version_id": edited_data["current_version"]["id"],
                "channel_ids": ["toutiao"],
            },
        )
        assert repeated.status_code == 202
        run_content_worker(client, tmp_path)
        repeated_data = client.get(
            f"/api/v1/documents/{created['id']}",
        ).json()["data"]
        assert repeated_data["current_version"]["title"].startswith(
            "即墨区少儿美术培训怎么选？",
        )
        assert "先看这些已确认信息" not in repeated_data["current_version"]["title"]


@pytest.mark.integration
def test_second_channel_failure_leaves_no_partial_versions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf)
        upload_enterprise_images(client, csrf, client_id)
        brief = prepare_brief(client, csrf, client_id, tmp_path)
        created = client.post(
            f"/api/v1/clients/{client_id}/documents",
            headers={"X-CSRF-Token": csrf},
            json={"brief_id": brief["id"], "title": brief["title"]},
        ).json()["data"]
        run_content_worker(client, tmp_path)
        generated = client.get(
            f"/api/v1/documents/{created['id']}",
        ).json()["data"]
        review_calls = 0

        async def fail_second_review(
            *args: object,
            **kwargs: object,
        ) -> tuple[str, str, list[dict[str, object]]]:
            nonlocal review_calls
            del args, kwargs
            review_calls += 1
            if review_calls == 2:
                raise ApiFailure(
                    status_code=502,
                    code=50201,
                    message="第二渠道复核失败",
                    retryable=False,
                )
            return "rules", "deterministic-v1", []

        monkeypatch.setattr(
            content_module,
            "_independent_review",
            fail_second_review,
        )
        accepted = client.post(
            f"/api/v1/documents/{created['id']}/operations",
            headers={
                "X-CSRF-Token": csrf,
                "Idempotency-Key": str(uuid4()),
            },
            json={
                "operation": "channel_variant",
                "source_version_id": generated["current_version"]["id"],
                "channel_ids": ["toutiao", "sohu"],
            },
        )
        assert accepted.status_code == 202
        run_content_worker(client, tmp_path)

        failed_job = client.get(
            f"/api/v1/jobs/{accepted.json()['data']['job_id']}",
        ).json()["data"]
        assert failed_job["status"] == "failed"
        after_failure = client.get(
            f"/api/v1/documents/{created['id']}",
        ).json()["data"]
        assert after_failure["current_version"]["id"] == generated["current_version"]["id"]
        assert after_failure["channel_variants"] == []
        versions = client.get(
            f"/api/v1/documents/{created['id']}/versions?page=1&page_size=100",
        ).json()["data"]["items"]
        assert [item["change_type"] for item in versions] == ["generated"]


@pytest.mark.integration
def test_unexpected_content_failure_retries_then_updates_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf)
        brief = prepare_brief(client, csrf, client_id, tmp_path)
        created = client.post(
            f"/api/v1/clients/{client_id}/documents",
            headers={"X-CSRF-Token": csrf},
            json={"brief_id": brief["id"], "title": brief["title"]},
        ).json()["data"]

        def fail_draft(*args: object, **kwargs: object) -> str:
            del args, kwargs
            raise OSError("simulated local writer failure")

        monkeypatch.setattr("app.content._build_fixed_mock_draft", fail_draft)
        for expected_status in ("generating", "generating", "failed"):
            run_content_worker(client, tmp_path)
            document = client.get(
                f"/api/v1/documents/{created['id']}",
            ).json()["data"]
            assert document["status"] == expected_status

        application = cast(FastAPI, client.app)

        async def job_state() -> tuple[str, int, str | None]:
            async with application.state.session_factory() as database:
                job = await database.scalar(
                    select(Job).where(
                        Job.job_type == "document_operation",
                        Job.client_id == UUID(client_id),
                    ),
                )
                assert job is not None
                return job.status, job.attempts, job.error_message

        status, attempts, message = asyncio.run(job_state())
        assert (status, attempts) == ("failed", 3)
        assert message == "内容处理暂时失败"


@pytest.mark.integration
def test_live_primary_writer_records_exact_model_and_uses_lightweight_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encoded_master = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    master = SecretStr(encoded_master)
    calls: list[str] = []
    writer_user_prompts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        model = str(payload["model"])
        calls.append(model)
        if model == "deepseek-v4-pro":
            writer_user_prompts.append(str(payload["messages"][-1]["content"]))
        if model == "deepseek-v4-pro" and len(calls) == 1:
            content = json.dumps(
                {
                    "outline_markdown": (
                        "# 即墨少儿美术\n\n## 直接回答\n\n## 服务与人群\n\n"
                        "## 选择条件\n\n## 常见问题\n\n## 来源"
                    ),
                },
                ensure_ascii=False,
            )
        elif model == "deepseek-v4-pro" and len(calls) == 2:
            content = json.dumps(
                {
                    "title": "莱恩美术全市第一",
                    "body_markdown": (
                        "# 莱恩美术全市第一\n\n"
                        "莱恩美术是全市第一，也是即墨家长最好的选择。"
                        "这里反复强调机构最好、效果最佳和绝对领先，"
                        "没有提供可核验的选择方法、适用边界或家长能够实际使用的信息。\n\n"
                        "## 结论\n\n莱恩美术值得所有家长优先选择。"
                    ),
                },
                ensure_ascii=False,
            )
        elif model == "deepseek-v4-pro":
            content = json.dumps(
                {
                    "title": "即墨少儿美术培训怎么了解？",
                    "body_markdown": (
                        "# 即墨少儿美术培训怎么了解？\n\n"
                        "莱恩美术在即墨区提供少儿美术培训，"
                        "适用客群为即墨区 4—12 岁儿童及家长。\n\n"
                        "## 直接回答\n\n先核对服务、人群和公开来源。\n\n"
                        "莱恩美术可以作为本地了解对象。"
                        "咨询莱恩美术时可以先核对课程安排。"
                        "到莱恩美术试听时可以观察课堂互动。"
                        "是否选择莱恩美术仍要结合孩子的实际体验。\n\n"
                        "## 常见问题\n\n### 咨询前看什么？\n\n"
                        "确认服务范围、最新安排和适用条件。\n\n"
                        "## 来源\n\n本文只使用已确认并获准公开的企业事实。"
                    ),
                },
                ensure_ascii=False,
            )
        else:
            raise AssertionError(f"unexpected fallback model call: {model}")
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 80},
            },
        )

    transport = httpx.MockTransport(handler)
    with build_client(
        tmp_path,
        app_master_key=master,
        provider_transport=transport,
    ) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf)
        brief = prepare_brief(client, csrf, client_id, tmp_path)
        created = client.post(
            f"/api/v1/clients/{client_id}/documents",
            headers={"X-CSRF-Token": csrf},
            json={"brief_id": brief["id"], "title": brief["title"]},
        )
        document_id = created.json()["data"]["id"]
        application = cast(FastAPI, client.app)

        async def configure_and_run() -> None:
            cipher = SecretCipher(encoded_master)
            async with application.state.session_factory() as database:
                database.add_all(
                    [
                        ProviderSetting(
                            provider="qwen",
                            enabled=True,
                            base_url=("https://dashscope.aliyuncs.com/compatible-mode/v1"),
                            writer_model="qwen3.7-plus",
                            reviewer_model=None,
                            fallback_model=None,
                            daily_budget_cny_fen=1_000,
                            timeout_seconds=30,
                            encrypted_api_key=cipher.encrypt("qwen", "qwen-test-key"),
                            secret_suffix="-key",
                            last_test_status="success",
                        ),
                        ProviderSetting(
                            provider="deepseek",
                            enabled=True,
                            base_url="https://api.deepseek.com/v1",
                            writer_model=None,
                            reviewer_model="deepseek-v4-pro",
                            fallback_model="deepseek-v4-flash",
                            daily_budget_cny_fen=1_000,
                            timeout_seconds=30,
                            encrypted_api_key=cipher.encrypt(
                                "deepseek",
                                "deepseek-test-key",
                            ),
                            secret_suffix="-key",
                            last_test_status="success",
                        ),
                    ],
                )
                await database.commit()
            job = await claim_next_job(application.state.session_factory)
            assert job is not None
            settings = Settings(
                app_env="test",
                db_password=SecretStr("unused"),
                storage_root=tmp_path,
                app_master_key=master,
                model_execution_mode="live",
            )
            await process_content_job(
                application.state.session_factory,
                job,
                settings,
                ProviderClient(transport),
            )
            async with application.state.session_factory() as database:
                completed_job = await database.get(Job, job.id)
                assert completed_job is not None
                assert completed_job.status == "succeeded", completed_job.error_message

        asyncio.run(configure_and_run())
        document = client.get(f"/api/v1/documents/{document_id}").json()["data"]
        assert document["status"] == "checked"
        assert document["current_version"]["body_markdown"].count("莱恩美术") <= 3
        assert document["current_version"]["provider"] == "deepseek"
        assert document["current_version"]["model"] == "deepseek-v4-pro"
        assert document["latest_check"]["provider"] == "rules"
        assert document["latest_check"]["model"] == "lightweight-publish-check-v1"
        assert calls == ["deepseek-v4-pro", "deepseek-v4-pro", "deepseek-v4-pro"]
        assert len(writer_user_prompts) == 3
        assert all("client:" not in prompt for prompt in writer_user_prompts)
        assert all('"fact_id"' not in prompt for prompt in writer_user_prompts)
        assert all(
            not content_module.INTERNAL_IDENTIFIER_PATTERN.search(prompt)
            for prompt in writer_user_prompts
        )

        manual = client.patch(
            f"/api/v1/documents/{document_id}",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": document["version"],
                "title": "莱恩美术全市第一",
                "body_markdown": document["current_version"]["body_markdown"],
                "save_reason": "验证人工编辑后的轻量发布检查",
            },
        )
        assert manual.status_code == 200
        manual_data = manual.json()["data"]
        assert manual_data["status"] == "blocked"
        assert manual_data["latest_check"]["provider"] == "rules"
        assert any(
            item["category"] == "compliance" and item["severity"] == "blocking"
            for item in manual_data["latest_check"]["findings"]
        )
        assert calls == ["deepseek-v4-pro", "deepseek-v4-pro", "deepseek-v4-pro"]

        async def usage_rows() -> list[ModelUsage]:
            async with application.state.session_factory() as database:
                return list(
                    (
                        await database.scalars(
                            select(ModelUsage).order_by(ModelUsage.created_at),
                        )
                    ).all(),
                )

        rows = asyncio.run(usage_rows())
        assert [item.purpose for item in rows] == [
            "content_outline",
            "content_draft",
            "content_draft_repair_1",
        ]
        assert all(item.status == "succeeded" for item in rows)
        assert all(item.input_tokens == 120 for item in rows)
        assert all(item.fact_snapshot_id is not None for item in rows)
        assert all(item.prompt_version == content_module.PROMPT_VERSION for item in rows)
        assert all(item.pricing_version == PRICING_VERSION for item in rows)

        versions_before = client.get(
            f"/api/v1/documents/{document_id}/versions?page=1&page_size=100",
        ).json()["data"]["items"]

        async def fail_quality_check(*args: object, **kwargs: object) -> None:
            del args, kwargs
            raise RuntimeError("quality persistence failed")

        monkeypatch.setattr(
            content_module,
            "_run_quality_check",
            fail_quality_check,
        )
        failed_save = client.patch(
            f"/api/v1/documents/{document_id}",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": manual_data["version"],
                "title": manual_data["title"],
                "body_markdown": (
                    manual_data["current_version"]["body_markdown"] + "\n\n仅用于验证事务回滚。"
                ),
                "save_reason": "验证复核后质量持久化失败时不产生孤立版本",
            },
        )
        assert failed_save.status_code == 500
        monkeypatch.undo()

        after_failure = client.get(
            f"/api/v1/documents/{document_id}",
        ).json()["data"]
        versions_after = client.get(
            f"/api/v1/documents/{document_id}/versions?page=1&page_size=100",
        ).json()["data"]["items"]
        assert after_failure["current_version"]["id"] == manual_data["current_version"]["id"]
        assert len(versions_after) == len(versions_before)
