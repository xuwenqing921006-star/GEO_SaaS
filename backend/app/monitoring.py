from __future__ import annotations

import math
import re
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
from typing import Annotated, Literal, TypedDict, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, Query, Request, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth import Authenticated, CsrfAuthenticated
from app.config import Settings
from app.database import (
    Client,
    DatabaseSession,
    Fact,
    Job,
    MonitoringBatch,
    MonitoringEvaluation,
    MonitoringFeedback,
    MonitoringQuestionSet,
    MonitoringSample,
    OptimizationAction,
    ProviderSetting,
    StrategyItem,
    utc_now,
)
from app.providers import (
    PROVIDER_OFFICIAL_HOSTS,
    ProviderClient,
    ProviderName,
    SecretCipher,
    finalize_model_usage,
    reserve_model_budget,
)
from app.responses import ApiFailure, error_response, success_response

CATALOG_VERSION = "2026.07.29-2"
CATALOG_VERIFIED_ON = date(2026, 7, 29)
QuestionFamily = Literal[
    "category_discovery",
    "recommendation",
    "scenario",
    "comparison",
    "brand_verification",
]
PlatformMode = Literal["api", "manual_consumer"]
PlatformPriority = Literal["P0", "P1"]

KEYWORD_MONITORING_FAMILY: dict[str, QuestionFamily] = {
    "brand": "brand_verification",
    "trust": "brand_verification",
    "recommendation": "recommendation",
    "decision": "recommendation",
    "scenario": "scenario",
    "comparison": "comparison",
    "transaction": "comparison",
    "core": "category_discovery",
    "service": "category_discovery",
    "geo_longtail": "category_discovery",
    "local_service": "category_discovery",
    "service_detail": "category_discovery",
}


class PlatformEntry(TypedDict):
    id: str
    name: str
    mode: PlatformMode
    priority: PlatformPriority
    provider: ProviderName | None
    consumer_entry_url: str
    sample_count_default: int
    active: bool
    note: str


PLATFORM_CATALOG: tuple[PlatformEntry, ...] = (
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "mode": "api",
        "priority": "P0",
        "provider": "deepseek",
        "consumer_entry_url": "https://chat.deepseek.com/",
        "sample_count_default": 2,
        "active": True,
        "note": "API 样本用于持续跟踪，不等同于消费者端应用回答。",
    },
    {
        "id": "doubao",
        "name": "豆包",
        "mode": "api",
        "priority": "P0",
        "provider": "doubao",
        "consumer_entry_url": "https://www.doubao.com/chat/",
        "sample_count_default": 1,
        "active": True,
        "note": "通过火山方舟官方 API 自动检测，不等同于豆包消费者端完整回答。",
    },
    {
        "id": "qwen",
        "name": "通义千问",
        "mode": "api",
        "priority": "P0",
        "provider": "qwen",
        "consumer_entry_url": "https://www.qianwen.com/",
        "sample_count_default": 2,
        "active": True,
        "note": "API 样本用于持续跟踪，不等同于消费者端应用回答。",
    },
)
PLATFORMS_BY_ID = {item["id"]: item for item in PLATFORM_CATALOG}
MONITORING_PROMPT_VERSION = "monitoring-v1"
MONITORING_PRICING_VERSION = "budget-ceiling-v1-2026-07-27"
MONITORING_BUDGET_RATES = {
    "qwen": (200, 800),
    "deepseek": (400, 1600),
    "doubao": (400, 1600),
}


def _model_cost_cny_fen(
    provider: ProviderName,
    input_tokens: int,
    output_tokens: int,
) -> int:
    input_rate, output_rate = MONITORING_BUDGET_RATES[provider]
    weighted = input_tokens * input_rate + output_tokens * output_rate
    return max(1, math.ceil(weighted / 1_000_000))


def calculate_monitoring_metrics(
    samples: list[dict[str, object]],
) -> dict[str, object]:
    def metric(rows: list[dict[str, object]], field: str) -> dict[str, int | float | None]:
        denominator = len(rows)
        numerator = sum(row.get(field) is True for row in rows)
        return {
            "numerator": numerator,
            "denominator": denominator,
            "rate": round(numerator * 100 / denominator, 2) if denominator else None,
        }

    def summary(rows: list[dict[str, object]]) -> dict[str, object]:
        effective = [row for row in rows if row.get("status") == "succeeded"]
        evaluated = [row for row in effective if row.get("brand_found") is not None]
        non_brand = [row for row in evaluated if row.get("is_brand_query") is not True]
        brand_mentions = [row for row in evaluated if row.get("brand_found") is True]
        supported = [
            row
            for row in evaluated
            if row.get("recommended") is True and row.get("recommendation_supported") is not None
        ]
        fact_checked = [row for row in evaluated if row.get("facts_accurate") is not None]
        repeat_groups: dict[str, list[dict[str, object]]] = {}
        for row in non_brand:
            if row.get("priority") != 1:
                continue
            question_id = row.get("question_id")
            if not isinstance(question_id, str):
                continue
            repeat_groups.setdefault(question_id, []).append(row)
        repeated = [group for group in repeat_groups.values() if len(group) >= 2]
        repeat_numerator = sum(
            sum(row.get("brand_found") is True for row in group) >= 2 for group in repeated
        )
        details = {
            "discovery": metric(non_brand, "brand_found"),
            "brand_mention": metric(evaluated, "brand_found"),
            "correct_association": metric(brand_mentions, "correctly_associated"),
            "recommendation": metric(non_brand, "recommended"),
            "recommendation_supported": metric(supported, "recommendation_supported"),
            "fact_accuracy": metric(fact_checked, "facts_accurate"),
            "source_coverage": metric(evaluated, "source_visible"),
            "repeat_appearance": {
                "numerator": repeat_numerator,
                "denominator": len(repeated),
                "rate": (round(repeat_numerator * 100 / len(repeated), 2) if repeated else None),
            },
        }
        return {
            "sample_count": len(rows),
            "effective_sample_count": len(effective),
            "failed_count": sum(row.get("status") == "failed" for row in rows),
            "not_executed_count": sum(row.get("status") == "not_executed" for row in rows),
            "brand_found_rate": details["discovery"]["rate"],
            "correct_association_rate": details["correct_association"]["rate"],
            "recommendation_rate": details["recommendation"]["rate"],
            "recommendation_supported_rate": details["recommendation_supported"]["rate"],
            "fact_accuracy_rate": details["fact_accuracy"]["rate"],
            "source_coverage_rate": details["source_coverage"]["rate"],
            "repeat_appearance_rate": details["repeat_appearance"]["rate"],
            "metric_details": details,
        }

    result = summary(samples)
    modes = sorted(
        {
            str(sample["collection_mode"])
            for sample in samples
            if sample.get("collection_mode") in {"api", "manual_consumer"}
        },
    )
    result["mode_breakdown"] = {
        mode: summary([sample for sample in samples if sample.get("collection_mode") == mode])
        for mode in modes
    }
    if len(modes) > 1:
        for field in (
            "brand_found_rate",
            "correct_association_rate",
            "recommendation_rate",
            "recommendation_supported_rate",
            "fact_accuracy_rate",
            "source_coverage_rate",
            "repeat_appearance_rate",
        ):
            result[field] = None
        metric_details = cast(dict[str, dict[str, int | float | None]], result["metric_details"])
        for detail in metric_details.values():
            detail["numerator"] = None
            detail["denominator"] = None
            detail["rate"] = None
    return result


