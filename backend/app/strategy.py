# ruff: noqa: RUF001

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth import Authenticated, CsrfAuthenticated
from app.config import Settings
from app.database import (
    Client,
    ContentBrief,
    ContentDocument,
    DatabaseSession,
    DiagnosticIssue,
    DiagnosticRun,
    Evidence,
    Fact,
    FactEvidence,
    Job,
    KnowledgeProfile,
    MonitoringEvaluation,
    MonitoringSample,
    PromptTemplate,
    StrategyBundle,
    StrategyItem,
)
from app.diagnostic_probes import (
    build_competitive_insights,
    calculate_platform_visibility,
    compact_search_area,
    compact_search_service,
    current_platform_results,
    run_auto_diagnostic,
)
from app.knowledge_context import (
    PUBLIC_AUTHORIZATIONS,
    list_content_eligible_facts,
    lock_content_fact_set,
)
from app.monitoring import PLATFORM_CATALOG
from app.prompt_templates import ensure_prompt_templates
from app.providers import ProviderClient
from app.responses import ApiFailure, error_response, success_response

CORE_FACT_KEYS = ("service.primary", "audience.primary", "location.service_area")
ENTITY_FACT_KEYS = (
    "identity.standard_name",
    "identity.industry",
    "location.administrative_area",
    "location.address",
    "location.service_area",
    "service.primary",
    "service.details",
    "audience.primary",
    "contact.public",
    "capability.primary",
)
DIAGNOSTIC_SCOPES = ("entity", "evidence", "content", "source", "visibility")
QUESTION_FAMILIES = (
    "discovery",
    "recommendation",
    "scenario",
    "comparison",
    "brand_verification",
)
DEFAULT_CHANNELS_BY_CONTENT_TYPE: dict[str, list[str]] = {
    "selection_guide": ["zhihu", "sohu", "toutiao"],
    "entity_profile": ["sohu", "baijia", "wechat"],
    "faq": ["zhihu", "baijia", "toutiao"],
}
BRIEF_TITLE_LENSES = (
    "首次咨询核验清单",
    "适用场景说明",
    "服务边界说明",
    "本地选择要点",
    "常见误区解答",
    "费用与流程核验",
    "家庭决策参考",
    "企业信息核验",
    "后续追问清单",
)


class DiagnosticInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: list[Literal["entity", "evidence", "content", "source", "visibility"]] = Field(
        min_length=1, max_length=5
    )
    monitoring_window_days: int = Field(ge=1, le=365)


class DiagnosticIssueInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    status: Literal["resolved", "ignored"]
    note: str = Field(min_length=2, max_length=1000)


class StrategyGenerateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    diagnostic_run_id: UUID
    include_families: list[
        Literal[
            "discovery",
            "recommendation",
            "scenario",
            "comparison",
            "brand_verification",
        ]
    ] = Field(min_length=1, max_length=5)
    brief_count: int = Field(ge=1, le=30)


class KeywordSuggestion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    main_keyword: str = Field(min_length=2, max_length=300)
    long_tail_keyword: str = Field(min_length=2, max_length=500)
    keyword_type: Literal[
        "local_service",
        "brand",
        "recommendation",
        "scenario",
        "service_detail",
        "comparison",
        "transaction",
        "trust",
    ]
    user_intent: str = Field(min_length=2, max_length=300)
    priority: Literal[1, 2, 3]
    recommended_content_type: (
        Literal[
            "local_recommendation",
            "selection_guide",
            "practical_guide",
            "service_explainer",
            "scenario_solution",
            "faq",
            "local_presence",
            "entity_profile",
            "price_guide",
            "service_process",
            "comparison",
            "case_study",
        ]
        | None
    ) = None


class KeywordSuggestionOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[dict[str, object]] = Field(min_length=1, max_length=50)

    @model_validator(mode="before")
    @classmethod
    def accept_common_model_envelopes(cls, value: object) -> object:
        if isinstance(value, list):
            return {"items": value}
        if not isinstance(value, dict):
            return value
        candidate = value.get("items")
        if candidate is None:
            candidate = value.get("keywords")
        if candidate is None:
            candidate = value.get("data")
        if isinstance(candidate, dict):
            candidate = candidate.get("items") or candidate.get("keywords")
        if isinstance(candidate, dict):
            candidate = [candidate]
        return {"items": candidate} if candidate is not None else value


KEYWORD_TYPE_ALIASES = {
    "local_service": "local_service",
    "地区主营": "local_service",
    "地区+主营": "local_service",
    "brand": "brand",
    "企业品牌": "brand",
    "品牌": "brand",
    "recommendation": "recommendation",
    "推荐决策": "recommendation",
    "推荐": "recommendation",
    "scenario": "scenario",
    "场景适配": "scenario",
    "场景": "scenario",
    "service_detail": "service_detail",
    "服务细分": "service_detail",
    "服务": "service_detail",
    "comparison": "comparison",
    "选择比较": "comparison",
    "比较": "comparison",
    "transaction": "transaction",
    "费用决策": "transaction",
    "价格流程": "transaction",
    "价格": "transaction",
    "trust": "trust",
    "信任核验": "trust",
    "资质核验": "trust",
    "信任": "trust",
}
KEYWORD_INTENT_DEFAULTS = {
    "local_service": "寻找本地区相关服务",
    "brand": "了解企业品牌与服务",
    "recommendation": "获取推荐候选并做决策",
    "scenario": "判断具体场景是否适用",
    "service_detail": "了解具体服务内容",
    "comparison": "比较服务条件和选择标准",
    "transaction": "了解费用、预约和服务流程",
    "trust": "核验企业信息与可信依据",
}
KEYWORD_CONTENT_FORM_DEFAULTS = {
    "local_service": "local_presence",
    "brand": "entity_profile",
    "recommendation": "local_recommendation",
    "scenario": "scenario_solution",
    "service_detail": "service_explainer",
    "comparison": "comparison",
    "transaction": "price_guide",
    "trust": "faq",
}
VALID_CONTENT_FORM_CODES = {
    "local_recommendation",
    "selection_guide",
    "practical_guide",
    "service_explainer",
    "scenario_solution",
    "faq",
    "local_presence",
    "entity_profile",
    "price_guide",
    "service_process",
    "comparison",
    "case_study",
}


def normalize_keyword_suggestions(
    output: KeywordSuggestionOutput,
) -> list[KeywordSuggestion]:
    normalized: list[KeywordSuggestion] = []
    for raw in output.items:
        long_tail = next(
            (
                str(raw[key]).strip()
                for key in ("long_tail_keyword", "text", "query", "question", "keyword")
                if raw.get(key) is not None and str(raw[key]).strip()
            ),
            "",
        )
        main_keyword = next(
            (
                str(raw[key]).strip()
                for key in ("main_keyword", "primary_keyword", "topic")
                if raw.get(key) is not None and str(raw[key]).strip()
            ),
            long_tail,
        )
        raw_type = next(
            (
                str(raw[key]).strip()
                for key in ("keyword_type", "type", "category")
                if raw.get(key) is not None and str(raw[key]).strip()
            ),
            "",
        )
        keyword_type = KEYWORD_TYPE_ALIASES.get(raw_type)
        if keyword_type is None:
            keyword_type = KEYWORD_TYPE_ALIASES.get(raw_type.lower())
        if not long_tail or not main_keyword or keyword_type is None:
            continue
        user_intent = next(
            (
                str(raw[key]).strip()
                for key in ("user_intent", "intent", "search_intent")
                if raw.get(key) is not None and str(raw[key]).strip()
            ),
            KEYWORD_INTENT_DEFAULTS[keyword_type],
        )
        raw_priority = raw.get("priority", 2)
        priority_aliases: dict[object, int] = {
            1: 1,
            2: 2,
            3: 3,
            "1": 1,
            "2": 2,
            "3": 3,
            "high": 1,
            "medium": 2,
            "low": 3,
            "高": 1,
            "中": 2,
            "低": 3,
        }
        try:
            priority = priority_aliases.get(raw_priority, 2)
            recommended_content_type = next(
                (
                    str(raw[key]).strip()
                    for key in (
                        "recommended_content_type",
                        "content_form",
                        "recommended_form",
                    )
                    if raw.get(key) is not None
                    and str(raw[key]).strip() in VALID_CONTENT_FORM_CODES
                ),
                KEYWORD_CONTENT_FORM_DEFAULTS[keyword_type],
            )
            normalized.append(
                KeywordSuggestion(
                    main_keyword=main_keyword,
                    long_tail_keyword=long_tail,
                    keyword_type=cast(
                        Literal[
                            "local_service",
                            "brand",
                            "recommendation",
                            "scenario",
                            "service_detail",
                            "comparison",
                            "transaction",
                            "trust",
                        ],
                        keyword_type,
                    ),
                    user_intent=user_intent,
                    priority=cast(Literal[1, 2, 3], priority),
                    recommended_content_type=cast(
                        Literal[
                            "local_recommendation",
                            "selection_guide",
                            "practical_guide",
                            "service_explainer",
                            "scenario_solution",
                            "faq",
                            "local_presence",
                            "entity_profile",
                            "price_guide",
                            "service_process",
                            "comparison",
                            "case_study",
                        ],
                        recommended_content_type,
                    ),
                ),
            )
        except (TypeError, ValidationError):
            continue
    return normalized


REQUIRED_KEYWORD_TYPES = {
    "local_service",
    "brand",
    "recommendation",
    "scenario",
    "service_detail",
    "comparison",
    "transaction",
    "trust",
}


def keyword_suggestion_is_supported(
    item: KeywordSuggestion,
    *,
    brand: str,
    district: str,
    service_topics: list[str],
) -> bool:
    text = item.long_tail_keyword.strip()
    main_keyword = item.main_keyword.strip()
    text_mentions_service = any(topic in text for topic in service_topics)
    main_is_anchored = (
        brand in main_keyword
        or district in main_keyword
        or any(topic in main_keyword for topic in service_topics)
    )
    if not main_is_anchored:
        return False
    if item.keyword_type == "brand":
        return brand in text
    if item.keyword_type in {"local_service", "recommendation", "comparison"}:
        return district in text and text_mentions_service
    if item.keyword_type == "transaction":
        return text_mentions_service or brand in text
    if item.keyword_type == "trust":
        return brand in text or text_mentions_service
    return text_mentions_service or brand in text


