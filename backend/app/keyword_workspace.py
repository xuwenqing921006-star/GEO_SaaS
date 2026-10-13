# ruff: noqa: RUF001

import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from hashlib import sha256
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth import Authenticated, CsrfAuthenticated
from app.config import Settings
from app.database import (
    Client,
    DatabaseSession,
    DiagnosticRun,
    Fact,
    Job,
    KeywordCandidate,
    KeywordGeneration,
    KeywordProfile,
    PromptTemplate,
    StrategyBundle,
    StrategyItem,
)
from app.diagnostic_probes import compact_search_area
from app.knowledge_context import list_content_eligible_facts, lock_content_fact_set
from app.providers import ProviderClient
from app.responses import ApiFailure, error_response, success_response
from app.strategy import KeywordSuggestionOutput, _service_topics

KeywordType = Literal[
    "local_service",
    "brand",
    "recommendation",
    "scenario",
    "service_detail",
    "comparison",
    "transaction",
    "trust",
]

KEYWORD_TYPES: tuple[str, ...] = (
    "local_service",
    "brand",
    "recommendation",
    "scenario",
    "service_detail",
    "comparison",
    "transaction",
    "trust",
)

CONTENT_TYPE_BY_KEYWORD_TYPE = {
    "local_service": "local_presence",
    "brand": "entity_profile",
    "recommendation": "selection_guide",
    "scenario": "scenario_solution",
    "service_detail": "service_explainer",
    "comparison": "comparison",
    "transaction": "price_guide",
    "trust": "faq",
}

INTENT_BY_KEYWORD_TYPE = {
    "local_service": "发现本地相关服务",
    "brand": "了解企业品牌与服务",
    "recommendation": "获得本地机构选择建议",
    "scenario": "判断具体需求是否适配",
    "service_detail": "了解具体服务项目",
    "comparison": "比较并选择合适机构",
    "transaction": "了解费用、流程与咨询方式",
    "trust": "核验企业信息与可信度",
}