class QuestionInput(BaseModel):
    id: str | None = Field(default=None, max_length=100)
    text: str = Field(min_length=2, max_length=500)
    family: QuestionFamily
    is_brand_query: bool = False
    target_level: Literal["L1", "L2", "L3"] = "L2"
    priority: int = Field(default=1, ge=1, le=9)


class QuestionSetCreateInput(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    frozen: bool = False
    questions: list[QuestionInput] = Field(min_length=1, max_length=50)


class QuestionSetPatchInput(BaseModel):
    version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=2, max_length=200)
    frozen: bool | None = None
    questions: list[QuestionInput] | None = Field(default=None, min_length=1, max_length=50)


class BatchCreateInput(BaseModel):
    question_set_id: UUID
    platform_ids: list[str] = Field(min_length=1, max_length=10)
    api_sample_count: int = Field(default=1, ge=1, le=5)
    manual_placeholders: bool = True


class ManualSampleInput(BaseModel):
    sample_id: UUID
    status: Literal["succeeded", "failed"]
    raw_answer: str | None = Field(default=None, max_length=50_000)
    failure_reason: str | None = Field(default=None, max_length=500)
    asked_at: datetime

    @model_validator(mode="after")
    def validate_status_payload(self) -> ManualSampleInput:
        if self.status == "succeeded" and not (self.raw_answer or "").strip():
            raise ValueError("successful sample requires raw_answer")
        if self.status == "failed" and not (self.failure_reason or "").strip():
            raise ValueError("failed sample requires failure_reason")
        return self


class ManualSamplesInput(BaseModel):
    items: list[ManualSampleInput] = Field(min_length=1, max_length=50)


class EvaluationInput(BaseModel):
    version: int | None = Field(default=None, ge=1)
    brand_found: bool
    correctly_associated: bool
    recommended: bool
    recommendation_supported: bool | None = None
    facts_accurate: bool | None = None
    source_visible: bool = False
    mentioned_name: str | None = Field(default=None, max_length=200)
    reasons: list[str] = Field(default_factory=list, max_length=20)
    incorrect_facts: list[dict[str, object]] = Field(default_factory=list, max_length=20)
    visible_sources: list[dict[str, object]] = Field(default_factory=list, max_length=20)
    note: str | None = Field(default=None, max_length=1000)


class FeedbackInput(BaseModel):
    action_type: Literal[
        "add_fact_task",
        "add_content_brief",
        "update_channel_priority",
        "increase_sample",
    ]
    reason: str = Field(min_length=2, max_length=1000)
    target_page: Literal["P02", "P04", "P06", "P07"]


def _platform_data(platform: PlatformEntry) -> dict[str, object]:
    return {
        **platform,
        "verified_on": CATALOG_VERIFIED_ON.isoformat(),
        "mode_label": "API 自动采样" if platform["mode"] == "api" else "消费者端人工采样",
    }


def _question_set_data(question_set: MonitoringQuestionSet) -> dict[str, object]:
    return {
        "id": str(question_set.id),
        "client_id": str(question_set.client_id),
        "name": question_set.name,
        "frozen": question_set.frozen,
        "questions": question_set.questions,
        "version": question_set.version,
        "created_at": question_set.created_at.isoformat(),
        "updated_at": question_set.updated_at.isoformat(),
    }


async def _questions_are_confirmed_strategy(
    database: AsyncSession,
    client_id: UUID,
    questions: list[QuestionInput],
) -> bool:
    try:
        item_ids = [UUID(question.id) for question in questions if question.id]
    except ValueError:
        return False
    if len(item_ids) != len(questions) or len(set(item_ids)) != len(item_ids):
        return False
    items = list(
        (
            await database.scalars(
                select(StrategyItem).where(
                    StrategyItem.client_id == client_id,
                    StrategyItem.id.in_(item_ids),
                    StrategyItem.active.is_(True),
                ),
            )
        ).all(),
    )
    if len(items) != len(questions):
        return False
    by_id = {item.id: item for item in items}
    family_map = {"category_discovery": "discovery"}
    for question in questions:
        item = by_id.get(UUID(question.id or ""))
        if item is None or item.text.strip() != question.text.strip():
            return False
        if item.kind == "question":
            expected_family = cast(
                QuestionFamily | None,
                (
                    "category_discovery"
                    if item.family == family_map["category_discovery"]
                    else item.family
                ),
            )
            is_confirmed = item.locked
        elif item.kind == "keyword":
            expected_family = KEYWORD_MONITORING_FAMILY.get(item.keyword_type or "")
            is_confirmed = item.selected or item.locked
        else:
            return False
        expected_level = item.target_level if item.target_level in {"L1", "L2", "L3"} else "L2"
        if (
            not is_confirmed
            or expected_family is None
            or question.family != expected_family
            or question.target_level != expected_level
            or question.priority != item.priority
            or (expected_family == "brand_verification") != question.is_brand_query
        ):
            return False
    return True


async def lock_monitoring_question_set(
    database: AsyncSession,
    question_set_id: UUID,
) -> MonitoringQuestionSet | None:
    return cast(
        MonitoringQuestionSet | None,
        await database.scalar(
            select(MonitoringQuestionSet)
            .where(MonitoringQuestionSet.id == question_set_id)
            .with_for_update(),
        ),
    )