def keyword_suggestion_is_natural(
    item: KeywordSuggestion,
    *,
    audience: str,
) -> bool:
    """Reject knowledge-base dumps and keep queries close to real user phrasing."""

    text = item.long_tail_keyword.strip().rstrip("?？")
    main_keyword = item.main_keyword.strip()
    if not text or len(text) > 28 or len(main_keyword) > 20:
        return False
    if "\n" in text or re.search(r"[:：;；]", text):
        return False
    if sum(text.count(mark) for mark in ("、", ",", "，")) > 1:
        return False
    compact_audience = re.sub(r"\s+", "", audience)
    return not (len(compact_audience) >= 8 and compact_audience in re.sub(r"\s+", "", text))


def stored_keyword_is_natural(item: StrategyItem, *, audience: str) -> bool:
    """Apply current generation rules to an older persisted AI keyword."""

    if item.kind != "keyword":
        return True
    if not item.main_keyword or not item.keyword_type:
        return False
    try:
        suggestion = KeywordSuggestion(
            main_keyword=item.main_keyword,
            long_tail_keyword=item.text,
            keyword_type=cast(
                Literal[
                    "local_service",
                    "brand",
                    "recommendation",
                    "scenario",
                    "service_detail",
                    "comparison",
                    "transaction",
                    "trust",
                ],
                item.keyword_type,
            ),
            user_intent=item.user_intent or "用户搜索意图",
            priority=cast(Literal[1, 2, 3], item.priority),
            recommended_content_type=cast(
                Literal[
                    "local_recommendation",
                    "selection_guide",
                    "practical_guide",
                    "service_explainer",
                    "scenario_solution",
                    "faq",
                    "local_presence",
                    "entity_profile",
                    "price_guide",
                    "service_process",
                    "comparison",
                    "case_study",
                ]
                | None,
                item.recommended_content_type,
            ),
        )
    except ValidationError:
        return False
    return keyword_suggestion_is_natural(suggestion, audience=audience)


def complete_keyword_categories(
    generated: list[dict[str, object]],
    fallback: list[dict[str, object]],
    seen: set[str],
) -> None:
    present_types = {
        str(item["keyword_type"]) for item in generated if item.get("keyword_type") is not None
    }
    for template in fallback:
        keyword_type = str(template.get("keyword_type", ""))
        text = str(template.get("text", ""))
        if (
            template.get("kind") != "keyword"
            or keyword_type not in REQUIRED_KEYWORD_TYPES - present_types
            or text in seen
        ):
            continue
        generated.append(template)
        seen.add(text)
        present_types.add(keyword_type)
    for template in fallback:
        if len(generated) >= 12:
            break
        text = str(template.get("text", ""))
        if template.get("kind") != "keyword" or text in seen:
            continue
        generated.append(template)
        seen.add(text)


class StrategyItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    text: str | None = Field(default=None, min_length=2, max_length=500)
    main_keyword: str | None = Field(default=None, min_length=2, max_length=300)
    user_intent: str | None = Field(default=None, min_length=2, max_length=300)
    keyword_type: (
        Literal[
            "local_service",
            "brand",
            "recommendation",
            "scenario",
            "service_detail",
            "comparison",
            "transaction",
            "trust",
        ]
        | None
    ) = None
    recommended_content_type: (
        Literal[
            "local_recommendation",
            "selection_guide",
            "practical_guide",
            "service_explainer",
            "scenario_solution",
            "faq",
            "local_presence",
            "entity_profile",
            "price_guide",
            "service_process",
            "comparison",
            "case_study",
        ]
        | None
    ) = None
    priority: Literal[1, 2, 3] | None = None
    locked: bool | None = None
    selected: bool | None = None
    active: bool | None = None

    @model_validator(mode="after")
    def require_change(self) -> "StrategyItemInput":
        if all(
            value is None
            for value in (
                self.text,
                self.main_keyword,
                self.user_intent,
                self.keyword_type,
                self.recommended_content_type,
                self.priority,
                self.locked,
                self.selected,
                self.active,
            )
        ):
            raise ValueError("至少提供一个可编辑字段")
        return self


class BriefCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=2, max_length=300)
    content_type: Literal[
        "local_recommendation",
        "entity_profile",
        "service_explainer",
        "selection_guide",
        "practical_guide",
        "scenario_solution",
        "faq",
        "price_guide",
        "service_process",
        "comparison",
        "case_study",
        "local_presence",
        "capability_proof",
        "case",
        "local_scenario",
    ]
    target_question_ids: list[UUID] = Field(min_length=1, max_length=100)
    target_keywords: list[str] = Field(min_length=1, max_length=100)
    target_level: Literal["L0", "L1", "L2", "L3", "L4"]
    audience: str = Field(min_length=2, max_length=1000)
    angle: str = Field(min_length=2, max_length=2000)
    required_fact_ids: list[UUID] = Field(min_length=1, max_length=200)
    required_evidence_ids: list[UUID] = Field(min_length=1, max_length=500)
    expected_recommendation_reason: str = Field(min_length=2, max_length=2000)
    prohibited_claims: list[str] = Field(max_length=200)
    retest_questions: list[str] = Field(max_length=100)
    suggested_channel_ids: list[str] = Field(max_length=100)
    priority: Literal[1, 2, 3]


class BriefUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=2, max_length=300)
    audience: str | None = Field(default=None, min_length=2, max_length=1000)
    angle: str | None = Field(default=None, min_length=2, max_length=2000)
    required_fact_ids: list[UUID] | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )
    required_evidence_ids: list[UUID] | None = Field(
        default=None,
        min_length=1,
        max_length=500,
    )
    expected_recommendation_reason: str | None = Field(
        default=None,
        min_length=2,
        max_length=2000,
    )
    prohibited_claims: list[str] | None = Field(default=None, max_length=200)
    retest_questions: list[str] | None = Field(default=None, max_length=100)
    suggested_channel_ids: list[str] | None = Field(default=None, max_length=100)
    priority: Literal[1, 2, 3] | None = None
    status: Literal["planned", "in_production", "completed", "archived"] | None = None

    @model_validator(mode="after")
    def require_change(self) -> "BriefUpdateInput":
        values = self.model_dump(exclude={"version"}, exclude_none=True)
        if not values:
            raise ValueError("至少提供一个可编辑字段")
        return self


def _issue_data(issue: DiagnosticIssue) -> dict[str, object]:
    return {
        "id": str(issue.id),
        "category": issue.category,
        "severity": issue.severity,
        "title": issue.title,
        "explanation": issue.explanation,
        "evidence_ids": issue.evidence_ids,
        "suggested_action": issue.suggested_action,
        "target_page": issue.target_page,
        "status": issue.status,
        "version": issue.version,
    }


async def _diagnostic_data(
    database: AsyncSession,
    diagnostic: DiagnosticRun,
) -> dict[str, object]:
    changed_fact_count = await diagnostic_snapshot_change_count(database, diagnostic)
    issues = list(
        (
            await database.scalars(
                select(DiagnosticIssue)
                .where(DiagnosticIssue.diagnostic_run_id == diagnostic.id)
                .order_by(DiagnosticIssue.severity, DiagnosticIssue.category),
            )
        ).all(),
    )
    platform_results = current_platform_results(diagnostic.platform_results)
    scored_platforms = [
        item
        for item in platform_results
        if isinstance(item, dict) and isinstance(item.get("score"), int)
    ]
    overall_score = diagnostic.scores.get("ai_visibility")
    competitive_insights = build_competitive_insights(platform_results)
    issue_rows = [_issue_data(issue) for issue in issues]
    for issue in issue_rows:
        issue["explanation"] = str(issue["explanation"]).replace(
            "本次三平台自动诊断",
            "本次自动诊断",
        )
    return {
        "id": str(diagnostic.id),
        "client_id": str(diagnostic.client_id),
        "status": diagnostic.status,
        "current_level": diagnostic.current_level,
        "scores": diagnostic.scores,
        "scope": diagnostic.scope,
        "monitoring_window_days": diagnostic.monitoring_window_days,
        "overall_score": overall_score,
        "overall_grade": (
            _visibility_grade(overall_score) if isinstance(overall_score, int) else None
        ),
        "evaluated_platform_count": len(scored_platforms),
        "total_platform_count": len(platform_results),
        "effective_sample_count": diagnostic.monitoring_sample_count,
        "platform_results": platform_results,
        "competitive_insights": competitive_insights,
        "issues": issue_rows,
        "fact_snapshot_id": str(diagnostic.fact_snapshot_id),
        "is_stale": changed_fact_count > 0,
        "changed_fact_count": changed_fact_count,
        "completed_at": (diagnostic.completed_at.isoformat() if diagnostic.completed_at else None),
    }


def _strategy_item_data(
    item: StrategyItem,
    *,
    generated_count: int = 0,
) -> dict[str, object]:
    return {
        "id": str(item.id),
        "kind": item.kind,
        "text": item.text,
        "family": item.family,
        "keyword_type": item.keyword_type,
        "provenance": item.provenance,
        "target_level": item.target_level,
        "priority": item.priority,
        "rationale": item.rationale,
        "main_keyword": item.main_keyword,
        "user_intent": item.user_intent,
        "recommended_content_type": item.recommended_content_type,
        "locked": item.locked,
        "selected": item.selected,
        "active": item.active,
        "generated_count": generated_count,
        "version": item.version,
    }