def _dedupe_strings(values: list[str], *, limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = re.sub(r"\s+", "", raw.strip())
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        result.append(value)
        if len(result) >= limit:
            break
    return result


def normalize_keyword_text(value: str) -> str:
    normalized = value.strip().casefold()
    normalized = re.sub(r"^(?:请问|麻烦|请帮我|帮我|想问一下)", "", normalized)
    normalized = re.sub(r"[\s\-—_，,。.!！?？、:：;；'\"“”‘’（）()]+", "", normalized)
    return normalized[:500]


def _recommended_count(
    keyword_types: Sequence[str],
    secondary_keywords: Sequence[str],
) -> int:
    return min(40, max(5, len(keyword_types) * 4 + len(secondary_keywords) * 2))


def _normalize_keyword_priority(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value in {1, 2, 3}:
        return value
    if not isinstance(value, str):
        return 2
    aliases = {
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
    return aliases.get(value.strip().casefold(), 2)


def _knowledge_fingerprint(client: Client, facts: list[Fact]) -> str:
    snapshot = {
        "client": {
            "name": client.standard_name,
            "industry": client.industry_name,
            "city": client.city,
            "district": client.district,
        },
        "facts": [
            {"id": str(fact.id), "key": fact.key, "value": fact.value, "version": fact.version}
            for fact in sorted(facts, key=lambda item: (item.key, str(item.id)))
        ],
    }
    return sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _fact_value(facts: list[Fact], key: str, fallback: str = "") -> str:
    return next((fact.value for fact in facts if fact.key == key and fact.value.strip()), fallback)


def _inferred_profile(client: Client, facts: list[Fact]) -> dict[str, object]:
    service = _fact_value(facts, "service.primary", client.industry_name)
    audience = _fact_value(facts, "audience.primary")
    topics = _service_topics(service, brand=client.standard_name, audience=audience)
    district = _fact_value(facts, "location.service_area", client.district).strip()
    compact_district = compact_search_area(district)
    compact_city = compact_search_area(client.city)
    regions = _dedupe_strings(
        [
            district,
            compact_district,
            f"{compact_city}{compact_district}",
            f"{client.city}{district}",
        ],
        limit=5,
    )
    keyword_types = list(KEYWORD_TYPES)
    secondary = _dedupe_strings(topics[1:], limit=10)
    return {
        "primary_keyword": topics[0],
        "regions": regions or [client.district],
        "secondary_keywords": secondary,
        "keyword_types": keyword_types,
        "recommended_count": _recommended_count(keyword_types, secondary),
        "knowledge_fingerprint": _knowledge_fingerprint(client, facts),
        "version": 0,
        "updated_at": None,
        "inferred": True,
    }


def _profile_data(profile: KeywordProfile) -> dict[str, object]:
    return {
        "primary_keyword": profile.primary_keyword,
        "regions": profile.regions,
        "secondary_keywords": profile.secondary_keywords,
        "keyword_types": profile.keyword_types,
        "recommended_count": profile.recommended_count,
        "knowledge_fingerprint": profile.knowledge_fingerprint,
        "version": profile.version,
        "updated_at": profile.updated_at.isoformat(),
        "inferred": False,
    }


def _candidate_data(candidate: KeywordCandidate) -> dict[str, object]:
    return {
        "id": str(candidate.id),
        "generation_id": str(candidate.generation_id),
        "text": candidate.text,
        "normalized_text": candidate.normalized_text,
        "main_keyword": candidate.main_keyword,
        "keyword_type": candidate.keyword_type,
        "user_intent": candidate.user_intent,
        "region": candidate.region,
        "secondary_keyword": candidate.secondary_keyword,
        "recommended_content_type": candidate.recommended_content_type,
        "priority": candidate.priority,
        "selected": candidate.selected,
        "active": candidate.active,
        "confirmed_item_id": (
            str(candidate.confirmed_item_id) if candidate.confirmed_item_id else None
        ),
        "version": candidate.version,
    }


def _generation_data(
    generation: KeywordGeneration,
    *,
    candidates: list[KeywordCandidate] | None = None,
) -> dict[str, object]:
    data: dict[str, object] = {
        "id": str(generation.id),
        "client_id": str(generation.client_id),
        "job_id": str(generation.job_id) if generation.job_id else None,
        "primary_keyword": generation.primary_keyword,
        "regions": generation.regions,
        "secondary_keywords": generation.secondary_keywords,
        "keyword_types": generation.keyword_types,
        "target_count": generation.target_count,
        "status": generation.status,
        "generated_count": generation.generated_count,
        "filtered_count": generation.filtered_count,
        "confirmed_count": generation.confirmed_count,
        "error_message": generation.error_message,
        "archived": generation.archived,
        "created_at": generation.created_at.isoformat(),
        "completed_at": (generation.completed_at.isoformat() if generation.completed_at else None),
        "confirmed_at": generation.confirmed_at.isoformat() if generation.confirmed_at else None,
        "version": generation.version,
    }
    if candidates is not None:
        data["candidates"] = [_candidate_data(candidate) for candidate in candidates]
    return data


class KeywordProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=0)
    primary_keyword: str = Field(min_length=2, max_length=300)
    regions: list[str] = Field(min_length=1, max_length=5)
    secondary_keywords: list[str] = Field(default_factory=list, max_length=10)
    keyword_types: list[KeywordType] = Field(min_length=1, max_length=8)

    @field_validator("regions")
    @classmethod
    def validate_regions(cls, value: list[str]) -> list[str]:
        normalized = _dedupe_strings(value, limit=5)
        if len(normalized) != len(value):
            raise ValueError("地区不能重复或为空")
        if any(len(item) > 100 for item in normalized):
            raise ValueError("地区长度不能超过100个字符")
        return normalized

    @field_validator("secondary_keywords")
    @classmethod
    def validate_secondary_keywords(cls, value: list[str]) -> list[str]:
        normalized = _dedupe_strings(value, limit=10)
        if len(normalized) != len(value):
            raise ValueError("二级关键词不能重复或为空")
        if any(len(item) > 300 for item in normalized):
            raise ValueError("二级关键词长度不能超过300个字符")
        return normalized

    @field_validator("keyword_types")
    @classmethod
    def validate_keyword_types(cls, value: list[KeywordType]) -> list[KeywordType]:
        if len(set(value)) != len(value):
            raise ValueError("关键词类型不能重复")
        return value


class KeywordGenerationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_version: int = Field(ge=0)
    target_count: int = Field(ge=5, le=50)


class KeywordCandidateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    selected: bool
    active: bool


class KeywordConfirmInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    candidate_ids: list[UUID] = Field(min_length=1, max_length=50)

    @field_validator("candidate_ids")
    @classmethod
    def validate_candidate_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("候选关键词不能重复")
        return value


def _task_templates(
    *,
    brand: str,
    primary: str,
    regions: list[str],
    secondaries: list[str],
    keyword_types: list[str],
) -> list[dict[str, object]]:
    services = _dedupe_strings([primary, *secondaries], limit=11)
    areas = regions or [""]
    templates: dict[str, tuple[str, ...]] = {
        "local_service": (
            "{area}{service}",
            "{area}{service}机构",
            "{area}哪里有{service}",
            "{area}{service}怎么选",
        ),
        "brand": (
            "{brand}怎么样",
            "{brand}好吗",
            "{brand}主要做什么",
            "{brand}适合哪些人",
            "{brand}在哪里",
        ),
        "recommendation": (
            "{area}{service}哪家好",
            "{area}{service}机构推荐",
            "请推荐一家{area}的{service}机构",
            "{area}值得了解的{service}机构",
        ),
        "scenario": (
            "孩子多大适合学{service}",
            "零基础怎么选{service}",
            "住在{area}怎么选{service}",
            "第一次咨询{service}要问什么",
        ),
        "service_detail": (
            "{service}主要学什么",
            "{service}有哪些课程",
            "{service}适合什么基础",
            "学{service}要准备什么",
        ),
        "comparison": (
            "{area}{service}机构怎么比较",
            "选{service}看哪些方面",
            "{service}大班和小班怎么选",
            "线上和线下{service}怎么选",
        ),
        "transaction": (
            "{area}{service}怎么收费",
            "{service}报名前要了解什么",
            "咨询{service}要准备哪些信息",
            "{service}体验课怎么预约",
        ),
        "trust": (
            "{brand}信息怎么核实",
            "选择{area}{service}要核实什么",
            "{service}机构资质怎么看",
            "{brand}服务范围是什么",
        ),
    }
    rows: list[dict[str, object]] = []
    for keyword_type in keyword_types:
        patterns = templates[keyword_type]
        for area in areas:
            for service in services:
                for pattern in patterns:
                    text = pattern.format(
                        area=compact_search_area(area),
                        service=service,
                        brand=brand,
                    )
                    rows.append(
                        {
                            "text": text,
                            "main_keyword": primary,
                            "keyword_type": keyword_type,
                            "user_intent": INTENT_BY_KEYWORD_TYPE[keyword_type],
                            "region": area or None,
                            "secondary_keyword": service if service != primary else None,
                            "recommended_content_type": CONTENT_TYPE_BY_KEYWORD_TYPE[keyword_type],
                            "priority": 1
                            if keyword_type in {"local_service", "recommendation"}
                            else 2,
                        },
                    )
    return rows


async def _live_suggestions(
    database: AsyncSession,
    settings: Settings,
    provider_client: ProviderClient,
    *,
    generation: KeywordGeneration,
    client: Client,
    facts: list[Fact],
    excluded: set[str],
    count: int,
) -> list[dict[str, object]]:
    from app.content import _execute_model_step, _parse_model_json

    prompt_payload = {
        "enterprise": {
            "name": client.standard_name,
            "industry": client.industry_name,
            "facts": [
                {"key": fact.key, "label": fact.label, "value": fact.value} for fact in facts
            ],
        },
        "keyword_profile": {
            "primary_keyword": generation.primary_keyword,
            "regions": generation.regions,
            "secondary_keywords": generation.secondary_keywords,
            "keyword_types": generation.keyword_types,
        },
        "target_count": count,
        "excluded_normalized_keywords": sorted(excluded)[-300:],
    }
    result = await _execute_model_step(
        database,
        settings,
        provider_client,
        client_id=client.id,
        fact_snapshot_id=None,
        purpose="writer",
        step="keyword_workspace",
        system_prompt=(
            "你是本地服务GEO关键词策略师。依据企业事实、主关键词、地区、二级关键词和"
            "关键词类型，生成普通消费者会直接在AI平台输入的中文问题。输出JSON对象items，"
            "每项包含long_tail_keyword、main_keyword、keyword_type、user_intent、priority、"
            "recommended_content_type。只使用请求中的keyword_type；问题通常8到28个汉字，"
            "priority只能填写数字1、2或3（1最高、3最低）。"
            "禁止搬运整段企业资料、堆砌项目、虚构热度、排名、效果、价格、资质或口碑。"
            "同一批次避免只替换‘哪家好/推荐/怎么样’的机械变体，且不要生成排除列表中的问题。"
        ),
        user_prompt=json.dumps(prompt_payload, ensure_ascii=False),
        schema=KeywordSuggestionOutput,
    )
    parsed = cast(
        KeywordSuggestionOutput, _parse_model_json(result.content, KeywordSuggestionOutput)
    )
    rows: list[dict[str, object]] = []
    for raw in parsed.items:
        text = str(raw.get("long_tail_keyword") or raw.get("text") or "").strip()
        keyword_type = str(raw.get("keyword_type") or "")
        if not text or keyword_type not in generation.keyword_types:
            continue
        rows.append(
            {
                "text": text,
                "main_keyword": str(raw.get("main_keyword") or generation.primary_keyword),
                "keyword_type": keyword_type,
                "user_intent": str(raw.get("user_intent") or INTENT_BY_KEYWORD_TYPE[keyword_type]),
                "region": next((area for area in generation.regions if area in text), None),
                "secondary_keyword": next(
                    (item for item in generation.secondary_keywords if item in text),
                    None,
                ),
                "recommended_content_type": str(
                    raw.get("recommended_content_type")
                    or CONTENT_TYPE_BY_KEYWORD_TYPE[keyword_type]
                ),
                "priority": _normalize_keyword_priority(raw.get("priority", 2)),
            },
        )
    return rows


async def process_keyword_generation_job(
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
            generation_id = UUID(str(current.payload["generation_id"]))
            generation = await database.scalar(
                select(KeywordGeneration)
                .where(KeywordGeneration.id == generation_id)
                .with_for_update(),
            )
            client = await database.get(Client, current.client_id)
            profile = await database.scalar(
                select(KeywordProfile)
                .where(KeywordProfile.client_id == current.client_id)
                .with_for_update(),
            )
            if generation is None or client is None or profile is None or client.status != "active":
                current.status = "failed"
                current.progress = 100
                current.error_message = "关键词任务或客户资料不存在"
                current.completed_at = now
                current.lease_until = None
                if generation is not None:
                    generation.status = "failed"
                    generation.error_message = current.error_message
                    generation.completed_at = now
                    generation.version += 1
                return True
            generation.status = "running"
            generation.version += 1
            await lock_content_fact_set(database, client.id)
            facts = await list_content_eligible_facts(database, client.id)
            excluded = set(
                (
                    await database.scalars(
                        select(KeywordCandidate.normalized_text).where(
                            KeywordCandidate.client_id == client.id,
                        ),
                    )
                ).all(),
            )
            existing_strategy_texts = (
                await database.scalars(
                    select(StrategyItem.text).where(
                        StrategyItem.client_id == client.id,
                        StrategyItem.kind == "keyword",
                    ),
                )
            ).all()
            excluded.update(normalize_keyword_text(text) for text in existing_strategy_texts)
            candidates: list[dict[str, object]] = []
            if settings.model_execution_mode == "live":
                try:
                    for _round in range(2):
                        missing = generation.target_count - len(candidates)
                        if missing <= 0:
                            break
                        candidates.extend(
                            await _live_suggestions(
                                database,
                                settings,
                                provider_client or ProviderClient(),
                                generation=generation,
                                client=client,
                                facts=facts,
                                excluded=excluded
                                | {
                                    normalize_keyword_text(str(item["text"])) for item in candidates
                                },
                                count=missing,
                            ),
                        )
                except ApiFailure as failure:
                    generation.status = "failed"
                    generation.error_message = failure.message
                    generation.completed_at = now
                    generation.version += 1
                    current.status = "failed"
                    current.progress = 100
                    current.error_message = failure.message
                    current.completed_at = now
                    current.lease_until = None
                    return True
            fallback = _task_templates(
                brand=client.standard_name,
                primary=generation.primary_keyword,
                regions=generation.regions,
                secondaries=generation.secondary_keywords,
                keyword_types=generation.keyword_types,
            )
            candidates.extend(fallback)
            filtered_count = 0
            accepted: list[dict[str, object]] = []
            seen = set(excluded)
            for candidate in candidates:
                text = re.sub(r"\s+", "", str(candidate["text"]).strip())
                normalized = normalize_keyword_text(text)
                if (
                    not normalized
                    or normalized in seen
                    or len(text) < 2
                    or len(text) > 60
                    or str(candidate["keyword_type"]) not in generation.keyword_types
                ):
                    filtered_count += 1
                    continue
                seen.add(normalized)
                candidate["text"] = text
                candidate["normalized_text"] = normalized
                accepted.append(candidate)
                if len(accepted) >= generation.target_count:
                    break
            for candidate in accepted:
                database.add(
                    KeywordCandidate(
                        generation_id=generation.id,
                        client_id=client.id,
                        text=str(candidate["text"]),
                        normalized_text=str(candidate["normalized_text"]),
                        main_keyword=str(
                            candidate.get("main_keyword") or generation.primary_keyword
                        ),
                        keyword_type=str(candidate["keyword_type"]),
                        user_intent=str(candidate["user_intent"]),
                        region=(str(candidate["region"]) if candidate.get("region") else None),
                        secondary_keyword=(
                            str(candidate["secondary_keyword"])
                            if candidate.get("secondary_keyword")
                            else None
                        ),
                        recommended_content_type=str(candidate["recommended_content_type"]),
                        priority=max(1, min(3, int(str(candidate["priority"])))),
                    ),
                )
            generation.status = "awaiting_confirmation"
            generation.generated_count = len(accepted)
            generation.filtered_count = filtered_count
            generation.completed_at = now
            generation.version += 1
            current.status = "succeeded"
            current.progress = 100
            current.completed_at = now
            current.lease_until = None
        return True


def build_keyword_workspace_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get("/clients/{client_id}/keyword-workspace")
    async def get_keyword_workspace(
        request: Request,
        client_id: UUID,
        database: DatabaseSession,
        authentication: Authenticated,
    ) -> Response:
        client = await database.get(Client, client_id)
        if client is None:
            return error_response(request, status_code=404, code=40401, message="客户不存在")
        facts = await list_content_eligible_facts(database, client.id)
        profile = await database.get(KeywordProfile, client.id)
        generations = list(
            (
                await database.scalars(
                    select(KeywordGeneration)
                    .where(
                        KeywordGeneration.client_id == client.id,
                        KeywordGeneration.archived.is_(False),
                    )
                    .order_by(KeywordGeneration.created_at.desc(), KeywordGeneration.id.desc()),
                )
            ).all(),
        )
        strategy_items = list(
            (
                await database.scalars(
                    select(StrategyItem)
                    .where(
                        StrategyItem.client_id == client.id,
                        StrategyItem.kind == "keyword",
                        StrategyItem.active.is_(True),
                    )
                    .order_by(StrategyItem.priority, StrategyItem.id),
                )
            ).all(),
        )
        return success_response(
            request,
            {
                "profile": _profile_data(profile) if profile else _inferred_profile(client, facts),
                "generations": [_generation_data(item) for item in generations],
                "confirmed_keywords": [
                    {
                        "id": str(item.id),
                        "text": item.text,
                        "keyword_type": item.keyword_type,
                        "main_keyword": item.main_keyword,
                        "selected": item.selected,
                        "active": item.active,
                        "version": item.version,
                    }
                    for item in strategy_items
                ],
            },
        )

    @router.put("/clients/{client_id}/keyword-profile")
    async def save_keyword_profile(
        request: Request,
        client_id: UUID,
        body: KeywordProfileInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        client = await database.scalar(
            select(Client).where(Client.id == client_id).with_for_update()
        )
        if client is None:
            return error_response(request, status_code=404, code=40401, message="客户不存在")
        facts = await list_content_eligible_facts(database, client.id)
        profile = await database.scalar(
            select(KeywordProfile).where(KeywordProfile.client_id == client.id).with_for_update(),
        )
        expected_version = profile.version if profile else 0
        if body.version != expected_version:
            return error_response(
                request,
                status_code=409,
                code=40901,
                message="关键词配置已被更新，请刷新后重试",
            )
        recommended = _recommended_count(body.keyword_types, body.secondary_keywords)
        if profile is None:
            profile = KeywordProfile(
                client_id=client.id,
                primary_keyword=body.primary_keyword.strip(),
                regions=body.regions,
                secondary_keywords=body.secondary_keywords,
                keyword_types=list(body.keyword_types),
                recommended_count=recommended,
                knowledge_fingerprint=_knowledge_fingerprint(client, facts),
            )
            database.add(profile)
        else:
            profile.primary_keyword = body.primary_keyword.strip()
            profile.regions = body.regions
            profile.secondary_keywords = body.secondary_keywords
            profile.keyword_types = list(body.keyword_types)
            profile.recommended_count = recommended
            profile.knowledge_fingerprint = _knowledge_fingerprint(client, facts)
            profile.version += 1
        await database.commit()
        await database.refresh(profile)
        return success_response(request, _profile_data(profile))

    @router.post("/clients/{client_id}/keyword-generations")
    async def create_keyword_generation(
        request: Request,
        client_id: UUID,
        body: KeywordGenerationInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
        idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    ) -> Response:
        client = await database.scalar(
            select(Client).where(Client.id == client_id).with_for_update()
        )
        if client is None:
            return error_response(request, status_code=404, code=40401, message="客户不存在")
        if client.status != "active":
            return error_response(
                request,
                status_code=409,
                code=40901,
                message="客户已暂停或归档，不能生成关键词",
            )
        profile = await database.scalar(
            select(KeywordProfile).where(KeywordProfile.client_id == client.id).with_for_update(),
        )
        if profile is None:
            if body.profile_version != 0:
                return error_response(
                    request,
                    status_code=409,
                    code=40901,
                    message="关键词配置已被更新，请刷新后重试",
                )
            facts = await list_content_eligible_facts(database, client.id)
            inferred = _inferred_profile(client, facts)
            profile = KeywordProfile(
                client_id=client.id,
                primary_keyword=str(inferred["primary_keyword"]),
                regions=cast(list[str], inferred["regions"]),
                secondary_keywords=cast(list[str], inferred["secondary_keywords"]),
                keyword_types=cast(list[str], inferred["keyword_types"]),
                recommended_count=cast(int, inferred["recommended_count"]),
                knowledge_fingerprint=str(inferred["knowledge_fingerprint"]),
            )
            database.add(profile)
            await database.flush()
        elif body.profile_version != profile.version and not (
            body.profile_version == 0 and profile.version == 1
        ):
            return error_response(
                request,
                status_code=409,
                code=40901,
                message="关键词配置已被更新，请刷新后重试",
            )
        key = str(idempotency_key)
        existing_job = await database.scalar(
            select(Job).where(
                Job.client_id == client.id,
                Job.job_type == "strategy_generate",
                Job.idempotency_key == key,
            ),
        )
        if existing_job is not None:
            existing_generation = await database.scalar(
                select(KeywordGeneration).where(KeywordGeneration.job_id == existing_job.id),
            )
            if existing_generation is None or existing_generation.target_count != body.target_count:
                return error_response(
                    request,
                    status_code=409,
                    code=40903,
                    message="幂等键已用于不同的关键词任务",
                )
            return success_response(
                request,
                {
                    "job_id": str(existing_job.id),
                    "generation_id": str(existing_generation.id),
                    "status": existing_job.status,
                    "progress": existing_job.progress,
                },
                status_code=202,
            )
        generation = KeywordGeneration(
            client_id=client.id,
            primary_keyword=profile.primary_keyword,
            regions=profile.regions,
            secondary_keywords=profile.secondary_keywords,
            keyword_types=profile.keyword_types,
            knowledge_fingerprint=profile.knowledge_fingerprint,
            target_count=body.target_count,
        )
        database.add(generation)
        await database.flush()
        job = Job(
            client_id=client.id,
            job_type="strategy_generate",
            idempotency_key=key,
            payload={"mode": "keyword_generation", "generation_id": str(generation.id)},
        )
        database.add(job)
        await database.flush()
        generation.job_id = job.id
        try:
            await database.commit()
        except IntegrityError:
            await database.rollback()
            return error_response(
                request,
                status_code=409,
                code=40903,
                message="关键词任务已提交，请勿重复操作",
            )
        return success_response(
            request,
            {
                "job_id": str(job.id),
                "generation_id": str(generation.id),
                "status": job.status,
                "progress": job.progress,
            },
            status_code=202,
        )

    @router.get("/keyword-generations/{generation_id}")
    async def get_keyword_generation(
        request: Request,
        generation_id: UUID,
        database: DatabaseSession,
        authentication: Authenticated,
    ) -> Response:
        generation = await database.get(KeywordGeneration, generation_id)
        if generation is None:
            return error_response(request, status_code=404, code=40401, message="关键词任务不存在")
        candidates = list(
            (
                await database.scalars(
                    select(KeywordCandidate)
                    .where(KeywordCandidate.generation_id == generation.id)
                    .order_by(
                        KeywordCandidate.priority, KeywordCandidate.created_at, KeywordCandidate.id
                    ),
                )
            ).all(),
        )
        return success_response(request, _generation_data(generation, candidates=candidates))

    @router.patch("/keyword-candidates/{candidate_id}")
    async def update_keyword_candidate(
        request: Request,
        candidate_id: UUID,
        body: KeywordCandidateInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        candidate = await database.scalar(
            select(KeywordCandidate).where(KeywordCandidate.id == candidate_id).with_for_update(),
        )
        if candidate is None:
            return error_response(request, status_code=404, code=40401, message="候选关键词不存在")
        generation = await database.get(KeywordGeneration, candidate.generation_id)
        if generation is None or generation.status != "awaiting_confirmation":
            return error_response(
                request,
                status_code=409,
                code=40901,
                message="当前任务状态不能修改候选关键词",
            )
        if candidate.version != body.version:
            return error_response(
                request,
                status_code=409,
                code=40901,
                message="候选关键词已被更新，请刷新后重试",
            )
        candidate.selected = body.selected and body.active
        candidate.active = body.active
        candidate.version += 1
        await database.commit()
        return success_response(request, _candidate_data(candidate))

    @router.post("/keyword-generations/{generation_id}/confirm")
    async def confirm_keyword_generation(
        request: Request,
        generation_id: UUID,
        body: KeywordConfirmInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        generation = await database.scalar(
            select(KeywordGeneration)
            .where(KeywordGeneration.id == generation_id)
            .with_for_update(),
        )
        if generation is None:
            return error_response(request, status_code=404, code=40401, message="关键词任务不存在")
        if generation.version != body.version:
            return error_response(
                request,
                status_code=409,
                code=40901,
                message="关键词任务已被更新，请刷新后重试",
            )
        if generation.status != "awaiting_confirmation":
            return error_response(
                request,
                status_code=409,
                code=40901,
                message="当前任务状态不能确认",
            )
        candidates = list(
            (
                await database.scalars(
                    select(KeywordCandidate)
                    .where(
                        KeywordCandidate.generation_id == generation.id,
                        KeywordCandidate.id.in_(body.candidate_ids),
                        KeywordCandidate.active.is_(True),
                    )
                    .with_for_update(),
                )
            ).all(),
        )
        if len(candidates) != len(body.candidate_ids):
            return error_response(
                request,
                status_code=422,
                code=42201,
                message="请选择当前任务中有效的候选关键词",
            )
        bundle = await database.scalar(
            select(StrategyBundle)
            .where(StrategyBundle.client_id == generation.client_id)
            .with_for_update(),
        )
        latest_diagnostic_id = await database.scalar(
            select(DiagnosticRun.id)
            .where(
                DiagnosticRun.client_id == generation.client_id,
                DiagnosticRun.status == "succeeded",
            )
            .order_by(DiagnosticRun.created_at.desc())
            .limit(1),
        )
        keyword_prompt = await database.scalar(
            select(PromptTemplate).where(
                PromptTemplate.code == "keyword_strategy",
                PromptTemplate.active.is_(True),
            ),
        )
        now = datetime.now(UTC)
        if bundle is None:
            bundle = StrategyBundle(
                client_id=generation.client_id,
                diagnostic_run_id=latest_diagnostic_id,
                prompt_template_code=keyword_prompt.code if keyword_prompt else None,
                prompt_template_version=keyword_prompt.current_version if keyword_prompt else None,
                generated_at=now,
            )
            database.add(bundle)
            await database.flush()
        else:
            bundle.generated_at = now
            bundle.version += 1
        chosen = set(body.candidate_ids)
        all_candidates = list(
            (
                await database.scalars(
                    select(KeywordCandidate)
                    .where(KeywordCandidate.generation_id == generation.id)
                    .with_for_update(),
                )
            ).all(),
        )
        for candidate in all_candidates:
            candidate.selected = candidate.id in chosen
            candidate.version += 1
        for candidate in candidates:
            item = StrategyItem(
                bundle_id=bundle.id,
                client_id=generation.client_id,
                kind="keyword",
                text=candidate.text,
                family=None,
                keyword_type=candidate.keyword_type,
                provenance="ai_generated",
                target_level=(
                    "L3"
                    if candidate.keyword_type == "recommendation"
                    else "L2"
                    if candidate.keyword_type == "brand"
                    else "L1"
                ),
                priority=candidate.priority,
                rationale=(
                    f"由知识库、主关键词“{generation.primary_keyword}”、地区和用户意图生成，"
                    "并经运营人员确认进入正式关键词库。"
                ),
                main_keyword=candidate.main_keyword,
                user_intent=candidate.user_intent,
                recommended_content_type=candidate.recommended_content_type,
                locked=True,
                selected=True,
                active=True,
            )
            database.add(item)
            await database.flush()
            candidate.confirmed_item_id = item.id
        generation.status = "confirmed"
        generation.confirmed_count = len(candidates)
        generation.confirmed_at = now
        generation.version += 1
        await database.commit()
        return success_response(request, _generation_data(generation))

    @router.delete("/keyword-generations/{generation_id}")
    async def archive_keyword_generation(
        request: Request,
        generation_id: UUID,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
        version: Annotated[int, Query(ge=1)],
    ) -> Response:
        generation = await database.scalar(
            select(KeywordGeneration)
            .where(KeywordGeneration.id == generation_id)
            .with_for_update(),
        )
        if generation is None:
            return error_response(request, status_code=404, code=40401, message="关键词任务不存在")
        if generation.version != version:
            return error_response(
                request,
                status_code=409,
                code=40901,
                message="关键词任务已被更新，请刷新后重试",
            )
        generation.archived = True
        generation.version += 1
        await database.commit()
        return success_response(request, _generation_data(generation))

    return router