async def lock_monitoring_client(
    database: AsyncSession,
    client_id: UUID,
) -> Client | None:
    return cast(
        Client | None,
        await database.scalar(
            select(Client).where(Client.id == client_id).with_for_update(),
        ),
    )


async def _recalculate_batch_status(
    database: AsyncSession,
    batch: MonitoringBatch,
) -> None:
    statuses = list(
        (
            await database.scalars(
                select(MonitoringSample.status).where(
                    MonitoringSample.batch_id == batch.id,
                ),
            )
        ).all(),
    )
    if not statuses or all(status == "not_executed" for status in statuses):
        batch.status = "queued"
        batch.completed_at = None
    elif any(status == "not_executed" for status in statuses):
        batch.status = "partial"
        batch.completed_at = None
    elif all(status == "failed" for status in statuses):
        batch.status = "failed"
        batch.completed_at = utc_now()
    elif any(status == "failed" for status in statuses):
        batch.status = "partial"
        batch.completed_at = utc_now()
    else:
        batch.status = "succeeded"
        batch.completed_at = utc_now()


def _optimization_action_data(action: OptimizationAction) -> dict[str, object]:
    return {
        "id": str(action.id),
        "client_id": str(action.client_id),
        "source": action.source_type,
        "source_id": str(action.source_id),
        "action_type": action.action_type,
        "title": action.title,
        "reason": action.reason,
        "target_level": action.target_level,
        "target_page": action.target_page,
        "status": action.status,
        "created_at": action.created_at.isoformat(),
    }


def _evaluation_data(evaluation: MonitoringEvaluation) -> dict[str, object]:
    suggested_actions: list[dict[str, str]] = []
    if not evaluation.brand_found:
        suggested_actions.append(
            {
                "action_type": "add_content_brief",
                "title": "补充品牌可发现内容",
                "reason": "成功取得回答，但客户名称没有出现，需要补充地区、服务与品牌关联内容。",
                "target_level": "L3",
                "target_page": "P04",
            },
        )
    if evaluation.brand_found and not evaluation.correctly_associated:
        suggested_actions.append(
            {
                "action_type": "add_fact_task",
                "title": "补强企业实体关联",
                "reason": "品牌已出现，但地区或服务关联不清晰，需要补充可核验企业事实。",
                "target_level": "L1",
                "target_page": "P02",
            },
        )
    if evaluation.correctly_associated and not evaluation.recommended:
        suggested_actions.append(
            {
                "action_type": "add_content_brief",
                "title": "补充推荐理由型内容",
                "reason": "品牌与业务关联正确，但尚未形成推荐，需要增加选择标准与差异化理由。",
                "target_level": "L3",
                "target_page": "P04",
            },
        )
    if evaluation.facts_accurate is False:
        suggested_actions.append(
            {
                "action_type": "add_fact_task",
                "title": "修正冲突事实",
                "reason": "回答中存在与企业知识库不一致的信息，需要优先核验并补强事实来源。",
                "target_level": "L1",
                "target_page": "P02",
            },
        )
    if not suggested_actions:
        suggested_actions.append(
            {
                "action_type": "increase_sample",
                "title": "扩大重复采样",
                "reason": "本次样本达到目标，建议增加不同时间的重复采样验证稳定性。",
                "target_level": "L2",
                "target_page": "P07",
            },
        )
    return {
        "id": str(evaluation.id),
        "sample_id": str(evaluation.sample_id),
        "brand_found": evaluation.brand_found,
        "correctly_associated": evaluation.correctly_associated,
        "recommended": evaluation.recommended,
        "recommendation_supported": evaluation.recommendation_supported,
        "facts_accurate": evaluation.facts_accurate,
        "source_visible": evaluation.source_visible,
        "mentioned_name": evaluation.mentioned_name,
        "reasons": evaluation.reasons,
        "incorrect_facts": evaluation.incorrect_facts,
        "visible_sources": evaluation.visible_sources,
        "note": evaluation.note,
        "evaluator": evaluation.evaluator,
        "version": evaluation.version,
        "updated_at": evaluation.updated_at.isoformat(),
        "suggested_actions": suggested_actions,
    }


def _sample_data(
    sample: MonitoringSample,
    evaluation: MonitoringEvaluation | None,
) -> dict[str, object]:
    return {
        "id": str(sample.id),
        "batch_id": str(sample.batch_id),
        "platform_id": sample.platform_id,
        "platform_name": sample.platform_name,
        "collection_mode": sample.collection_mode,
        "question_id": sample.question_id,
        "question_text": sample.question_text,
        "question_family": sample.question_family,
        "is_brand_query": sample.is_brand_query,
        "priority": sample.question_priority,
        "attempt": sample.attempt,
        "status": sample.status,
        "raw_answer": sample.raw_answer,
        "asked_at": sample.asked_at.isoformat() if sample.asked_at else None,
        "failure_reason": sample.failure_reason,
        "evaluation": _evaluation_data(evaluation) if evaluation else None,
    }


async def _batch_data(database: AsyncSession, batch: MonitoringBatch) -> dict[str, object]:
    samples = list(
        (
            await database.scalars(
                select(MonitoringSample)
                .where(MonitoringSample.batch_id == batch.id)
                .order_by(
                    MonitoringSample.platform_id,
                    MonitoringSample.question_family,
                    MonitoringSample.question_id,
                    MonitoringSample.attempt,
                ),
            )
        ).all(),
    )
    evaluations = (
        list(
            (
                await database.scalars(
                    select(MonitoringEvaluation).where(
                        MonitoringEvaluation.sample_id.in_([sample.id for sample in samples]),
                    ),
                )
            ).all(),
        )
        if samples
        else []
    )
    evaluation_by_sample = {item.sample_id: item for item in evaluations}
    metric_rows: list[dict[str, object]] = [
        {
            "status": sample.status,
            "brand_found": (
                evaluation_by_sample[sample.id].brand_found
                if sample.id in evaluation_by_sample
                else None
            ),
            "correctly_associated": (
                evaluation_by_sample[sample.id].correctly_associated
                if sample.id in evaluation_by_sample
                else None
            ),
            "recommended": (
                evaluation_by_sample[sample.id].recommended
                if sample.id in evaluation_by_sample
                else None
            ),
            "facts_accurate": (
                evaluation_by_sample[sample.id].facts_accurate
                if sample.id in evaluation_by_sample
                else None
            ),
            "recommendation_supported": (
                evaluation_by_sample[sample.id].recommendation_supported
                if sample.id in evaluation_by_sample
                else None
            ),
            "source_visible": (
                evaluation_by_sample[sample.id].source_visible
                if sample.id in evaluation_by_sample
                else None
            ),
            "collection_mode": sample.collection_mode,
            "question_id": sample.question_id,
            "question_family": sample.question_family,
            "is_brand_query": sample.is_brand_query,
            "priority": sample.question_priority,
        }
        for sample in samples
    ]
    return {
        "id": str(batch.id),
        "client_id": str(batch.client_id),
        "question_set_id": str(batch.question_set_id),
        "question_set_version": batch.question_set_version,
        "status": batch.status,
        "platform_ids": batch.platform_ids,
        "api_sample_count": batch.api_sample_count,
        "created_at": batch.created_at.isoformat(),
        "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
        "samples": [
            _sample_data(sample, evaluation_by_sample.get(sample.id)) for sample in samples
        ],
        "summary": calculate_monitoring_metrics(metric_rows),
    }