def _brief_data(brief: ContentBrief) -> dict[str, object]:
    return {
        "id": str(brief.id),
        "client_id": str(brief.client_id),
        "title": brief.title,
        "content_type": brief.content_type,
        "target_question_ids": brief.target_question_ids,
        "target_keywords": brief.target_keywords,
        "target_level": brief.target_level,
        "audience": brief.audience,
        "angle": brief.angle,
        "required_fact_ids": brief.required_fact_ids,
        "required_evidence_ids": brief.required_evidence_ids,
        "expected_recommendation_reason": brief.expected_recommendation_reason,
        "prohibited_claims": brief.prohibited_claims,
        "retest_questions": brief.retest_questions,
        "suggested_channel_ids": brief.suggested_channel_ids,
        "priority": brief.priority,
        "status": brief.status,
        "keyword_strategy_id": (
            str(brief.keyword_strategy_id) if brief.keyword_strategy_id else None
        ),
        "keyword_type": brief.keyword_type,
        "prompt_template_code": brief.prompt_template_code,
        "prompt_template_version": brief.prompt_template_version,
        "target_channel_id": brief.target_channel_id,
        "contact_policy": brief.contact_policy,
        "prompt_layers_snapshot": brief.prompt_layers_snapshot or [],
        "contact_allowed_urls": brief.contact_allowed_urls or [],
        "version": brief.version,
    }


async def _strategy_data(
    database: AsyncSession,
    bundle: StrategyBundle,
    *,
    active_only: bool,
) -> dict[str, object]:
    item_query = select(StrategyItem).where(StrategyItem.bundle_id == bundle.id)
    if active_only:
        item_query = item_query.where(StrategyItem.active.is_(True))
    items = list(
        (
            await database.scalars(
                item_query.order_by(
                    StrategyItem.priority,
                    StrategyItem.kind,
                    StrategyItem.family,
                    StrategyItem.id,
                ),
            )
        ).all(),
    )
    brief_query = select(ContentBrief).where(ContentBrief.bundle_id == bundle.id)
    if active_only:
        brief_query = brief_query.where(ContentBrief.status != "archived")
    briefs = list(
        (
            await database.scalars(
                brief_query.order_by(ContentBrief.priority, ContentBrief.id),
            )
        ).all(),
    )
    generated_counts: dict[UUID, int] = {}
    for brief in briefs:
        if brief.keyword_strategy_id is not None:
            generated_counts[brief.keyword_strategy_id] = (
                generated_counts.get(brief.keyword_strategy_id, 0) + 1
            )
    return {
        "client_id": str(bundle.client_id),
        "diagnostic_run_id": (
            str(bundle.diagnostic_run_id) if bundle.diagnostic_run_id is not None else None
        ),
        "items": [
            _strategy_item_data(
                item,
                generated_count=generated_counts.get(item.id, 0),
            )
            for item in items
        ],
        "briefs": [_brief_data(brief) for brief in briefs],
        "prompt_template_code": bundle.prompt_template_code,
        "prompt_template_version": bundle.prompt_template_version,
        "generated_at": bundle.generated_at.isoformat(),
        "version": bundle.version,
    }


async def _eligible_fact_map(
    database: AsyncSession,
    client_id: UUID,
) -> dict[str, Fact]:
    return {fact.key: fact for fact in await list_content_eligible_facts(database, client_id)}


async def _evidence_ids_by_fact(
    database: AsyncSession,
    facts: list[Fact],
) -> dict[UUID, list[str]]:
    fact_ids = [fact.id for fact in facts]
    if not fact_ids:
        return {}
    links = (
        await database.execute(
            select(FactEvidence.fact_id, FactEvidence.evidence_id).where(
                FactEvidence.fact_id.in_(fact_ids),
            ),
        )
    ).all()
    mapped: dict[UUID, list[str]] = {fact_id: [] for fact_id in fact_ids}
    for fact_id, evidence_id in links:
        mapped[fact_id].append(str(evidence_id))
    return mapped


async def diagnostic_snapshot_change_count(
    database: AsyncSession,
    diagnostic: DiagnosticRun,
    fact_map: dict[str, Fact] | None = None,
) -> int:
    """Count facts whose identity, value, version, or evidence set changed."""

    fact_map = fact_map or await _eligible_fact_map(database, diagnostic.client_id)
    facts = list(fact_map.values())
    evidence_by_fact = await _evidence_ids_by_fact(database, facts)
    current = {
        str(fact.id): (
            fact.key,
            fact.value,
            fact.version,
            tuple(sorted(evidence_by_fact.get(fact.id, []))),
        )
        for fact in facts
    }
    snapshot: dict[str, tuple[str, str, int, tuple[str, ...]]] = {}
    for raw in diagnostic.fact_snapshot:
        try:
            version = raw["version"]
            evidence_ids = raw["evidence_ids"]
            if not isinstance(version, int) or not isinstance(evidence_ids, list):
                return max(len(current), len(diagnostic.fact_snapshot), 1)
            snapshot[str(raw["id"])] = (
                str(raw["key"]),
                str(raw["value"]),
                version,
                tuple(sorted(str(value) for value in evidence_ids)),
            )
        except (KeyError, TypeError, ValueError):
            return max(len(current), len(diagnostic.fact_snapshot), 1)
    changed_ids = set(current) ^ set(snapshot)
    changed_shared = sum(
        current[fact_id] != snapshot[fact_id] for fact_id in set(current) & set(snapshot)
    )
    return len(changed_ids) + changed_shared


async def _diagnostic_snapshot_matches(
    database: AsyncSession,
    diagnostic: DiagnosticRun,
    fact_map: dict[str, Fact],
) -> bool:
    """Reject a stale diagnostic instead of mixing its identity with newer facts."""

    return await diagnostic_snapshot_change_count(database, diagnostic, fact_map) == 0


def _has_core_facts(client: Client, fact_map: dict[str, Fact]) -> bool:
    return bool(client.standard_name.strip() and client.district.strip()) and all(
        key in fact_map for key in CORE_FACT_KEYS
    )


def _job_accepted(job: Job, resource_type: str) -> dict[str, object]:
    return {
        "job_id": str(job.id),
        "status": job.status,
        "progress": job.progress,
        "resource_type": resource_type,
        "resource_id": None,
    }


def _new_issue(
    diagnostic: DiagnosticRun,
    *,
    category: str,
    severity: str,
    title: str,
    explanation: str,
    evidence_ids: list[str],
    suggested_action: str,
    target_page: str,
) -> DiagnosticIssue:
    return DiagnosticIssue(
        diagnostic_run_id=diagnostic.id,
        client_id=diagnostic.client_id,
        category=category,
        severity=severity,
        title=title,
        explanation=explanation,
        evidence_ids=evidence_ids,
        suggested_action=suggested_action,
        target_page=target_page,
    )