def _auto_evaluation(
    sample: MonitoringSample,
    client: Client,
    confirmed_facts: list[Fact],
) -> MonitoringEvaluation:
    answer = (sample.raw_answer or "").casefold()
    names = [
        value.casefold()
        for value in (client.standard_name, client.short_name)
        if value and len(value.strip()) >= 2
    ]
    brand_found = any(name in answer for name in names)
    location_terms = [
        value.casefold()
        for value in (client.district, client.city, client.service_radius)
        if value and len(value.strip()) >= 2
    ]
    service_terms = [
        value.casefold()
        for value in (client.industry_name, client.industry_code)
        if value and len(value.strip()) >= 2
    ]
    correctly_associated = brand_found and (
        any(term in answer for term in location_terms)
        or any(term in answer for term in service_terms)
    )
    recommendation_cues = ("推荐", "可以考虑", "可了解", "建议选择", "值得了解")
    recommended = brand_found and any(cue in answer for cue in recommendation_cues)
    visible_urls = re.findall(r"https?://[^\s,.;)]+", sample.raw_answer or "")
    source_visible = bool(visible_urls)
    matched_facts = [
        {"fact_id": str(fact.id), "label": fact.label, "value": fact.value}
        for fact in confirmed_facts
        if len(fact.value.strip()) >= 2 and fact.value.casefold() in answer
    ]
    reasons: list[str] = []
    if not brand_found:
        reasons.append("回答中未发现企业标准名称或简称")
    elif not correctly_associated:
        reasons.append("发现企业名称，但地区或服务关联不足")
    elif not recommended:
        reasons.append("已正确关联企业，但没有形成明确推荐")
    else:
        reasons.append("回答中发现企业、正确关联并出现推荐表达")
    if matched_facts:
        reasons.append(f"命中 {len(matched_facts)} 项已确认企业事实，仍需人工核验其他陈述")
    else:
        reasons.append("未找到足以自动核验的已确认企业事实，事实准确性保持待核验")
    return MonitoringEvaluation(
        sample_id=sample.id,
        client_id=sample.client_id,
        brand_found=brand_found,
        correctly_associated=correctly_associated,
        recommended=recommended,
        recommendation_supported=None,
        facts_accurate=None,
        source_visible=source_visible,
        mentioned_name=client.standard_name if brand_found else None,
        reasons=reasons,
        incorrect_facts=[],
        visible_sources=[{"url": url, "source": "raw_answer"} for url in visible_urls],
        note=(
            "系统仅完成确定性匹配; 命中事实: "
            + ", ".join(str(item["label"]) for item in matched_facts)
            if matched_facts
            else "系统未宣称事实准确或推荐有据，等待人工依据 P02 事实与证据复核。"
        ),
        evaluator="system",
    )


def _fixed_mock_answer(sample: MonitoringSample, client: Client) -> str:
    if sample.question_family == "recommendation":
        return (
            f"如果在{client.district}寻找{client.industry_name}，可以了解"
            f"{client.standard_name}，并在到店前核对当前服务范围、价格与时间安排。"
            "这不是唯一选择，建议结合公开资料和实际咨询判断。"
        )
    return (
        f"{client.standard_name}是一家服务{client.district}的{client.industry_name}机构。"
        "选择本地服务时，应核对主体名称、地址、服务范围、价格和当前营业信息。"
    )