def _percentage(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return max(0, min(100, round(numerator * 100 / denominator)))


def calculate_readiness_scores(
    *,
    entity_present_count: int,
    entity_total_count: int,
    fact_count: int,
    evidenced_fact_count: int,
    question_family_count: int,
    content_type_count: int,
    public_presence_count: int | None,
    ai_visibility_score: int | None,
) -> dict[str, int | None]:
    """Calculate readiness only from records the system actually holds."""

    content_score = min(
        100,
        max(0, question_family_count) * 12 + max(0, content_type_count) * 8,
    )
    source_score = (
        None if not public_presence_count else min(100, max(0, public_presence_count) * 25)
    )
    return {
        "entity_completeness": _percentage(entity_present_count, entity_total_count),
        "evidence_coverage": _percentage(evidenced_fact_count, fact_count),
        "content_coverage": content_score,
        "source_coverage": source_score,
        "ai_visibility": ai_visibility_score,
    }


def _visibility_grade(score: int | None) -> str | None:
    if score is None:
        return None
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 50:
        return "medium"
    return "poor"


def _calculate_platform_visibility_legacy(
    *,
    platform_id: str,
    platform_name: str,
    collection_mode: str,
    evaluations: list[dict[str, object]],
    measured_at: str | None,
) -> dict[str, object]:
    """Score one platform only from successful, evaluated monitoring samples."""

    if not evaluations:
        return {
            "platform_id": platform_id,
            "platform_name": platform_name,
            "collection_mode": collection_mode,
            "status": "untested",
            "score": None,
            "grade": None,
            "comment": "尚无有效检测样本。",
            "valid_sample_count": 0,
            "measured_at": measured_at,
            "metrics": {
                "mention_rate": None,
                "association_rate": None,
                "recommendation_rate": None,
                "accuracy_rate": None,
                "stability_rate": None,
            },
        }

    discovery = [
        item for item in evaluations if item.get("question_family") != "brand_verification"
    ] or evaluations
    mentioned = [item for item in evaluations if item.get("brand_found") is True]
    recommendations = [
        item for item in evaluations if item.get("question_family") == "recommendation"
    ]
    fact_checked = [item for item in evaluations if isinstance(item.get("facts_accurate"), bool)]
    repeat_groups: dict[str, list[dict[str, object]]] = {}
    for item in discovery:
        if item.get("priority") == 1:
            repeat_groups.setdefault(str(item["question_id"]), []).append(item)
    repeat_candidates = [group for group in repeat_groups.values() if len(group) >= 2]

    mention_rate = _percentage(
        sum(item.get("brand_found") is True for item in discovery),
        len(discovery),
    )
    association_rate = _percentage(
        sum(item.get("correctly_associated") is True for item in mentioned),
        len(mentioned),
    )
    recommendation_rate = _percentage(
        sum(item.get("recommended") is True for item in recommendations),
        len(recommendations),
    )
    accuracy_rate = _percentage(
        sum(item.get("facts_accurate") is True for item in fact_checked),
        len(fact_checked),
    )
    stability_rate = _percentage(
        sum(
            sum(item.get("brand_found") is True for item in group) >= 2
            for group in repeat_candidates
        ),
        len(repeat_candidates),
    )
    score = round(
        mention_rate * 0.30
        + association_rate * 0.20
        + recommendation_rate * 0.25
        + accuracy_rate * 0.15
        + stability_rate * 0.10,
    )
    recommended = any(item.get("recommended") is True for item in evaluations)
    associated = any(
        item.get("brand_found") is True and item.get("correctly_associated") is True
        for item in evaluations
    )
    found = any(item.get("brand_found") is True for item in evaluations)
    status = (
        "recommended"
        if recommended
        else "associated"
        if associated
        else "mentioned"
        if found
        else "not_found"
    )
    metric_scores = {
        "企业提及": mention_rate,
        "正确关联": association_rate,
        "推荐命中": recommendation_rate,
        "事实准确": accuracy_rate,
        "稳定出现": stability_rate,
    }
    weak_metric = min(metric_scores, key=metric_scores.__getitem__)
    comment = (
        "企业已稳定进入回答并具备推荐表现。"
        if score >= 80
        else f"已有一定可见性，当前优先补强{weak_metric}。"
        if score >= 40
        else f"当前可见性较弱，建议优先改善{weak_metric}。"
    )
    return {
        "platform_id": platform_id,
        "platform_name": platform_name,
        "collection_mode": collection_mode,
        "status": status,
        "score": score,
        "grade": _visibility_grade(score),
        "comment": comment,
        "valid_sample_count": len(evaluations),
        "measured_at": measured_at,
        "metrics": {
            "mention_rate": mention_rate,
            "association_rate": association_rate,
            "recommendation_rate": recommendation_rate,
            "accuracy_rate": accuracy_rate,
            "stability_rate": stability_rate,
        },
    }


async def _monitoring_visibility(
    database: AsyncSession,
    client_id: UUID,
    *,
    monitoring_window_days: int,
    now: datetime,
) -> tuple[int | None, str, int, list[dict[str, object]]]:
    cutoff = now - timedelta(days=monitoring_window_days)
    rows = (
        await database.execute(
            select(MonitoringSample, MonitoringEvaluation)
            .join(
                MonitoringEvaluation,
                MonitoringEvaluation.sample_id == MonitoringSample.id,
                isouter=True,
            )
            .where(
                MonitoringSample.client_id == client_id,
                MonitoringSample.created_at >= cutoff,
            ),
        )
    ).all()
    rows_by_platform: dict[
        str,
        list[tuple[MonitoringSample, MonitoringEvaluation | None]],
    ] = {}
    for sample, evaluation in rows:
        rows_by_platform.setdefault(sample.platform_id, []).append((sample, evaluation))

    platform_results: list[dict[str, object]] = []
    effective_sample_count = 0
    for platform in PLATFORM_CATALOG:
        if not platform["active"]:
            continue
        platform_rows = rows_by_platform.get(platform["id"], [])
        evaluations: list[dict[str, object]] = []
        measured_times: list[datetime] = []
        for sample, evaluation in platform_rows:
            if sample.asked_at is not None:
                measured_times.append(sample.asked_at)
            if sample.status != "succeeded" or evaluation is None:
                continue
            evaluations.append(
                {
                    "question_id": sample.question_id,
                    "question_family": sample.question_family,
                    "priority": sample.question_priority,
                    "brand_found": evaluation.brand_found,
                    "correctly_associated": evaluation.correctly_associated,
                    "recommended": evaluation.recommended,
                    "facts_accurate": evaluation.facts_accurate,
                },
            )
        effective_sample_count += len(evaluations)
        measured_at = max(measured_times).isoformat() if measured_times else None
        result = calculate_platform_visibility(
            platform_id=platform["id"],
            platform_name=platform["name"],
            collection_mode=platform["mode"],
            evaluations=evaluations,
            measured_at=measured_at,
        )
        if (
            not evaluations
            and platform_rows
            and all(sample.status == "failed" for sample, _evaluation in platform_rows)
        ):
            result["status"] = "failed"
            result["comment"] = "最近检测失败，失败样本不计入评分。"
        platform_results.append(result)

    scored = [
        cast(int, result["score"])
        for result in platform_results
        if isinstance(result.get("score"), int)
    ]
    overall_score = round(sum(scored) / len(scored)) if scored else None
    evaluated = [
        (sample, evaluation)
        for sample, evaluation in rows
        if sample.status == "succeeded" and evaluation is not None
    ]
    non_brand = [row for row in evaluated if not row[0].is_brand_query]
    repeat_groups: dict[str, list[tuple[MonitoringSample, MonitoringEvaluation]]] = {}
    for sample, evaluation in non_brand:
        if sample.question_priority == 1:
            repeat_groups.setdefault(sample.question_id, []).append((sample, evaluation))
    repeat_successes = sum(
        sum(evaluation.brand_found for _sample, evaluation in group) >= 2
        for group in repeat_groups.values()
        if len(group) >= 2
    )
    level = "L0"
    if any(evaluation.brand_found for _sample, evaluation in non_brand):
        level = "L1"
        if any(
            evaluation.brand_found and evaluation.correctly_associated
            for _sample, evaluation in evaluated
        ):
            level = "L2"
            if any(
                evaluation.recommended and evaluation.correctly_associated
                for _sample, evaluation in non_brand
            ):
                level = "L3"
                if repeat_successes:
                    level = "L4"
    return overall_score, level, effective_sample_count, platform_results


async def process_diagnostic_job(
    session_factory: async_sessionmaker[AsyncSession],
    claimed_job: Job,
    settings: Settings,
) -> bool:
    now = datetime.now(UTC)
    async with session_factory() as database:
        await ensure_prompt_templates(database)
        await database.commit()
        async with database.begin():
            current = await database.scalar(
                select(Job)
                .where(
                    Job.id == claimed_job.id,
                    Job.status == "running",
                    Job.attempts == claimed_job.attempts,
                )
                .with_for_update(),
            )
            if current is None:
                return False
            client = await database.get(Client, current.client_id)
            if client is None:
                current.status = "failed"
                current.progress = 100
                current.error_message = "客户不存在"
                current.completed_at = now
                current.lease_until = None
                return True
            if client.status != "active":
                current.status = "failed"
                current.progress = 100
                current.error_message = "客户已暂停或归档，不能执行诊断"
                current.completed_at = now
                current.lease_until = None
                return True
            await lock_content_fact_set(database, client.id)
            fact_map = await _eligible_fact_map(database, client.id)
            if not _has_core_facts(client, fact_map):
                current.status = "failed"
                current.progress = 100
                current.error_message = "企业名称、地区或服务事实不足，无法诊断"
                current.completed_at = now
                current.lease_until = None
                return True
            facts = list(fact_map.values())
            evidence_by_fact = await _evidence_ids_by_fact(database, facts)
            core_facts = [fact_map[key] for key in CORE_FACT_KEYS]
            core_evidence = [
                evidence_id
                for fact in core_facts
                for evidence_id in evidence_by_fact.get(fact.id, [])
            ]
            profile = await database.get(KnowledgeProfile, client.id)
            presences = profile.external_presences if profile else []
            selected_scopes = cast(list[str], current.payload["scope"])
            monitoring_window_days = cast(
                int,
                current.payload["monitoring_window_days"],
            )
            question_families = set(
                (
                    await database.scalars(
                        select(StrategyItem.family).where(
                            StrategyItem.client_id == client.id,
                            StrategyItem.kind == "question",
                            StrategyItem.active.is_(True),
                            StrategyItem.family.is_not(None),
                        ),
                    )
                ).all(),
            )
            content_types = set(
                (
                    await database.scalars(
                        select(ContentBrief.content_type)
                        .join(
                            ContentDocument,
                            ContentDocument.brief_id == ContentBrief.id,
                        )
                        .where(
                            ContentDocument.client_id == client.id,
                            ContentDocument.status.in_(
                                (
                                    "draft",
                                    "blocked",
                                    "checked",
                                    "optimized",
                                    "exported",
                                    "published",
                                ),
                            ),
                        ),
                    )
                ).all(),
            )
            entity_keys = set(fact_map) & set(ENTITY_FACT_KEYS)
            if client.standard_name.strip():
                entity_keys.add("identity.standard_name")
            if client.district.strip():
                entity_keys.add("location.administrative_area")
            evidenced_fact_count = sum(bool(evidence_by_fact.get(fact.id)) for fact in facts)
            (
                ai_visibility_score,
                current_level,
                monitoring_sample_count,
                platform_results,
            ) = await run_auto_diagnostic(
                database,
                settings=settings,
                client=client,
                facts=facts,
                measured_at=now.isoformat(),
            )
            public_presence_count = sum(
                isinstance(presence, dict) and presence.get("active") is not False
                for presence in presences
            )
            scores = calculate_readiness_scores(
                entity_present_count=len(entity_keys),
                entity_total_count=len(ENTITY_FACT_KEYS),
                fact_count=len(facts),
                evidenced_fact_count=evidenced_fact_count,
                question_family_count=len(question_families),
                content_type_count=len(content_types),
                public_presence_count=public_presence_count or None,
                ai_visibility_score=ai_visibility_score,
            )
            for score_key, scope_name in {
                "entity_completeness": "entity",
                "evidence_coverage": "evidence",
                "content_coverage": "content",
                "source_coverage": "source",
                "ai_visibility": "visibility",
            }.items():
                if scope_name not in selected_scopes:
                    scores[score_key] = None
            diagnostic = DiagnosticRun(
                client_id=client.id,
                status="succeeded",
                current_level=current_level,
                scores=scores,
                scope=selected_scopes,
                monitoring_window_days=monitoring_window_days,
                platform_results=platform_results,
                monitoring_sample_count=monitoring_sample_count,
                fact_snapshot=[
                    {
                        "id": str(fact.id),
                        "key": fact.key,
                        "label": fact.label,
                        "value": fact.value,
                        "version": fact.version,
                        "evidence_ids": evidence_by_fact.get(fact.id, []),
                    }
                    for fact in facts
                ],
                completed_at=now,
            )
            database.add(diagnostic)
            await database.flush()
            issues: list[DiagnosticIssue] = []
            if scores["entity_completeness"] != 100:
                missing_labels = {
                    "identity.industry": "所属行业",
                    "location.address": "经营地址",
                    "service.details": "服务详细介绍",
                    "contact.public": "联系方式",
                    "capability.primary": "企业优势",
                }
                missing = [label for key, label in missing_labels.items() if key not in entity_keys]
                issues.append(
                    _new_issue(
                        diagnostic,
                        category="entity",
                        severity="warning",
                        title="企业实体信息仍可补强",
                        explanation=(
                            f"当前实体准备度为 {scores['entity_completeness']}%，"
                            f"建议补充 {'、'.join(missing) or '企业详细信息'}。"
                        ),
                        evidence_ids=core_evidence,
                        suggested_action="回到企业知识库补充缺少的企业信息。",
                        target_page="P02",
                    ),
                )
            if scores["evidence_coverage"] != 100:
                issues.append(
                    _new_issue(
                        diagnostic,
                        category="evidence",
                        severity="warning",
                        title="部分知识缺少资料依据",
                        explanation=(
                            f"当前 {len(facts)} 条有效知识中，"
                            f"{evidenced_fact_count} 条关联了上传资料或手工来源记录。"
                        ),
                        evidence_ids=core_evidence,
                        suggested_action="为重要企业信息补充原始资料或来源说明。",
                        target_page="P02",
                    ),
                )
            if scores["content_coverage"] != 100:
                question_coverage_complete = len(question_families) >= len(
                    QUESTION_FAMILIES,
                )
                issues.append(
                    _new_issue(
                        diagnostic,
                        category="content",
                        severity="warning",
                        title=(
                            "内容形式覆盖仍可补强"
                            if question_coverage_complete
                            else "本地需求问题覆盖不足"
                        ),
                        explanation=(
                            f"当前已覆盖 {len(question_families)}/{len(QUESTION_FAMILIES)} "
                            "类用户问题，"
                            f"形成 {len(content_types)} 类 AI 文章。"
                        ),
                        evidence_ids=core_evidence,
                        suggested_action=(
                            "围绕现有关键词补充知识科普、场景解答、选择指南等不同内容形式。"
                            if question_coverage_complete
                            else "补齐发现、推荐、场景、比较和品牌核验内容。"
                        ),
                        target_page="P04",
                    ),
                )
            if scores["source_coverage"] is None or scores["source_coverage"] != 100:
                issues.append(
                    _new_issue(
                        diagnostic,
                        category="source",
                        severity="warning",
                        title="公开来源覆盖仍需扩展",
                        explanation=(
                            f"企业服务范围为“{fact_map['location.service_area'].value}”，"
                            f"当前记录 {public_presence_count} 个公开账号或页面。"
                        ),
                        evidence_ids=core_evidence,
                        suggested_action="根据内容类型选择可公开访问的发布渠道。",
                        target_page="P06",
                    ),
                )
            if scores["ai_visibility"] is None:
                issues.append(
                    _new_issue(
                        diagnostic,
                        category="visibility",
                        severity="info",
                        title="尚无可用的 AI 平台检测结果",
                        explanation=(
                            "本次四平台自动诊断没有取得有效回答。"
                            "未配置、超时和请求失败不会被误记为企业未出现。"
                        ),
                        evidence_ids=[],
                        suggested_action="在系统设置中完成对应平台 API 配置后重新诊断。",
                        target_page="P07",
                    ),
                )
            elif current_level != "L4":
                evaluated_platform_count = sum(
                    result.get("status") not in {"unconfigured", "untested", "failed"}
                    for result in platform_results
                )
                issues.append(
                    _new_issue(
                        diagnostic,
                        category="visibility",
                        severity="warning",
                        title="AI 可见性仍需提升",
                        explanation=(
                            f"本次自动诊断在 {evaluated_platform_count} 个平台取得 "
                            f"{monitoring_sample_count} 个有效回答，"
                            f"当前达到 {current_level}。"
                        ),
                        evidence_ids=[],
                        suggested_action="根据未提及、关联不足或未进入推荐的问题安排下一轮内容。",
                        target_page="P07",
                    ),
                )
            database.add_all(issue for issue in issues if issue.category in selected_scopes)
            client.current_level = current_level
            client.next_action = {
                "L0": "生成首批关键词策略",
                "L1": "补强地区、服务与客群关联",
                "L2": "补充可核实的推荐理由内容",
                "L3": "扩大跨平台和跨时间复测",
                "L4": "保持发布节奏并定期复测",
            }[current_level]
            current.status = "succeeded"
            current.progress = 100
            current.completed_at = now
            current.lease_until = None
        return True


def _service_topics(
    service: str,
    *,
    brand: str = "",
    audience: str = "",
) -> list[str]:
    source = " ".join((service, audience))
    topics: list[str] = []
    if any(
        marker in source
        for marker in ("美术", "素描", "动漫", "国画", "绘画", "水粉", "水彩", "线描", "彩铅")
    ):
        topics.append(
            "少儿美术培训"
            if any(marker in source for marker in ("少儿", "儿童", "孩子", "4-", "4—"))
            else "美术培训",
        )
    if any(marker in source for marker in ("硬笔", "软笔", "书法")):
        topics.append("硬笔书法" if "硬笔" in source else "书法培训")
    if not topics:
        for part in re.split(r"[\n,\uFF0C\u3001;\uFF1B:\uFF1A/]+", service):
            candidate = part.strip(" .;\u3002\uff1b\uff0c\u3001")
            if 2 <= len(candidate) <= 18 and candidate not in topics:
                topics.append(candidate)
            if len(topics) >= 3:
                break
    return topics or [service.strip()[:18] or "本地服务"]


def _strategy_templates(
    *,
    brand: str,
    district: str,
    service: str,
    audience: str,
) -> list[dict[str, object]]:
    district = compact_search_area(district)
    service = compact_search_service(service, audience)
    audience_label = (
        "孩子"
        if any(marker in audience for marker in ("少儿", "儿童", "孩子", "青少年", "幼儿"))
        else "有相关需求的人"
    )
    education_service = any(
        marker in service for marker in ("美术", "书法", "培训", "教育", "课程")
    )
    scenario_query = (
        f"{audience_label}适合什么{service}课程"
        if education_service
        else f"需要{service}时要注意什么"
    )
    scenario_question = (
        f"{audience_label}学{service}要注意什么" if education_service else scenario_query
    )
    basis = (
        f"依据已确认事实: 企业“{brand}”、服务地区“{district}”、"
        f"核心服务“{service}”、适用对象“{audience}”。"
    )
    keyword_specs = [
        (
            f"{district}{service}",
            f"{district}{service}机构",
            "local_service",
            "寻找本地服务机构",
            1,
        ),
        (
            f"{district}{service}",
            f"{district}{service}推荐",
            "local_service",
            "了解本地候选机构",
            1,
        ),
        (
            f"{district}{service}",
            f"{district}{service}哪家好",
            "local_service",
            "比较本地服务机构",
            1,
        ),
        (brand, f"{brand}怎么样", "brand", "了解企业口碑与基本情况", 1),
        (brand, f"{brand}好吗", "brand", "判断企业是否适合", 1),
        (brand, f"{brand}有哪些{service}服务", "brand", "核实品牌主营业务", 2),
        (
            f"{district}{service}",
            f"请推荐一家{district}的{service}机构",
            "recommendation",
            "请求明确推荐候选",
            1,
        ),
        (
            f"{district}{service}",
            f"{district}值得了解的{service}机构",
            "recommendation",
            "寻找值得进一步咨询的候选",
            1,
        ),
        (
            f"{district}{service}",
            f"{district}{service}怎么选",
            "recommendation",
            "获取选择标准",
            1,
        ),
        (
            service,
            scenario_query,
            "scenario",
            "按人群和需求匹配服务",
            2,
        ),
        (
            service,
            f"第一次了解{service}需要确认什么",
            "scenario",
            "首次咨询前获取信息",
            2,
        ),
        (
            f"{district}{service}",
            f"{district}{service}适合哪些人",
            "scenario",
            "确认服务适用人群",
            2,
        ),
        (
            service,
            f"{district}{service}包括哪些内容",
            "service_detail",
            "了解具体服务项目",
            2,
        ),
        (
            service,
            f"{service}咨询前要了解什么",
            "service_detail",
            "了解服务流程和边界",
            2,
        ),
        (
            f"{district}{service}",
            f"{district}{service}机构主要看什么",
            "comparison",
            "比较机构条件",
            2,
        ),
        (
            f"{district}{service}",
            f"比较{district}{service}服务要注意什么",
            "comparison",
            "规避选择风险",
            2,
        ),
        (
            f"{district}{service}",
            f"{district}{service}费用和服务怎么比较",
            "comparison",
            "比较费用与服务内容",
            3,
        ),
        (
            f"{district}{service}",
            f"{district}{service}一般怎么收费",
            "transaction",
            "了解费用构成与询价方法",
            2,
        ),
        (
            service,
            f"{service}咨询和预约流程是什么",
            "transaction",
            "了解咨询预约与服务流程",
            2,
        ),
        (
            brand,
            f"{brand}的企业信息和服务范围怎么核实",
            "trust",
            "核验品牌身份与服务信息",
            2,
        ),
        (
            f"{district}{service}",
            f"选择{district}{service}机构要核实哪些信息",
            "trust",
            "核验机构信息与可信依据",
            2,
        ),
    ]
    keywords: list[dict[str, object]] = [
        {
            "kind": "keyword",
            "main_keyword": main_keyword,
            "text": text,
            "keyword_type": keyword_type,
            "user_intent": user_intent,
            "recommended_content_type": KEYWORD_CONTENT_FORM_DEFAULTS[keyword_type],
            "target_level": (
                "L3"
                if keyword_type == "recommendation"
                else "L2"
                if keyword_type == "brand"
                else "L1"
            ),
            "priority": priority,
            "rationale": (
                f"{basis} 用户意图为“{user_intent}”，"
                "该建议来自企业资料与语义推导，不代表外部查询热度或平台收录结果。"
            ),
        }
        for main_keyword, text, keyword_type, user_intent, priority in keyword_specs
    ]
    return [
        *keywords,
        {
            "kind": "question",
            "family": "discovery",
            "text": f"{district}{service}",
            "target_level": "L1",
            "priority": 1,
            "rationale": f"{basis} 这是不含品牌名的品类发现问题。",
        },
        {
            "kind": "question",
            "family": "recommendation",
            "text": f"{district}{service}哪家好",
            "target_level": "L3",
            "priority": 1,
            "rationale": f"{basis} 先建立可核实的推荐理由，不做无依据的推荐承诺。",
        },
        {
            "kind": "question",
            "family": "scenario",
            "text": scenario_question,
            "target_level": "L2",
            "priority": 2,
            "rationale": f"{basis} 将适用对象与真实服务场景组合。",
        },
        {
            "kind": "question",
            "family": "comparison",
            "text": f"{district}{service}机构怎么选",
            "target_level": "L3",
            "priority": 2,
            "rationale": f"{basis} 提供选择标准，不生成虚假榜单或竞品结论。",
        },
        {
            "kind": "question",
            "family": "brand_verification",
            "text": f"{brand}怎么样",
            "target_level": "L2",
            "priority": 1,
            "rationale": f"{basis} 用于核验品牌、地区和服务能否被正确关联。",
        },
    ]


async def _strategy_templates_for_job(
    database: AsyncSession,
    settings: Settings,
    provider_client: ProviderClient,
    *,
    client: Client,
    diagnostic: DiagnosticRun,
    fact_map: dict[str, Fact],
    brand: str,
    district: str,
    service: str,
    audience: str,
) -> list[dict[str, object]]:
    service_topics = _service_topics(service, brand=brand, audience=audience)
    district = compact_search_area(district)
    primary_service = compact_search_service(service_topics[0], audience)
    service_topics = list(
        dict.fromkeys(compact_search_service(topic, audience) for topic in service_topics),
    )
    fallback = _strategy_templates(
        brand=brand,
        district=district,
        service=primary_service,
        audience=audience,
    )
    if settings.model_execution_mode == "fixed_mock":
        return fallback

    from app.content import _execute_model_step, _parse_model_json

    fact_context = [
        {
            "key": fact.key,
            "label": fact.label,
            "value": fact.value,
        }
        for fact in fact_map.values()
    ]
    keyword_prompt = await database.scalar(
        select(PromptTemplate).where(
            PromptTemplate.code == "keyword_strategy",
            PromptTemplate.active.is_(True),
        ),
    )
    editable_keyword_rules = (
        keyword_prompt.template_text
        if keyword_prompt is not None
        else ("覆盖地区主营、品牌核验、推荐决策、场景适配、费用流程、信任验证和用户后续追问。")
    )
    variable_values = {
        "所在地区": district,
        "所属行业": client.industry_name,
        "主营业务": "、".join(service_topics),
        "企业标准名称": brand,
        "企业事实": "；".join(f"{item['label']}：{item['value']}" for item in fact_context),
    }
    for variable, value in variable_values.items():
        editable_keyword_rules = re.sub(
            r"\{\{\s*" + re.escape(variable) + r"\s*\}\}",
            value,
            editable_keyword_rules,
        )
    try:
        result = await _execute_model_step(
            database,
            settings,
            provider_client,
            client_id=client.id,
            fact_snapshot_id=diagnostic.fact_snapshot_id,
            purpose="writer",
            step="keyword_strategy",
            system_prompt=(
                "你是本地服务 GEO 关键词策略师。只依据输入的企业事实生成中文关键词，"
                "输出 JSON 对象 items。每项必须包含 main_keyword、long_tail_keyword、"
                "keyword_type、user_intent、priority、recommended_content_type。"
                "keyword_type 只能是 local_service、brand、recommendation、scenario、"
                "service_detail、comparison、transaction、trust。"
                "生成 16—28 条自然语言问题，覆盖全部八类。不得虚构服务、地区、年龄、"
                "资质、价格、案例、排名、口碑或效果，不输出搜索量或竞争度。"
                "问题必须像普通消费者会直接输入AI的短查询，通常不超过28个汉字。"
                "先从资料中提炼一个地区、一个核心品类或一个品牌，再组合问题；"
                "如果主营事实是一段服务清单，只提炼代表性品类，禁止把整段课程、"
                "产品、人群或年龄清单直接拼进关键词。地区可用消费者常用简称，"
                "例如“即墨区”写成“即墨”。地区主营可写“即墨少儿美术”，"
                "推荐决策可写“即墨少儿美术哪家好”或“请推荐一家即墨的少儿美术机构”，"
                "品牌核验可写“莱恩美术怎么样”；不要追加服务清单或适用对象说明。"
                "同义问题要合并，避免仅替换“哪家好、推荐、怎么样”的机械变体。"
                f"\n\n运营配置的关键词策略：\n{editable_keyword_rules}"
            ),
            user_prompt=json.dumps(
                {
                    "client": {
                        "name": brand,
                        "district": district,
                        "industry": client.industry_name,
                        "service": primary_service,
                        "service_topics": service_topics,
                        "audience": audience,
                    },
                    "facts": fact_context,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            schema=KeywordSuggestionOutput,
        )
    except ApiFailure as failure:
        if failure.code != 50201:
            raise
        fallback[0]["generation_notice"] = (
            "模型返回结构仍不稳定，本次已使用企业资料生成安全备选关键词，"
            "旧关键词保留在历史记录，当前列表已替换为安全备选。"
        )
        return fallback
    parsed_output = cast(
        KeywordSuggestionOutput,
        _parse_model_json(result.content, KeywordSuggestionOutput),
    )
    parsed = normalize_keyword_suggestions(parsed_output)

    generated: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in parsed:
        text = item.long_tail_keyword.strip()
        if (
            text in seen
            or not keyword_suggestion_is_supported(
                item,
                brand=brand,
                district=district,
                service_topics=service_topics,
            )
            or not keyword_suggestion_is_natural(
                item,
                audience=audience,
            )
        ):
            continue
        seen.add(text)
        generated.append(
            {
                "kind": "keyword",
                "main_keyword": item.main_keyword.strip(),
                "text": text,
                "keyword_type": item.keyword_type,
                "user_intent": item.user_intent.strip(),
                "recommended_content_type": item.recommended_content_type
                or KEYWORD_CONTENT_FORM_DEFAULTS[item.keyword_type],
                "target_level": (
                    "L3"
                    if item.keyword_type == "recommendation"
                    else "L2"
                    if item.keyword_type == "brand"
                    else "L1"
                ),
                "priority": item.priority,
                "rationale": (
                    "由 AI 根据当前企业名称、地区、行业、主营业务、目标人群和企业资料"
                    f"生成，用户意图为“{item.user_intent.strip()}”。"
                ),
                "provenance": "ai_generated",
            },
        )
        if len(generated) >= 18:
            break
    complete_keyword_categories(generated, fallback, seen)
    questions = [item for item in fallback if item["kind"] == "question"]
    return [*generated, *questions]


async def process_strategy_job(
    session_factory: async_sessionmaker[AsyncSession],
    claimed_job: Job,
    settings: Settings,
    provider_client: ProviderClient | None = None,
) -> bool:
    now = datetime.now(UTC)
    async with session_factory() as database:
        async with database.begin():
            current = await database.scalar(
                select(Job)
                .where(
                    Job.id == claimed_job.id,
                    Job.status == "running",
                    Job.attempts == claimed_job.attempts,
                )
                .with_for_update(),
            )
            if current is None:
                return False
            client = await database.get(Client, current.client_id)
            diagnostic_id = UUID(str(current.payload["diagnostic_run_id"]))
            diagnostic = await database.get(DiagnosticRun, diagnostic_id)
            await lock_content_fact_set(database, current.client_id)
            snapshot_fact_ids = (
                [UUID(str(item["id"])) for item in diagnostic.fact_snapshot]
                if diagnostic is not None
                else []
            )
            locked_fact_ids = set(
                (
                    await database.scalars(
                        select(Fact.id)
                        .where(
                            Fact.client_id == current.client_id,
                            Fact.id.in_(snapshot_fact_ids),
                        )
                        .order_by(Fact.id)
                        .with_for_update(),
                    )
                ).all(),
            )
            fact_map = (
                await _eligible_fact_map(database, current.client_id) if client is not None else {}
            )
            snapshot_matches = (
                await _diagnostic_snapshot_matches(database, diagnostic, fact_map)
                if diagnostic is not None
                else False
            )
            if (
                client is None
                or client.status != "active"
                or diagnostic is None
                or diagnostic.client_id != current.client_id
                or diagnostic.status != "succeeded"
                or not _has_core_facts(client, fact_map)
                or locked_fact_ids != set(snapshot_fact_ids)
                or not snapshot_matches
            ):
                current.status = "failed"
                current.progress = 100
                current.error_message = "诊断使用的事实已变化，请重新运行诊断"
                current.completed_at = now
                current.lease_until = None
                return True
            bundle = await database.scalar(
                select(StrategyBundle)
                .where(StrategyBundle.client_id == client.id)
                .with_for_update(),
            )
            existing_items = (
                list(
                    (
                        await database.scalars(
                            select(StrategyItem)
                            .where(StrategyItem.bundle_id == bundle.id)
                            .with_for_update(),
                        )
                    ).all(),
                )
                if bundle is not None
                else []
            )
            service = fact_map["service.primary"].value
            audience = fact_map["audience.primary"].value
            district = fact_map["location.service_area"].value
            locked_items: list[StrategyItem] = []
            for item in existing_items:
                if not item.active:
                    continue
                if item.locked:
                    locked_items.append(item)
                    continue
                if not item.selected:
                    continue
                if item.provenance == "ai_generated" and not stored_keyword_is_natural(
                    item,
                    audience=audience,
                ):
                    item.selected = False
                    item.active = False
                    item.version += 1
                    continue
                locked_items.append(item)
            included_families = set(
                cast(list[str], current.payload["include_families"]),
            )
            try:
                templates = await _strategy_templates_for_job(
                    database,
                    settings,
                    provider_client or ProviderClient(),
                    client=client,
                    diagnostic=diagnostic,
                    fact_map=fact_map,
                    brand=client.standard_name,
                    district=district,
                    service=service,
                    audience=audience,
                )
            except ApiFailure as failure:
                current.status = "failed"
                current.progress = 100
                current.error_message = failure.message
                current.completed_at = now
                current.lease_until = None
                return True
            keyword_prompt = await database.scalar(
                select(PromptTemplate).where(
                    PromptTemplate.code == "keyword_strategy",
                    PromptTemplate.active.is_(True),
                ),
            )
            if bundle is None:
                bundle = StrategyBundle(
                    client_id=client.id,
                    diagnostic_run_id=diagnostic.id,
                    prompt_template_code=(
                        keyword_prompt.code if keyword_prompt is not None else None
                    ),
                    prompt_template_version=(
                        keyword_prompt.current_version if keyword_prompt is not None else None
                    ),
                    generated_at=now,
                )
                database.add(bundle)
                await database.flush()
            else:
                bundle.diagnostic_run_id = diagnostic.id
                bundle.prompt_template_code = (
                    keyword_prompt.code if keyword_prompt is not None else None
                )
                bundle.prompt_template_version = (
                    keyword_prompt.current_version if keyword_prompt is not None else None
                )
                bundle.generated_at = now
                bundle.version += 1
            generation_notice = next(
                (
                    str(template["generation_notice"])
                    for template in templates
                    if template.get("generation_notice")
                ),
                None,
            )
            for item in existing_items:
                if item.active and not item.locked and not item.selected:
                    item.active = False
                    item.version += 1

            def has_locked_equivalent(template: dict[str, object]) -> bool:
                return any(
                    item.kind == template["kind"]
                    and (
                        item.family == template.get("family")
                        if item.kind == "question"
                        else item.text == template["text"]
                    )
                    for item in locked_items
                )

            generated_items: list[StrategyItem] = []
            for template in templates:
                family = template.get("family")
                if family is not None and family not in included_families:
                    continue
                if has_locked_equivalent(template):
                    continue
                generated_items.append(
                    StrategyItem(
                        bundle_id=bundle.id,
                        client_id=client.id,
                        kind=str(template["kind"]),
                        text=str(template["text"]),
                        family=str(family) if family else None,
                        keyword_type=(
                            str(template["keyword_type"]) if template.get("keyword_type") else None
                        ),
                        provenance=str(
                            template.get("provenance", "system_inference"),
                        ),
                        target_level=str(template["target_level"]),
                        priority=cast(int, template["priority"]),
                        rationale=str(template["rationale"]),
                        main_keyword=(
                            str(template["main_keyword"]) if template.get("main_keyword") else None
                        ),
                        user_intent=(
                            str(template["user_intent"]) if template.get("user_intent") else None
                        ),
                        recommended_content_type=(
                            str(template["recommended_content_type"])
                            if template.get("recommended_content_type")
                            else None
                        ),
                    ),
                )
            database.add_all(generated_items)
            await database.flush()
            active_questions = [
                item
                for item in [*locked_items, *generated_items]
                if item.kind == "question" and item.active
            ]
            active_keywords = [
                item.text
                for item in [*locked_items, *generated_items]
                if item.kind == "keyword" and item.active
            ]
            await database.execute(
                update(ContentBrief)
                .where(
                    ContentBrief.bundle_id == bundle.id,
                    ContentBrief.status != "archived",
                )
                .values(
                    status="archived",
                    version=ContentBrief.version + 1,
                ),
            )
            facts = list(fact_map.values())
            evidence_by_fact = await _evidence_ids_by_fact(database, facts)
            required_fact_ids = [str(fact.id) for fact in facts]
            required_evidence_ids = [
                evidence_id for fact in facts for evidence_id in evidence_by_fact.get(fact.id, [])
            ]
            profile = await database.get(KnowledgeProfile, client.id)
            prohibited_claims = [
                str(item.get("phrase", ""))
                for item in (profile.prohibited_claims if profile else [])
                if item.get("phrase")
            ]
            brief_specs = [
                (
                    f"{district}{service}怎么选: 公开信息核验指南",
                    "selection_guide",
                    "直接回答消费者如何选择，用客户已确认事实说明服务边界、适用对象和核验方法。",
                    "公开事实完整、服务边界清楚，能够作为可核实的候选信息。",
                    "L3",
                ),
                (
                    f"{client.standard_name}在{district}提供什么服务",
                    "entity_profile",
                    "建立企业名称、地区、核心服务和适用对象之间的清晰实体关系。",
                    "品牌与地区、服务和客群之间存在一致且可追溯的公开说明。",
                    "L2",
                ),
                (
                    f"{district}{service}常见咨询问题",
                    "faq",
                    "用独立可摘取的问答覆盖发现、场景、比较和推荐决策问题。",
                    "围绕真实服务条件回答具体问题，不使用排名、保证或虚假评价。",
                    "L1",
                ),
            ]
            requested_count = cast(int, current.payload["brief_count"])
            selected_specs = [
                brief_specs[index % len(brief_specs)] for index in range(requested_count)
            ]
            briefs = [
                ContentBrief(
                    bundle_id=bundle.id,
                    client_id=client.id,
                    title=(
                        title
                        if index < len(brief_specs)
                        else (
                            f"{title}｜"
                            f"{
                                BRIEF_TITLE_LENSES[
                                    (index // len(brief_specs) - 1) % len(BRIEF_TITLE_LENSES)
                                ]
                            }"
                        )
                    ),
                    content_type=content_type,
                    target_question_ids=[str(item.id) for item in active_questions],
                    target_keywords=active_keywords,
                    target_level=target_level,
                    audience=audience,
                    angle=angle,
                    required_fact_ids=required_fact_ids,
                    required_evidence_ids=required_evidence_ids,
                    expected_recommendation_reason=recommendation_reason,
                    prohibited_claims=prohibited_claims,
                    retest_questions=[item.text for item in active_questions],
                    suggested_channel_ids=list(
                        DEFAULT_CHANNELS_BY_CONTENT_TYPE.get(
                            content_type,
                            ["sohu", "baijia", "toutiao"],
                        ),
                    ),
                    priority=1 if index == 0 else 2 if index < 3 else 3,
                )
                for index, (
                    title,
                    content_type,
                    angle,
                    recommendation_reason,
                    target_level,
                ) in enumerate(selected_specs)
            ]
            database.add_all(briefs)
            client.next_action = "按优先级生成首批 GEO 内容"
            current.status = "succeeded"
            current.progress = 100
            current.error_message = generation_notice
            current.completed_at = now
            current.lease_until = None
        return True


async def _validate_brief_references(
    database: AsyncSession,
    client_id: UUID,
    *,
    fact_ids: list[UUID],
    evidence_ids: list[UUID],
    question_ids: list[UUID] | None = None,
) -> bool:
    if not fact_ids or not evidence_ids:
        return False
    eligible_fact_ids = {fact.id for fact in await list_content_eligible_facts(database, client_id)}
    requested_fact_ids = set(fact_ids)
    requested_evidence_ids = set(evidence_ids)
    if not requested_fact_ids.issubset(eligible_fact_ids):
        return False
    linked_rows = (
        await database.execute(
            select(FactEvidence.fact_id, FactEvidence.evidence_id)
            .join(Evidence, Evidence.id == FactEvidence.evidence_id)
            .where(
                FactEvidence.fact_id.in_(requested_fact_ids),
                FactEvidence.evidence_id.in_(requested_evidence_ids),
                Evidence.client_id == client_id,
                Evidence.authorization_status.in_(PUBLIC_AUTHORIZATIONS),
            ),
        )
    ).all()
    if {fact_id for fact_id, _ in linked_rows} != requested_fact_ids:
        return False
    if {evidence_id for _, evidence_id in linked_rows} != requested_evidence_ids:
        return False
    if question_ids:
        question_count = len(
            (
                await database.scalars(
                    select(StrategyItem.id).where(
                        StrategyItem.client_id == client_id,
                        StrategyItem.kind == "question",
                        StrategyItem.active.is_(True),
                        StrategyItem.id.in_(question_ids),
                    ),
                )
            ).all(),
        )
        if question_count != len(set(question_ids)):
            return False
    return True


def build_strategy_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["strategy"])

    @router.post("/clients/{client_id}/diagnostics")
    async def create_diagnostic(
        request: Request,
        client_id: UUID,
        body: DiagnosticInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
        idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    ) -> Response:
        client = await database.get(Client, client_id)
        if client is None:
            return error_response(request, status_code=404, code=40401, message="客户不存在")
        if client.status != "active":
            return error_response(
                request,
                status_code=409,
                code=40901,
                message="客户已暂停或归档，不能创建诊断任务",
            )
        fact_map = await _eligible_fact_map(database, client_id)
        if not _has_core_facts(client, fact_map):
            return error_response(
                request,
                status_code=422,
                code=42201,
                message="企业名称、地区或服务事实不足，无法诊断",
            )
        key = str(idempotency_key)
        payload = body.model_dump(mode="json")
        existing = await database.scalar(
            select(Job).where(
                Job.client_id == client_id,
                Job.job_type == "diagnostic",
                Job.idempotency_key == key,
            ),
        )
        if existing is not None:
            if existing.payload != payload:
                return error_response(
                    request,
                    status_code=409,
                    code=40903,
                    message="幂等键已用于不同的诊断参数",
                )
            return success_response(
                request,
                _job_accepted(existing, "diagnostic"),
                status_code=202,
            )
        job = Job(
            client_id=client_id,
            job_type="diagnostic",
            idempotency_key=key,
            payload=payload,
        )
        database.add(job)
        try:
            await database.commit()
        except IntegrityError:
            await database.rollback()
            existing = await database.scalar(
                select(Job).where(
                    Job.client_id == client_id,
                    Job.job_type == "diagnostic",
                    Job.idempotency_key == key,
                ),
            )
            if existing is None:
                raise
            if existing.payload != payload:
                return error_response(
                    request,
                    status_code=409,
                    code=40903,
                    message="幂等键已用于不同的诊断参数",
                )
            job = existing
        return success_response(
            request,
            _job_accepted(job, "diagnostic"),
            status_code=202,
        )

    @router.get("/clients/{client_id}/diagnostics/latest")
    async def get_latest_diagnostic(
        request: Request,
        client_id: UUID,
        database: DatabaseSession,
        authentication: Authenticated,
    ) -> Response:
        if await database.get(Client, client_id) is None:
            return error_response(request, status_code=404, code=40401, message="客户不存在")
        diagnostic = await database.scalar(
            select(DiagnosticRun)
            .where(DiagnosticRun.client_id == client_id)
            .order_by(DiagnosticRun.created_at.desc(), DiagnosticRun.id.desc())
            .limit(1),
        )
        data = await _diagnostic_data(database, diagnostic) if diagnostic is not None else None
        return success_response(request, data)

    @router.patch("/diagnostic-issues/{issue_id}")
    async def update_diagnostic_issue(
        request: Request,
        issue_id: UUID,
        body: DiagnosticIssueInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        issue = await database.scalar(
            select(DiagnosticIssue).where(DiagnosticIssue.id == issue_id).with_for_update(),
        )
        if issue is None:
            return error_response(
                request,
                status_code=404,
                code=40401,
                message="诊断问题不存在",
            )
        if issue.version != body.version:
            return error_response(
                request,
                status_code=409,
                code=40901,
                message="诊断问题已被更新，请刷新后重试",
            )
        issue.status = body.status
        issue.note = body.note
        issue.version += 1
        await database.commit()
        return success_response(request, _issue_data(issue))

    @router.post("/clients/{client_id}/strategy/generate")
    async def create_strategy(
        request: Request,
        client_id: UUID,
        body: StrategyGenerateInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
        idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    ) -> Response:
        client = await database.scalar(
            select(Client).where(Client.id == client_id).with_for_update(),
        )
        diagnostic = await database.get(DiagnosticRun, body.diagnostic_run_id)
        fact_map = await _eligible_fact_map(database, client_id) if client is not None else {}
        if client is not None and client.status != "active":
            return error_response(
                request,
                status_code=409,
                code=40901,
                message="客户已暂停或归档，不能生成策略",
            )
        if (
            client is None
            or diagnostic is None
            or diagnostic.client_id != client_id
            or diagnostic.status != "succeeded"
            or not _has_core_facts(client, fact_map)
        ):
            return error_response(
                request,
                status_code=422,
                code=42201,
                message="诊断或事实不满足策略生成条件",
            )
        if not await _diagnostic_snapshot_matches(database, diagnostic, fact_map):
            return error_response(
                request,
                status_code=422,
                code=42201,
                message="诊断使用的事实已变化，请重新运行诊断",
            )
        key = str(idempotency_key)
        payload = body.model_dump(mode="json")
        existing = await database.scalar(
            select(Job).where(
                Job.client_id == client_id,
                Job.job_type == "strategy_generate",
                Job.idempotency_key == key,
            ),
        )
        if existing is not None:
            if existing.payload != payload:
                return error_response(
                    request,
                    status_code=409,
                    code=40903,
                    message="幂等键已用于不同的策略参数",
                )
            return success_response(
                request,
                _job_accepted(existing, "strategy"),
                status_code=202,
            )
        active_jobs = list(
            (
                await database.scalars(
                    select(Job)
                    .where(
                        Job.client_id == client_id,
                        Job.job_type == "strategy_generate",
                        Job.status.in_(("queued", "running")),
                    )
                    .order_by(Job.created_at.desc()),
                )
            ).all(),
        )
        active_matching_job = next(
            (active_job for active_job in active_jobs if active_job.payload == payload),
            None,
        )
        if active_matching_job is not None:
            return success_response(
                request,
                _job_accepted(active_matching_job, "strategy"),
                status_code=202,
            )
        job = Job(
            client_id=client_id,
            job_type="strategy_generate",
            idempotency_key=key,
            payload=payload,
        )
        database.add(job)
        try:
            await database.commit()
        except IntegrityError:
            await database.rollback()
            existing = await database.scalar(
                select(Job).where(
                    Job.client_id == client_id,
                    Job.job_type == "strategy_generate",
                    Job.idempotency_key == key,
                ),
            )
            if existing is None:
                raise
            if existing.payload != payload:
                return error_response(
                    request,
                    status_code=409,
                    code=40903,
                    message="幂等键已用于不同的策略参数",
                )
            job = existing
        return success_response(
            request,
            _job_accepted(job, "strategy"),
            status_code=202,
        )

    @router.get("/clients/{client_id}/strategy")
    async def get_strategy(
        request: Request,
        client_id: UUID,
        database: DatabaseSession,
        authentication: Authenticated,
        active_only: Annotated[bool, Query()] = True,
    ) -> Response:
        if await database.get(Client, client_id) is None:
            return error_response(request, status_code=404, code=40401, message="客户不存在")
        bundle = await database.scalar(
            select(StrategyBundle).where(StrategyBundle.client_id == client_id),
        )
        data = (
            await _strategy_data(database, bundle, active_only=active_only)
            if bundle is not None
            else None
        )
        return success_response(request, data)

    @router.patch("/strategy-items/{item_id}")
    async def update_strategy_item(
        request: Request,
        item_id: UUID,
        body: StrategyItemInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        item_bundle_id = await database.scalar(
            select(StrategyItem.bundle_id).where(StrategyItem.id == item_id),
        )
        if item_bundle_id is None:
            return error_response(
                request,
                status_code=404,
                code=40401,
                message="策略项不存在",
            )
        await database.scalar(
            select(StrategyBundle).where(StrategyBundle.id == item_bundle_id).with_for_update(),
        )
        item = await database.scalar(
            select(StrategyItem).where(StrategyItem.id == item_id).with_for_update(),
        )
        if item is None:
            return error_response(
                request,
                status_code=404,
                code=40401,
                message="策略项不存在",
            )
        if item.version != body.version:
            return error_response(
                request,
                status_code=409,
                code=40901,
                message="策略项已被更新，请刷新后重试",
            )
        if body.text is not None:
            item.text = body.text.strip()
        if body.main_keyword is not None:
            item.main_keyword = body.main_keyword.strip()
        if body.user_intent is not None:
            item.user_intent = body.user_intent.strip()
        if body.keyword_type is not None:
            item.keyword_type = body.keyword_type
        if body.recommended_content_type is not None:
            item.recommended_content_type = body.recommended_content_type
        if body.priority is not None:
            item.priority = body.priority
        if body.locked is not None:
            item.locked = body.locked
        if body.selected is not None:
            item.selected = body.selected
        if body.active is not None:
            item.active = body.active
            if not body.active:
                item.selected = False
        item.version += 1
        await database.commit()
        return success_response(request, _strategy_item_data(item))

    @router.post("/clients/{client_id}/briefs")
    async def create_brief(
        request: Request,
        client_id: UUID,
        body: BriefCreateInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        bundle = await database.scalar(
            select(StrategyBundle).where(StrategyBundle.client_id == client_id),
        )
        if bundle is None or not await _validate_brief_references(
            database,
            client_id,
            fact_ids=body.required_fact_ids,
            evidence_ids=body.required_evidence_ids,
            question_ids=body.target_question_ids,
        ):
            return error_response(
                request,
                status_code=422,
                code=42201,
                message="简报缺少目标问题或必需事实",
            )
        brief = ContentBrief(
            bundle_id=bundle.id,
            client_id=client_id,
            **body.model_dump(mode="json"),
        )
        database.add(brief)
        await database.commit()
        return success_response(request, _brief_data(brief), status_code=201)

    @router.get("/briefs/{brief_id}")
    async def get_brief(
        request: Request,
        brief_id: UUID,
        database: DatabaseSession,
        authentication: Authenticated,
    ) -> Response:
        brief = await database.get(ContentBrief, brief_id)
        if brief is None:
            return error_response(
                request,
                status_code=404,
                code=40401,
                message="内容简报不存在",
            )
        return success_response(request, _brief_data(brief))

    @router.patch("/briefs/{brief_id}")
    async def update_brief(
        request: Request,
        brief_id: UUID,
        body: BriefUpdateInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        brief = await database.scalar(
            select(ContentBrief).where(ContentBrief.id == brief_id).with_for_update(),
        )
        if brief is None:
            return error_response(
                request,
                status_code=404,
                code=40401,
                message="内容简报不存在",
            )
        if brief.version != body.version:
            return error_response(
                request,
                status_code=409,
                code=40901,
                message="内容简报已被更新，请刷新后重试",
            )
        changes = body.model_dump(exclude={"version"}, exclude_none=True, mode="json")
        fact_ids = [
            UUID(value) for value in changes.get("required_fact_ids", brief.required_fact_ids)
        ]
        evidence_ids = [
            UUID(value)
            for value in changes.get(
                "required_evidence_ids",
                brief.required_evidence_ids,
            )
        ]
        if (
            "required_fact_ids" in changes or "required_evidence_ids" in changes
        ) and not await _validate_brief_references(
            database,
            brief.client_id,
            fact_ids=fact_ids,
            evidence_ids=evidence_ids,
        ):
            return error_response(
                request,
                status_code=422,
                code=42201,
                message="简报缺少目标问题或必需事实",
            )
        for field, value in changes.items():
            setattr(brief, field, value)
        brief.version += 1
        await database.commit()
        return success_response(request, _brief_data(brief))

    return router