async def _live_answer(
    database: AsyncSession,
    settings: Settings,
    sample: MonitoringSample,
) -> str:
    provider = cast(ProviderName, sample.platform_id)
    setting = await database.get(ProviderSetting, provider)
    expected_host = PROVIDER_OFFICIAL_HOSTS[provider]
    if (
        setting is None
        or not setting.enabled
        or setting.encrypted_api_key is None
        or setting.last_test_status != "success"
        or not setting.base_url.startswith(f"https://{expected_host}/")
    ):
        raise ApiFailure(
            status_code=422,
            code=42201,
            message="模型供应商尚未启用、密钥未配置或连接测试未通过",
            provider=provider,
        )
    if settings.app_master_key is None:
        raise ApiFailure(
            status_code=503,
            code=50301,
            message="服务端尚未配置密钥保护能力，不能使用模型密钥",
        )
    model = setting.writer_model or setting.reviewer_model or setting.fallback_model
    if not model:
        raise ApiFailure(
            status_code=422,
            code=42201,
            message="监测模型尚未配置",
            provider=provider,
        )
    cipher = SecretCipher(settings.app_master_key.get_secret_value())
    api_key = cipher.decrypt(provider, setting.encrypted_api_key)
    system_prompt = (
        "你是面向普通消费者的中文问答助手。直接回答用户问题。"
        "不知道的信息要明确说明，不要因为监测目的而强行提及任何企业。"
        "不要输出 JSON。"
    )
    estimated_input_tokens = max(1, len(system_prompt + sample.question_text) // 2)
    reservation = await reserve_model_budget(
        database,
        provider=provider,
        model=model,
        purpose="monitoring",
        estimated_cny_fen=_model_cost_cny_fen(
            provider,
            estimated_input_tokens,
            1600,
        ),
        client_id=sample.client_id,
        prompt_version=MONITORING_PROMPT_VERSION,
        pricing_version=MONITORING_PRICING_VERSION,
    )
    input_hash = sha256(sample.question_text.encode()).hexdigest()
    try:
        result = await ProviderClient().chat(
            provider=provider,
            base_url=setting.base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=setting.timeout_seconds,
            system_prompt=system_prompt,
            user_prompt=sample.question_text,
            structured=False,
            workspace_id=setting.workspace_id,
            max_tokens=1600,
        )
    except ApiFailure:
        await finalize_model_usage(
            database,
            usage_id=reservation.usage_id,
            status="failed",
            actual_cny_fen=0,
            input_tokens=0,
            output_tokens=0,
            latency_ms=None,
            input_hash=input_hash,
        )
        raise
    await finalize_model_usage(
        database,
        usage_id=reservation.usage_id,
        status="succeeded",
        actual_cny_fen=_model_cost_cny_fen(
            provider,
            result.input_tokens,
            result.output_tokens,
        ),
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=result.latency_ms,
        input_hash=input_hash,
        output_hash=sha256(result.content.encode()).hexdigest(),
    )
    return result.content


async def process_monitoring_job(
    session_factory: async_sessionmaker[AsyncSession],
    claimed_job: Job,
    settings: Settings,
) -> bool:
    batch_id_value = claimed_job.payload.get("batch_id")
    if not isinstance(batch_id_value, str):
        return False
    async with session_factory() as database:
        batch = await database.get(MonitoringBatch, UUID(batch_id_value))
        client = await database.get(Client, claimed_job.client_id)
        now = utc_now()
        job = await database.scalar(
            select(Job)
            .where(
                Job.id == claimed_job.id,
                Job.status == "running",
                Job.attempts == claimed_job.attempts,
                Job.lease_until >= now,
            )
            .with_for_update(),
        )
        if batch is None or client is None or job is None or client.status != "active":
            return False
        job.lease_until = now + timedelta(minutes=5)
        batch.status = "running"
        await database.commit()
        confirmed_facts = list(
            (
                await database.scalars(
                    select(Fact).where(
                        Fact.client_id == client.id,
                        Fact.status == "confirmed",
                    ),
                )
            ).all(),
        )
        samples = list(
            (
                await database.scalars(
                    select(MonitoringSample).where(
                        MonitoringSample.batch_id == batch.id,
                        MonitoringSample.collection_mode == "api",
                        MonitoringSample.status == "not_executed",
                    ),
                )
            ).all(),
        )
        for sample in samples:
            current_job = await database.scalar(
                select(Job)
                .where(
                    Job.id == claimed_job.id,
                    Job.status == "running",
                    Job.attempts == claimed_job.attempts,
                    Job.lease_until >= utc_now(),
                )
                .with_for_update(),
            )
            if current_job is None:
                await database.rollback()
                return False
            current_job.lease_until = utc_now() + timedelta(minutes=5)
            await database.commit()
            try:
                answer = (
                    _fixed_mock_answer(sample, client)
                    if settings.model_execution_mode == "fixed_mock"
                    else await _live_answer(database, settings, sample)
                )
                sample.status = "succeeded"
                sample.raw_answer = answer
                sample.asked_at = utc_now()
                sample.failure_reason = None
                database.add(_auto_evaluation(sample, client, confirmed_facts))
            except ApiFailure as failure:
                sample.status = "failed"
                sample.raw_answer = None
                sample.asked_at = utc_now()
                sample.failure_reason = failure.message[:500]
            await database.commit()
        job = await database.scalar(
            select(Job)
            .where(
                Job.id == claimed_job.id,
                Job.status == "running",
                Job.attempts == claimed_job.attempts,
                Job.lease_until >= utc_now(),
            )
            .with_for_update(),
        )
        batch = await database.scalar(
            select(MonitoringBatch)
            .where(MonitoringBatch.id == UUID(batch_id_value))
            .with_for_update(),
        )
        if job is None or batch is None:
            await database.rollback()
            return False
        await _recalculate_batch_status(database, batch)
        job.status = "succeeded"
        job.progress = 100
        job.lease_until = None
        job.completed_at = utc_now()
        await database.commit()
    return True


def build_monitoring_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["monitoring"])

    @router.get("/monitoring/platforms")
    async def get_platforms(
        request: Request,
        authentication: Authenticated,
        priority: Annotated[PlatformPriority | None, Query()] = None,
        mode: Annotated[PlatformMode | None, Query()] = None,
        active: Annotated[bool, Query()] = True,
    ) -> Response:
        items = [
            _platform_data(item)
            for item in PLATFORM_CATALOG
            if (not active or item["active"])
            and (priority is None or item["priority"] == priority)
            and (mode is None or item["mode"] == mode)
        ]
        return success_response(
            request,
            {"items": items, "catalog_version": CATALOG_VERSION},
        )

    @router.get("/clients/{client_id}/question-sets")
    async def get_question_sets(
        request: Request,
        client_id: UUID,
        database: DatabaseSession,
        authentication: Authenticated,
    ) -> Response:
        if await database.get(Client, client_id) is None:
            return error_response(request, status_code=404, code=40401, message="客户不存在")
        items = list(
            (
                await database.scalars(
                    select(MonitoringQuestionSet)
                    .where(MonitoringQuestionSet.client_id == client_id)
                    .order_by(MonitoringQuestionSet.created_at.desc()),
                )
            ).all(),
        )
        return success_response(request, {"items": [_question_set_data(item) for item in items]})

    @router.post("/clients/{client_id}/question-sets")
    async def create_question_set(
        request: Request,
        client_id: UUID,
        body: QuestionSetCreateInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        if await database.get(Client, client_id) is None:
            return error_response(request, status_code=404, code=40401, message="客户不存在")
        if body.frozen and not await _questions_are_confirmed_strategy(
            database,
            client_id,
            body.questions,
        ):
            return error_response(
                request,
                status_code=422,
                code=42201,
                message="监测问题必须来自关键词页面已选择的关键词或已锁定的问题",
            )
        questions = [
            {
                **question.model_dump(exclude={"id"}),
                "id": question.id or str(uuid4()),
            }
            for question in body.questions
        ]
        if body.frozen:
            strategy_item_ids = [
                UUID(question.id) for question in body.questions if question.id is not None
            ]
            await database.execute(
                update(StrategyItem)
                .where(
                    StrategyItem.client_id == client_id,
                    StrategyItem.id.in_(strategy_item_ids),
                    StrategyItem.kind == "keyword",
                    StrategyItem.selected.is_(True),
                )
                .values(
                    locked=True,
                    version=StrategyItem.version + 1,
                ),
            )
        question_set = MonitoringQuestionSet(
            client_id=client_id,
            name=body.name,
            frozen=body.frozen,
            questions=questions,
        )
        database.add(question_set)
        await database.commit()
        await database.refresh(question_set)
        return success_response(
            request,
            _question_set_data(question_set),
            status_code=201,
        )

    @router.patch("/question-sets/{question_set_id}")
    async def patch_question_set(
        request: Request,
        question_set_id: UUID,
        body: QuestionSetPatchInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        question_set = await lock_monitoring_question_set(database, question_set_id)
        if question_set is None:
            return error_response(request, status_code=404, code=40401, message="问题集不存在")
        if question_set.version != body.version:
            return error_response(
                request, status_code=409, code=40901, message="问题集已被更新，请刷新后重试"
            )
        if question_set.frozen and (
            body.name is not None or body.questions is not None or body.frozen is False
        ):
            return error_response(
                request, status_code=409, code=40902, message="冻结问题集不可修改"
            )
        next_questions = body.questions or [
            QuestionInput.model_validate(question) for question in question_set.questions
        ]
        if body.frozen is True and not await _questions_are_confirmed_strategy(
            database,
            question_set.client_id,
            next_questions,
        ):
            return error_response(
                request,
                status_code=422,
                code=42201,
                message="监测问题必须来自关键词页面已选择的关键词或已锁定的问题",
            )
        if body.name is not None:
            question_set.name = body.name
        if body.questions is not None:
            question_set.questions = [
                {
                    **question.model_dump(exclude={"id"}),
                    "id": question.id or str(uuid4()),
                }
                for question in body.questions
            ]
        if body.frozen is not None:
            question_set.frozen = body.frozen
        question_set.version += 1
        await database.commit()
        await database.refresh(question_set)
        return success_response(request, _question_set_data(question_set))

    @router.post("/clients/{client_id}/monitoring-batches")
    async def create_batch(
        request: Request,
        client_id: UUID,
        body: BatchCreateInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
        idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    ) -> Response:
        client = await lock_monitoring_client(database, client_id)
        if client is None:
            return error_response(request, status_code=404, code=40401, message="客户不存在")
        if client.status != "active":
            return error_response(
                request,
                status_code=409,
                code=40901,
                message="暂停或归档客户不能创建监测批次",
            )
        question_set = await database.get(MonitoringQuestionSet, body.question_set_id)
        if question_set is None or question_set.client_id != client_id:
            return error_response(
                request, status_code=422, code=42201, message="问题集不属于当前客户"
            )
        unknown_or_inactive = sorted(
            platform_id
            for platform_id in set(body.platform_ids)
            if platform_id not in PLATFORMS_BY_ID or not PLATFORMS_BY_ID[platform_id]["active"]
        )
        if unknown_or_inactive or not question_set.frozen:
            return error_response(
                request,
                status_code=422,
                code=42201,
                message="问题集未冻结或未选择监测平台",
            )
        try:
            frozen_questions = [
                QuestionInput.model_validate(question) for question in question_set.questions
            ]
        except ValueError:
            frozen_questions = []
        if not frozen_questions or not await _questions_are_confirmed_strategy(
            database,
            client_id,
            frozen_questions,
        ):
            return error_response(
                request,
                status_code=422,
                code=42201,
                message="监测问题必须来自关键词页面已选择的关键词或已锁定的问题",
            )
        platform_ids = sorted(set(body.platform_ids))
        payload = {
            "question_set_id": str(question_set.id),
            "question_set_version": question_set.version,
            "platform_ids": platform_ids,
            "api_sample_count": body.api_sample_count,
            "manual_placeholders": body.manual_placeholders,
        }
        existing_job = await database.scalar(
            select(Job).where(
                Job.client_id == client_id,
                Job.job_type == "monitoring_batch",
                Job.idempotency_key == str(idempotency_key),
            ),
        )
        if existing_job is not None:
            if any(existing_job.payload.get(key) != value for key, value in payload.items()):
                return error_response(
                    request, status_code=409, code=40903, message="幂等键已用于不同监测参数"
                )
            existing_batch = await database.get(
                MonitoringBatch,
                UUID(cast(str, existing_job.payload["batch_id"])),
            )
            if existing_batch is None:
                raise RuntimeError("monitoring batch missing for idempotent job")
            return success_response(
                request,
                {
                    "batch": await _batch_data(database, existing_batch),
                    "job": {
                        "id": str(existing_job.id),
                        "job_type": existing_job.job_type,
                        "status": existing_job.status,
                    },
                },
                status_code=202,
            )
        batch = MonitoringBatch(
            client_id=client_id,
            question_set_id=question_set.id,
            question_set_version=question_set.version,
            question_snapshot=question_set.questions,
            platform_ids=platform_ids,
            api_sample_count=body.api_sample_count,
        )
        database.add(batch)
        await database.flush()
        for platform_id in platform_ids:
            platform = PLATFORMS_BY_ID[platform_id]
            if platform["mode"] == "manual_consumer" and not body.manual_placeholders:
                continue
            for question in question_set.questions:
                attempts = (
                    body.api_sample_count
                    if platform["mode"] == "api" and int(str(question["priority"])) == 1
                    else 1
                )
                for attempt in range(1, attempts + 1):
                    database.add(
                        MonitoringSample(
                            batch_id=batch.id,
                            client_id=client_id,
                            platform_id=platform_id,
                            platform_name=platform["name"],
                            collection_mode=platform["mode"],
                            question_id=str(question["id"]),
                            question_text=str(question["text"]),
                            question_family=str(question["family"]),
                            is_brand_query=bool(question["is_brand_query"]),
                            question_priority=int(str(question["priority"])),
                            attempt=attempt,
                            status="not_executed",
                        ),
                    )
        job = Job(
            client_id=client_id,
            job_type="monitoring_batch",
            idempotency_key=str(idempotency_key),
            payload={**payload, "batch_id": str(batch.id)},
        )
        database.add(job)
        try:
            await database.commit()
        except IntegrityError:
            await database.rollback()
            existing_job = await database.scalar(
                select(Job).where(
                    Job.client_id == client_id,
                    Job.job_type == "monitoring_batch",
                    Job.idempotency_key == str(idempotency_key),
                ),
            )
            if existing_job is None:
                raise
            if any(existing_job.payload.get(key) != value for key, value in payload.items()):
                return error_response(
                    request, status_code=409, code=40903, message="幂等键已用于不同监测参数"
                )
            recovered_batch = await database.get(
                MonitoringBatch,
                UUID(cast(str, existing_job.payload["batch_id"])),
            )
            if recovered_batch is None:
                raise RuntimeError("monitoring batch missing for idempotent job") from None
            batch = recovered_batch
            job = existing_job
        await database.refresh(batch)
        await database.refresh(job)
        return success_response(
            request,
            {
                "batch": await _batch_data(database, batch),
                "job": {
                    "id": str(job.id),
                    "job_type": job.job_type,
                    "status": job.status,
                },
            },
            status_code=202,
        )

    @router.get("/monitoring-batches/{batch_id}")
    async def get_batch(
        request: Request,
        batch_id: UUID,
        database: DatabaseSession,
        authentication: Authenticated,
    ) -> Response:
        batch = await database.get(MonitoringBatch, batch_id)
        if batch is None:
            return error_response(request, status_code=404, code=40401, message="监测批次不存在")
        return success_response(request, await _batch_data(database, batch))

    @router.get("/clients/{client_id}/monitoring-batches/latest")
    async def get_latest_batch(
        request: Request,
        client_id: UUID,
        database: DatabaseSession,
        authentication: Authenticated,
    ) -> Response:
        batch = await database.scalar(
            select(MonitoringBatch)
            .where(MonitoringBatch.client_id == client_id)
            .order_by(MonitoringBatch.created_at.desc(), MonitoringBatch.id.desc()),
        )
        if batch is None:
            return error_response(request, status_code=404, code=40401, message="暂无监测批次")
        return success_response(request, await _batch_data(database, batch))

    @router.post("/monitoring-batches/{batch_id}/manual-samples")
    async def add_manual_samples(
        request: Request,
        batch_id: UUID,
        body: ManualSamplesInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        batch = await database.get(MonitoringBatch, batch_id)
        if batch is None:
            return error_response(request, status_code=404, code=40401, message="监测批次不存在")
        client = await database.get(Client, batch.client_id)
        if client is None:
            return error_response(request, status_code=404, code=40401, message="客户不存在")
        confirmed_facts = list(
            (
                await database.scalars(
                    select(Fact).where(
                        Fact.client_id == client.id,
                        Fact.status == "confirmed",
                    ),
                )
            ).all(),
        )
        changed: list[MonitoringSample] = []
        for item in body.items:
            sample = await database.get(MonitoringSample, item.sample_id)
            if (
                sample is None
                or sample.batch_id != batch_id
                or sample.collection_mode != "manual_consumer"
            ):
                return error_response(
                    request,
                    status_code=422,
                    code=42201,
                    message="仅可回填当前批次的消费者端人工样本",
                )
            existing_evaluation = await database.scalar(
                select(MonitoringEvaluation).where(
                    MonitoringEvaluation.sample_id == sample.id,
                ),
            )
            if existing_evaluation is not None:
                await database.delete(existing_evaluation)
            sample.status = item.status
            sample.raw_answer = item.raw_answer.strip() if item.raw_answer else None
            sample.failure_reason = item.failure_reason.strip() if item.failure_reason else None
            sample.asked_at = item.asked_at
            if item.status == "succeeded":
                database.add(_auto_evaluation(sample, client, confirmed_facts))
            changed.append(sample)
        await _recalculate_batch_status(database, batch)
        await database.commit()
        evaluations = list(
            (
                await database.scalars(
                    select(MonitoringEvaluation).where(
                        MonitoringEvaluation.sample_id.in_([item.id for item in changed]),
                    ),
                )
            ).all(),
        )
        by_sample = {item.sample_id: item for item in evaluations}
        return success_response(
            request,
            {"items": [_sample_data(item, by_sample.get(item.id)) for item in changed]},
        )

    @router.put("/monitoring-samples/{sample_id}/evaluation")
    async def put_evaluation(
        request: Request,
        sample_id: UUID,
        body: EvaluationInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        sample = await database.get(MonitoringSample, sample_id)
        if sample is None:
            return error_response(request, status_code=404, code=40401, message="监测样本不存在")
        if sample.status != "succeeded":
            return error_response(
                request, status_code=422, code=42201, message="只有成功样本可以评估"
            )
        evaluation = await database.scalar(
            select(MonitoringEvaluation).where(MonitoringEvaluation.sample_id == sample.id),
        )
        if evaluation is None:
            if body.version is not None:
                return error_response(request, status_code=409, code=40901, message="评估版本冲突")
            evaluation = MonitoringEvaluation(
                sample_id=sample.id,
                client_id=sample.client_id,
                brand_found=body.brand_found,
                correctly_associated=body.correctly_associated,
                recommended=body.recommended,
                recommendation_supported=body.recommendation_supported,
                facts_accurate=body.facts_accurate,
                source_visible=body.source_visible,
                mentioned_name=body.mentioned_name,
                reasons=body.reasons,
                incorrect_facts=body.incorrect_facts,
                visible_sources=body.visible_sources,
                note=body.note,
                evaluator="user",
            )
            database.add(evaluation)
        else:
            if body.version != evaluation.version:
                return error_response(
                    request, status_code=409, code=40901, message="评估已被更新，请刷新后重试"
                )
            for field in (
                "brand_found",
                "correctly_associated",
                "recommended",
                "recommendation_supported",
                "facts_accurate",
                "source_visible",
                "mentioned_name",
                "reasons",
                "incorrect_facts",
                "visible_sources",
                "note",
            ):
                setattr(evaluation, field, getattr(body, field))
            evaluation.evaluator = "user"
            evaluation.version += 1
        await database.commit()
        await database.refresh(evaluation)
        return success_response(request, _evaluation_data(evaluation))

    @router.get("/clients/{client_id}/monitoring-metrics")
    async def get_metrics(
        request: Request,
        client_id: UUID,
        database: DatabaseSession,
        authentication: Authenticated,
        date_from: Annotated[date, Query(alias="from")],
        date_to: Annotated[date, Query(alias="to")],
        platform_ids: Annotated[list[str] | None, Query()] = None,
        question_families: Annotated[list[QuestionFamily] | None, Query()] = None,
    ) -> Response:
        if date_to < date_from or (date_to - date_from).days > 366:
            return error_response(request, status_code=400, code=40001, message="监测时间范围无效")
        sample_time = func.coalesce(MonitoringSample.asked_at, MonitoringSample.created_at)
        query = (
            select(
                MonitoringSample.status.label("status"),
                MonitoringEvaluation.brand_found.label("brand_found"),
                MonitoringEvaluation.correctly_associated.label("correctly_associated"),
                MonitoringEvaluation.recommended.label("recommended"),
                MonitoringEvaluation.facts_accurate.label("facts_accurate"),
                MonitoringEvaluation.recommendation_supported.label(
                    "recommendation_supported",
                ),
                MonitoringEvaluation.source_visible.label("source_visible"),
                MonitoringSample.collection_mode.label("collection_mode"),
                MonitoringSample.question_id.label("question_id"),
                MonitoringSample.question_family.label("question_family"),
                MonitoringSample.is_brand_query.label("is_brand_query"),
                MonitoringSample.question_priority.label("priority"),
            )
            .outerjoin(
                MonitoringEvaluation,
                MonitoringEvaluation.sample_id == MonitoringSample.id,
            )
            .where(
                MonitoringSample.client_id == client_id,
                sample_time >= datetime.combine(date_from, time.min, tzinfo=UTC),
                sample_time <= datetime.combine(date_to, time.max, tzinfo=UTC),
            )
        )
        if platform_ids:
            query = query.where(MonitoringSample.platform_id.in_(platform_ids))
        if question_families:
            query = query.where(MonitoringSample.question_family.in_(question_families))
        rows = [dict(row) for row in (await database.execute(query)).mappings().all()]
        return success_response(
            request,
            {
                **calculate_monitoring_metrics(rows),
                "time_range": {
                    "from": date_from.isoformat(),
                    "to": date_to.isoformat(),
                },
                "platform_ids": platform_ids or [],
                "question_families": question_families or [],
            },
        )

    @router.post("/monitoring-evaluations/{evaluation_id}/feedback")
    async def create_feedback(
        request: Request,
        evaluation_id: UUID,
        body: FeedbackInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        evaluation = await database.get(MonitoringEvaluation, evaluation_id)
        if evaluation is None:
            return error_response(request, status_code=404, code=40401, message="监测评估不存在")
        defaults = {
            "add_fact_task": ("L1", "P02", "核验并补强企业事实"),
            "add_content_brief": ("L3", "P04", "生成下一轮内容简报"),
            "update_channel_priority": ("L2", "P06", "调整渠道发布优先级"),
            "increase_sample": ("L2", "P07", "扩大同题重复采样"),
        }
        target_level, expected_page, title = defaults[body.action_type]
        if body.target_page != expected_page:
            return error_response(
                request, status_code=422, code=42201, message="动作类型与目标页面不匹配"
            )
        sufficient = {
            "add_fact_task": (
                not evaluation.correctly_associated or evaluation.facts_accurate is False
            ),
            "add_content_brief": (not evaluation.brand_found or not evaluation.recommended),
            "update_channel_priority": not evaluation.source_visible,
            "increase_sample": True,
        }[body.action_type]
        if not sufficient:
            return error_response(
                request,
                status_code=422,
                code=42202,
                message="该评估没有足够依据生成反馈动作",
            )
        existing = await database.scalar(
            select(MonitoringFeedback).where(
                MonitoringFeedback.evaluation_id == evaluation.id,
                MonitoringFeedback.action_type == body.action_type,
            ),
        )
        if existing is not None:
            return success_response(
                request,
                {
                    "id": str(existing.id),
                    "evaluation_id": str(existing.evaluation_id),
                    "action_type": existing.action_type,
                    "reason": existing.reason,
                    "target_level": existing.target_level,
                    "target_page": existing.target_page,
                    "converted_record_type": existing.converted_record_type,
                    "converted_record_id": str(existing.converted_record_id),
                    "status": existing.status,
                    "created_at": existing.created_at.isoformat(),
                },
            )
        action = OptimizationAction(
            client_id=evaluation.client_id,
            source_type="monitoring_feedback",
            source_id=evaluation.id,
            action_type=body.action_type,
            title=title,
            reason=body.reason,
            target_level=target_level,
            target_page=body.target_page,
        )
        database.add(action)
        await database.flush()
        feedback = MonitoringFeedback(
            client_id=evaluation.client_id,
            evaluation_id=evaluation.id,
            action_type=body.action_type,
            reason=body.reason,
            target_level=target_level,
            target_page=body.target_page,
            converted_record_type="optimization_action",
            converted_record_id=action.id,
        )
        database.add(feedback)
        try:
            await database.commit()
        except IntegrityError:
            await database.rollback()
            recovered_feedback = await database.scalar(
                select(MonitoringFeedback).where(
                    MonitoringFeedback.evaluation_id == evaluation.id,
                    MonitoringFeedback.action_type == body.action_type,
                ),
            )
            if recovered_feedback is None:
                raise
            feedback = recovered_feedback
        await database.refresh(feedback)
        return success_response(
            request,
            {
                "id": str(feedback.id),
                "evaluation_id": str(feedback.evaluation_id),
                "action_type": feedback.action_type,
                "reason": feedback.reason,
                "target_level": feedback.target_level,
                "target_page": feedback.target_page,
                "converted_record_type": feedback.converted_record_type,
                "converted_record_id": str(feedback.converted_record_id),
                "status": feedback.status,
                "created_at": feedback.created_at.isoformat(),
            },
            status_code=201,
        )

    @router.get("/clients/{client_id}/optimization-actions")
    async def get_optimization_actions(
        request: Request,
        client_id: UUID,
        database: DatabaseSession,
        authentication: Authenticated,
        target_page: Annotated[
            Literal["P02", "P04", "P06", "P07"] | None,
            Query(),
        ] = None,
    ) -> Response:
        if await database.get(Client, client_id) is None:
            return error_response(request, status_code=404, code=40401, message="客户不存在")
        query = select(OptimizationAction).where(
            OptimizationAction.client_id == client_id,
        )
        if target_page is not None:
            query = query.where(OptimizationAction.target_page == target_page)
        actions = list(
            (
                await database.scalars(
                    query.order_by(
                        OptimizationAction.created_at.desc(),
                        OptimizationAction.id.desc(),
                    ),
                )
            ).all(),
        )
        return success_response(
            request,
            {"items": [_optimization_action_data(action) for action in actions]},
        )

    return router
