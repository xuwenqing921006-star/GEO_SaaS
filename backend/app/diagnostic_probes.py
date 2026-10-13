# ruff: noqa: RUF001

import asyncio
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from typing import TypedDict, cast
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import Client, Fact, ProviderSetting
from app.providers import (
    PROVIDER_OFFICIAL_HOSTS,
    ProviderClient,
    ProviderName,
    ProviderSearchSource,
    SecretCipher,
    finalize_model_usage,
    reserve_model_budget,
)
from app.responses import ApiFailure

AUTO_DIAGNOSTIC_PROMPT_VERSION = "geo-auto-diagnostic-v1"
AUTO_DIAGNOSTIC_PRICING_VERSION = "budget-ceiling-v1-2026-07-29"
AUTO_DIAGNOSTIC_BUDGET_RATES: dict[ProviderName, tuple[int, int]] = {
    "deepseek": (400, 1600),
    "doubao": (400, 1600),
    "wenxin": (400, 1600),
    "yuanbao": (400, 1600),
    "qwen": (200, 800),
    "kimi": (400, 1600),
}
RECOMMENDATION_CUES = (
    "推荐",
    "可以考虑",
    "可考虑",
    "可了解",
    "建议选择",
    "值得了解",
    "备选",
)
NEGATIVE_RECOMMENDATION_CUES = (
    "无法推荐",
    "不能推荐",
    "不做推荐",
    "没有足够信息推荐",
    "无法确认是否推荐",
)
SOURCE_URL_PATTERN = re.compile(r"https?://[^\s,，。；;）)>\]]+")


class DiagnosticPlatformEntry(TypedDict):
    id: str
    name: str
    provider: ProviderName
    note: str


AUTO_DIAGNOSTIC_PLATFORMS: tuple[DiagnosticPlatformEntry, ...] = (
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "provider": "deepseek",
        "note": "官方 API 自动检测；当前接口不提供原生网页来源字段。",
    },
    {
        "id": "qwen",
        "name": "通义千问",
        "provider": "qwen",
        "note": "通过阿里云百炼官方 API 联网检测并保留搜索来源。",
    },
    {
        "id": "doubao",
        "name": "豆包",
        "provider": "doubao",
        "note": "通过火山方舟 Responses API 联网检测并保留可见引用。",
    },
    {
        "id": "wenxin",
        "name": "文心一言",
        "provider": "wenxin",
        "note": "通过百度千帆 ERNIE 官方 API 联网检测并保留搜索来源。",
    },
)


def current_platform_results(
    platform_results: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Keep historical diagnostics readable after the platform catalog expands."""

    existing = {
        str(result.get("platform_id")): result
        for result in platform_results
        if isinstance(result, dict) and result.get("platform_id")
    }
    questions = next(
        (
            cast(list[dict[str, object]], result["questions"])
            for result in platform_results
            if isinstance(result.get("questions"), list)
        ),
        [],
    )
    normalized: list[dict[str, object]] = []
    for platform in AUTO_DIAGNOSTIC_PLATFORMS:
        previous = existing.get(platform["id"])
        if previous is not None:
            normalized.append(
                {
                    **previous,
                    "platform_note": previous.get("platform_note", platform["note"]),
                    "source_capability": previous.get(
                        "source_capability",
                        ("not_supported" if platform["id"] == "deepseek" else "no_sources"),
                    ),
                    "source_count": previous.get("source_count", 0),
                    "sources": previous.get("sources", []),
                    "competitors": previous.get("competitors", []),
                    "channel_signals": previous.get("channel_signals", []),
                },
            )
            continue
        normalized.append(
            {
                "platform_id": platform["id"],
                "platform_name": platform["name"],
                "collection_mode": "api",
                "status": "unconfigured",
                "score": None,
                "grade": None,
                "comment": "该平台尚未参与这次历史诊断，配置后重新诊断即可取得结果。",
                "valid_sample_count": 0,
                "measured_at": None,
                "metrics": {
                    "mention_rate": None,
                    "association_rate": None,
                    "recommendation_rate": None,
                    "accuracy_rate": None,
                    "source_rate": None,
                },
                "questions": questions,
                "platform_note": platform["note"],
                "source_capability": (
                    "not_supported" if platform["id"] == "deepseek" else "no_sources"
                ),
                "source_count": 0,
                "sources": [],
                "competitors": [],
                "channel_signals": [],
            },
        )
    return normalized


CHANNEL_HOST_RULES: tuple[tuple[str, str, str], ...] = (
    ("baijiahao.baidu.com", "baijia", "百家号"),
    ("zhidao.baidu.com", "baidu", "百度内容生态"),
    ("baike.baidu.com", "baidu", "百度内容生态"),
    ("sohu.com", "sohu", "搜狐号 / 搜狐"),
    ("toutiao.com", "toutiao", "头条号 / 今日头条"),
    ("163.com", "netease", "网易号 / 网易"),
    ("new.qq.com", "penguin", "企鹅号 / 腾讯新闻"),
    ("page.om.qq.com", "penguin", "企鹅号 / 腾讯内容开放平台"),
    ("zhihu.com", "zhihu", "知乎"),
    ("mp.weixin.qq.com", "wechat", "微信公众号"),
    ("bilibili.com", "bilibili", "哔哩哔哩"),
    ("xiaohongshu.com", "xiaohongshu", "小红书"),
    ("douyin.com", "douyin", "抖音"),
    ("dianping.com", "local_review", "大众点评"),
    ("meituan.com", "local_review", "美团"),
    ("amap.com", "map", "地图平台"),
    ("map.baidu.com", "map", "地图平台"),
)

GENERIC_COMPETITOR_CUES = (
    "哪家",
    "推荐",
    "怎么选",
    "选择",
    "家长",
    "孩子",
    "课程",
    "建议",
    "注意",
    "以下",
    "可以",
    "适合",
    "培训机构",
    "教育机构",
    "本地机构",
    "正规机构",
)
ORGANIZATION_CUES = (
    "美术",
    "教育",
    "艺术",
    "书法",
    "学校",
    "中心",
    "工作室",
    "公司",
    "品牌",
    "门店",
    "家政",
    "维修",
    "摄影",
    "口腔",
    "医院",
    "诊所",
    "餐厅",
    "酒店",
    "健身",
    "瑜伽",
    "装饰",
    "装修",
)
COMPETITOR_CONTENT_SIGNALS: tuple[
    tuple[str, str, tuple[str, ...], str],
    ...,
] = (
    (
        "local_relevance",
        "地区与需求匹配清晰",
        ("本地", "附近", "区域", "地址", "到店", "同城", "校区", "门店"),
        "补充“地区＋主营服务＋适用对象”的独立内容，并保证企业名称和服务范围一致。",
    ),
    (
        "service_detail",
        "服务信息具体、容易摘取",
        ("课程", "服务", "项目", "班型", "年龄", "适合", "流程", "内容"),
        "补齐服务项目、适用人群、服务流程和限制条件，避免只写品牌宣传语。",
    ),
    (
        "trust_evidence",
        "存在可核验的信任信息",
        ("师资", "资质", "证书", "年限", "案例", "口碑", "评价", "获奖", "认证"),
        "发布可核验的资质、团队、服务年限或案例事实；没有依据的优势不要补写。",
    ),
    (
        "decision_information",
        "覆盖了用户决策信息",
        ("价格", "收费", "试听", "预约", "对比", "怎么选", "推荐", "注意事项"),
        "围绕价格范围、选择标准、预约流程和常见顾虑制作决策型问答内容。",
    ),
)


class AutoProbeQuestion(TypedDict):
    id: str
    family: str
    label: str
    text: str


@dataclass(frozen=True)
class PreparedPlatform:
    platform_id: str
    platform_name: str
    provider: ProviderName
    note: str
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int
    workspace_id: str | None
    usage_id: UUID


@dataclass(frozen=True)
class PlatformCall:
    question: AutoProbeQuestion
    answer: str | None
    error: str | None
    input_tokens: int
    output_tokens: int
    latency_ms: int
    sources: tuple[ProviderSearchSource, ...]
    source_capability: str


def build_auto_probe_questions(
    *,
    brand: str,
    district: str,
    service: str,
    audience: str,
) -> list[AutoProbeQuestion]:
    search_area = compact_search_area(district)
    search_service = compact_search_service(service, audience)
    district_service = f"{search_area}{search_service}".strip()
    return [
        {
            "id": "category-discovery",
            "family": "category_discovery",
            "label": "地区与主营发现",
            "text": district_service,
        },
        {
            "id": "recommendation",
            "family": "recommendation",
            "label": "推荐决策",
            "text": f"{district_service}哪家好",
        },
        {
            "id": "brand-verification",
            "family": "brand_verification",
            "label": "品牌核验",
            "text": f"{brand.strip()}怎么样",
        },
    ]


def compact_search_area(district: str) -> str:
    value = district.strip()
    if value.endswith(("市", "县")) and len(value) >= 3:
        return value[:-1]
    if value.endswith("区") and len(value) >= 3 and not value.endswith(("新区", "开发区")):
        return value[:-1]
    return value


def compact_search_service(service: str, audience: str) -> str:
    value = re.sub(r"^(主营业务|主营服务|核心服务|服务项目)\s*[:：]?\s*", "", service)
    combined = f"{value} {audience}".casefold()
    child_audience = any(
        cue in combined for cue in ("少儿", "儿童", "孩子", "青少年", "幼儿", "学生")
    )
    if "美术" in value:
        return "少儿美术" if child_audience else "美术培训"
    if "硬笔书法" in value:
        return "少儿硬笔书法" if child_audience else "硬笔书法培训"
    if "书法" in value:
        return "少儿书法" if child_audience else "书法培训"
    first_service = re.split(r"[:：,，、;；。\n（(]", value, maxsplit=1)[0].strip()
    first_service = re.sub(r"\s+", "", first_service)
    if first_service:
        return first_service[:16]
    return "本地服务"


def _percentage(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return max(0, min(100, round(numerator * 100 / denominator)))


def visibility_grade(score: int | None) -> str | None:
    if score is None:
        return None
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 50:
        return "medium"
    return "poor"


def calculate_platform_visibility(
    *,
    platform_id: str,
    platform_name: str,
    collection_mode: str,
    evaluations: list[dict[str, object]],
    measured_at: str | None,
    questions: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Apply the fixed five-factor score only to successful automatic answers."""

    if not evaluations:
        return {
            "platform_id": platform_id,
            "platform_name": platform_name,
            "collection_mode": collection_mode,
            "status": "untested",
            "score": None,
            "grade": None,
            "comment": "尚未取得有效自动检测回答。",
            "valid_sample_count": 0,
            "measured_at": measured_at,
            "metrics": {
                "mention_rate": None,
                "association_rate": None,
                "recommendation_rate": None,
                "accuracy_rate": None,
                "source_rate": None,
            },
            "questions": questions or [],
        }

    discovery = [
        item for item in evaluations if item.get("question_family") != "brand_verification"
    ]
    recommendations = [
        item for item in evaluations if item.get("question_family") == "recommendation"
    ]
    mentioned = [item for item in discovery if item.get("brand_found") is True]
    mention_rate = _percentage(
        sum(item.get("brand_found") is True for item in discovery),
        len(discovery),
    )
    association_rate = _percentage(
        sum(item.get("correctly_associated") is True for item in discovery),
        len(discovery),
    )
    recommendation_rate = _percentage(
        sum(item.get("recommended") is True for item in recommendations),
        len(recommendations),
    )
    accuracy_rate = _percentage(
        sum(
            isinstance(item.get("matched_fact_count"), int)
            and cast(int, item["matched_fact_count"]) > 0
            for item in mentioned
        ),
        len(mentioned),
    )
    source_evaluable = [item for item in mentioned if item.get("source_evaluable") is not False]
    source_rate = (
        _percentage(
            sum(item.get("source_visible") is True for item in source_evaluable),
            len(source_evaluable),
        )
        if source_evaluable
        else None
    )
    weighted_score = (
        mention_rate * 0.30
        + association_rate * 0.25
        + recommendation_rate * 0.25
        + accuracy_rate * 0.15
    )
    score = round(
        weighted_score + source_rate * 0.05 if source_rate is not None else weighted_score / 0.95,
    )
    recommended = any(item.get("recommended") is True for item in recommendations)
    associated = any(item.get("correctly_associated") is True for item in discovery)
    found = any(item.get("brand_found") is True for item in discovery)
    brand_query_found = any(
        item.get("question_family") == "brand_verification" and item.get("brand_found") is True
        for item in evaluations
    )
    status = (
        "recommended"
        if recommended
        else "associated"
        if associated
        else "mentioned"
        if found
        else "brand_only"
        if brand_query_found
        else "not_found"
    )
    metric_scores: dict[str, int] = {
        "品牌出现": mention_rate,
        "地区与主营关联": association_rate,
        "推荐命中": recommendation_rate,
        "可核验企业事实": accuracy_rate,
    }
    if source_rate is not None:
        metric_scores["可见来源"] = source_rate
    weak_metric = min(metric_scores, key=metric_scores.__getitem__)
    comment = (
        "品牌只在直接询问品牌时出现，尚未进入品类发现或推荐回答。"
        if status == "brand_only"
        else "品牌已进入品类回答，关联和推荐表现较完整。"
        if score >= 85
        else f"品牌已有一定可见性，下一步优先补强{weak_metric}。"
        if score >= 50
        else f"当前自动检测可见性较弱，建议优先改善{weak_metric}。"
    )
    return {
        "platform_id": platform_id,
        "platform_name": platform_name,
        "collection_mode": collection_mode,
        "status": status,
        "score": score,
        "grade": visibility_grade(score),
        "comment": comment,
        "valid_sample_count": len(evaluations),
        "measured_at": measured_at,
        "metrics": {
            "mention_rate": mention_rate,
            "association_rate": association_rate,
            "recommendation_rate": recommendation_rate,
            "accuracy_rate": accuracy_rate,
            "source_rate": source_rate,
        },
        "questions": questions or [],
    }


def _platform_placeholder(
    *,
    platform_id: str,
    platform_name: str,
    note: str,
    questions: list[AutoProbeQuestion],
    status: str,
    comment: str,
) -> dict[str, object]:
    return {
        "platform_id": platform_id,
        "platform_name": platform_name,
        "collection_mode": "api",
        "status": status,
        "score": None,
        "grade": None,
        "comment": comment,
        "valid_sample_count": 0,
        "measured_at": None,
        "metrics": {
            "mention_rate": None,
            "association_rate": None,
            "recommendation_rate": None,
            "accuracy_rate": None,
            "source_rate": None,
        },
        "questions": [
            {
                "id": question["id"],
                "family": question["family"],
                "label": question["label"],
                "text": question["text"],
                "answer_excerpt": None,
                "status": "not_run",
            }
            for question in questions
        ],
        "platform_note": note,
        "source_capability": ("not_supported" if platform_id == "deepseek" else "no_sources"),
        "source_count": 0,
        "sources": [],
        "competitors": [],
        "channel_signals": [],
    }


def _budget_cost(
    provider: ProviderName,
    input_tokens: int,
    output_tokens: int,
) -> int:
    input_rate, output_rate = AUTO_DIAGNOSTIC_BUDGET_RATES[provider]
    weighted = input_tokens * input_rate + output_tokens * output_rate
    return max(1, math.ceil(weighted / 1_000_000))


def _model_for(provider: ProviderName, setting: ProviderSetting) -> str | None:
    if provider == "deepseek":
        return setting.reviewer_model or setting.writer_model or setting.fallback_model
    return setting.writer_model or setting.reviewer_model or setting.fallback_model


def _brand_aliases(client: Client) -> list[str]:
    return list(
        dict.fromkeys(
            value.casefold()
            for value in (client.standard_name, client.short_name)
            if value and len(value.strip()) >= 2
        )
    )


def _known_fact_terms(facts: list[Fact]) -> list[str]:
    excluded_keys = {
        "identity.standard_name",
        "identity.brand_name",
        "location.administrative_area",
        "location.service_area",
        "service.primary",
    }
    terms: list[str] = []
    for fact in facts:
        if fact.key in excluded_keys:
            continue
        for part in re.split(r"[，,。；;、\n：:（）()]+", fact.value):
            normalized = part.strip().casefold()
            if 4 <= len(normalized) <= 80:
                terms.append(normalized)
    return list(dict.fromkeys(terms))[:40]


def _channel_for_source(url: str, site_name: str | None) -> tuple[str, str, str]:
    host = (urlsplit(url).hostname or "").casefold()
    for domain, channel_id, channel_name in CHANNEL_HOST_RULES:
        if host == domain or host.endswith(f".{domain}"):
            return channel_id, channel_name, host
    label = site_name.strip() if site_name and site_name.strip() else host or "其他公开网页"
    return "other_web", label, host


def _source_rows(calls: list[PlatformCall]) -> list[dict[str, object]]:
    rows_by_url: dict[str, dict[str, object]] = {}
    for call in calls:
        for source in call.sources:
            channel_id, channel_name, domain = _channel_for_source(
                source.url,
                source.site_name,
            )
            row = rows_by_url.setdefault(
                source.url,
                {
                    "index": source.index,
                    "title": source.title,
                    "url": source.url,
                    "site_name": source.site_name,
                    "snippet": source.snippet,
                    "domain": domain,
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                    "question_ids": [],
                    "question_labels": [],
                },
            )
            question_ids = cast(list[str], row["question_ids"])
            question_labels = cast(list[str], row["question_labels"])
            if call.question["id"] not in question_ids:
                question_ids.append(call.question["id"])
                question_labels.append(call.question["label"])
    return list(rows_by_url.values())


def _clean_candidate(value: str) -> str:
    return re.sub(r"^[\s#>*\-\d.、（）()]+|[：:，,。；;！!？?\s]+$", "", value).strip()


def _competitor_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    candidates.extend(re.findall(r"\*\*([^*\n]{2,28})\*\*", text))
    candidates.extend(
        re.findall(
            r"(?:^|\n)\s*(?:\d{1,2}[.、)]|[-*])\s*([^：:\n]{2,28})(?=\s*[：:]|\n|$)",
            text,
        ),
    )
    normalized: list[str] = []
    for candidate in candidates:
        value = _clean_candidate(candidate)
        if not 2 <= len(value) <= 24:
            continue
        if any(cue in value for cue in GENERIC_COMPETITOR_CUES):
            continue
        if not any(cue in value for cue in ORGANIZATION_CUES):
            continue
        if value not in normalized:
            normalized.append(value)
    return normalized


def _answer_excerpt(text: str, candidate: str) -> str | None:
    for sentence in re.split(r"(?<=[。！？!?；;])|\n+", text):
        cleaned = re.sub(r"\s+", " ", sentence).strip(" -*#>\t")
        if candidate.casefold() in cleaned.casefold():
            return cleaned[:280]
    return None


def _competitor_rows(
    calls: list[PlatformCall],
    *,
    brand_aliases: list[str],
) -> list[dict[str, object]]:
    rows: dict[str, dict[str, object]] = {}
    for call in calls:
        if not call.answer:
            continue
        normalized_answer = call.answer.casefold()
        brand_positions = [
            normalized_answer.find(alias)
            for alias in brand_aliases
            if normalized_answer.find(alias) >= 0
        ]
        brand_position = min(brand_positions) if brand_positions else None
        candidates = _competitor_candidates(call.answer)
        for source in call.sources:
            candidates.extend(_competitor_candidates(source.title))
            if source.snippet:
                candidates.extend(_competitor_candidates(source.snippet))
        for candidate in dict.fromkeys(candidates):
            normalized = candidate.casefold()
            if any(alias in normalized or normalized in alias for alias in brand_aliases):
                continue
            position = normalized_answer.find(normalized)
            row = rows.setdefault(
                normalized,
                {
                    "name": candidate,
                    "mention_count": 0,
                    "recommendation_count": 0,
                    "appeared_before_client_count": 0,
                    "question_ids": [],
                    "source_urls": [],
                    "answer_excerpts": [],
                    "source_evidence": [],
                },
            )
            if position >= 0:
                row["mention_count"] = cast(int, row["mention_count"]) + 1
                question_ids = cast(list[str], row["question_ids"])
                if call.question["id"] not in question_ids:
                    question_ids.append(call.question["id"])
                if call.question["family"] == "recommendation":
                    row["recommendation_count"] = cast(int, row["recommendation_count"]) + 1
                if brand_position is not None and position < brand_position:
                    row["appeared_before_client_count"] = (
                        cast(int, row["appeared_before_client_count"]) + 1
                    )
                excerpt = _answer_excerpt(call.answer, candidate)
                answer_excerpts = cast(list[str], row["answer_excerpts"])
                if excerpt and excerpt not in answer_excerpts and len(answer_excerpts) < 4:
                    answer_excerpts.append(excerpt)
            for source in call.sources:
                source_text = f"{source.title} {source.snippet or ''}".casefold()
                if normalized in source_text:
                    source_urls = cast(list[str], row["source_urls"])
                    if source.url not in source_urls:
                        source_urls.append(source.url)
                    source_evidence = cast(
                        list[dict[str, object]],
                        row["source_evidence"],
                    )
                    if all(item.get("url") != source.url for item in source_evidence):
                        source_evidence.append(
                            {
                                "title": source.title,
                                "url": source.url,
                                "site_name": source.site_name,
                                "snippet": source.snippet,
                            },
                        )
    result: list[dict[str, object]] = []
    for row in rows.values():
        mention_count = cast(int, row["mention_count"])
        source_urls = cast(list[str], row["source_urls"])
        if mention_count == 0 and not source_urls:
            continue
        reasons: list[str] = []
        if mention_count:
            reasons.append(f"在 {mention_count} 个回答中被提及")
        if cast(int, row["recommendation_count"]):
            reasons.append("进入了推荐决策回答")
        if cast(int, row["appeared_before_client_count"]):
            reasons.append("在同一回答中出现在客户品牌之前")
        if source_urls:
            reasons.append(f"有 {len(source_urls)} 条检索来源标题直接提及")
        result.append({**row, "reasons": reasons})
    return sorted(
        result,
        key=lambda row: (
            cast(int, row["mention_count"]),
            len(cast(list[str], row["source_urls"])),
        ),
        reverse=True,
    )[:10]


def _channel_signal_rows(
    sources: list[dict[str, object]],
    competitors: list[dict[str, object]],
    *,
    total_question_count: int,
) -> list[dict[str, object]]:
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for source in sources:
        groups[str(source["channel_id"])].append(source)
    max_count = max((len(rows) for rows in groups.values()), default=1)
    competitor_names = [str(row["name"]).casefold() for row in competitors]
    result: list[dict[str, object]] = []
    for channel_id, rows in groups.items():
        question_ids = {
            question_id for row in rows for question_id in cast(list[str], row["question_ids"])
        }
        competitor_hits = sum(
            any(name in str(row["title"]).casefold() for name in competitor_names) for row in rows
        )
        score = round(
            len(rows) / max_count * 45
            + len(question_ids) / max(1, total_question_count) * 35
            + competitor_hits / max(1, len(rows)) * 20,
        )
        confidence = (
            "high"
            if len(rows) >= 4 and len(question_ids) >= 2
            else "medium"
            if len(rows) >= 2
            else "low"
        )
        result.append(
            {
                "channel_id": channel_id,
                "channel_name": rows[0]["channel_name"],
                "signal_score": min(100, score),
                "confidence": confidence,
                "source_count": len(rows),
                "question_count": len(question_ids),
                "competitor_reference_count": competitor_hits,
                "evidence": [{"title": row["title"], "url": row["url"]} for row in rows[:6]],
            },
        )
    return sorted(
        result,
        key=lambda row: (cast(int, row["signal_score"]), cast(int, row["source_count"])),
        reverse=True,
    )


def _competitor_strength_analysis(
    row: dict[str, object],
) -> tuple[list[dict[str, str]], list[str]]:
    signals: list[dict[str, str]] = []
    actions: list[str] = []

    def add_signal(code: str, label: str, evidence: str, action: str) -> None:
        if any(item["code"] == code for item in signals):
            return
        signals.append({"code": code, "label": label, "evidence": evidence})
        if action not in actions:
            actions.append(action)

    platform_count = cast(int, row["platform_count"])
    recommendation_count = cast(int, row["recommendation_count"])
    appeared_before_count = cast(int, row["appeared_before_client_count"])
    source_count = cast(int, row["source_count"])
    if platform_count >= 2:
        add_signal(
            "cross_platform_presence",
            "多个 AI 平台重复识别",
            f"本次在 {platform_count} 个平台出现。",
            "统一企业名称、地区、主营和核心事实，并在多个独立公开来源保持一致。",
        )
    if recommendation_count:
        add_signal(
            "recommendation_match",
            "进入推荐决策回答",
            f"在 {recommendation_count} 个推荐问题回答中出现。",
            "围绕同一推荐问题补充选择标准、适用场景和可核验差异，不要直接仿写竞品。",
        )
    if appeared_before_count:
        add_signal(
            "position_lead",
            "在回答中的位置领先",
            f"有 {appeared_before_count} 次出现在客户品牌之前。",
            "在内容首段形成“企业名称＋地区＋主营＋适用对象”的完整实体句，便于答案摘取。",
        )
    if source_count >= 2:
        add_signal(
            "multiple_sources",
            "有多个公开来源交叉支持",
            f"发现 {source_count} 条直接相关来源。",
            "将同一组可核验事实分布到 2—3 个独立公开渠道，并定期检查信息一致性。",
        )

    evidence_texts = [
        str(excerpt)
        for excerpt in cast(list[object], row.get("answer_excerpts", []))
        if isinstance(excerpt, str)
    ]
    for source in cast(list[object], row.get("source_evidence", [])):
        if not isinstance(source, dict):
            continue
        evidence_texts.extend(
            str(value)
            for value in (source.get("title"), source.get("snippet"))
            if isinstance(value, str) and value.strip()
        )
    evidence_text = " ".join(evidence_texts)
    for code, label, cues, action in COMPETITOR_CONTENT_SIGNALS:
        matched = [cue for cue in cues if cue in evidence_text]
        if matched:
            add_signal(
                code,
                label,
                f"回答或参考资料出现：{'、'.join(matched[:4])}。",
                action,
            )
    return signals[:6], actions[:5]


def build_competitive_insights(
    platform_results: list[dict[str, object]],
) -> dict[str, object]:
    """Aggregate observable evidence without claiming access to ranking algorithms."""

    source_capable_platforms = {
        str(platform["platform_id"])
        for platform in platform_results
        if platform.get("status") not in {"unconfigured", "failed"}
        and platform.get("source_capability") in {"available", "no_sources"}
    }
    competitor_groups: dict[str, dict[str, object]] = {}
    channel_groups: dict[str, dict[str, object]] = {}
    source_urls: set[str] = set()
    for platform in platform_results:
        platform_id = str(platform.get("platform_id", ""))
        platform_name = str(platform.get("platform_name", platform_id))
        competitors = platform.get("competitors", [])
        if isinstance(competitors, list):
            for competitor in competitors:
                if not isinstance(competitor, dict) or not competitor.get("name"):
                    continue
                normalized = str(competitor["name"]).casefold()
                row = competitor_groups.setdefault(
                    normalized,
                    {
                        "name": competitor["name"],
                        "platform_ids": set(),
                        "platform_names": set(),
                        "mention_count": 0,
                        "recommendation_count": 0,
                        "appeared_before_client_count": 0,
                        "source_urls": set(),
                        "reasons": set(),
                        "answer_excerpts": [],
                        "source_evidence": {},
                    },
                )
                cast(set[str], row["platform_ids"]).add(platform_id)
                cast(set[str], row["platform_names"]).add(platform_name)
                for key in (
                    "mention_count",
                    "recommendation_count",
                    "appeared_before_client_count",
                ):
                    value = competitor.get(key, 0)
                    row[key] = cast(int, row[key]) + (value if isinstance(value, int) else 0)
                for url in competitor.get("source_urls", []):
                    if isinstance(url, str):
                        cast(set[str], row["source_urls"]).add(url)
                for reason in competitor.get("reasons", []):
                    if isinstance(reason, str):
                        cast(set[str], row["reasons"]).add(reason)
                excerpts = cast(list[str], row["answer_excerpts"])
                for excerpt in competitor.get("answer_excerpts", []):
                    if isinstance(excerpt, str) and excerpt not in excerpts and len(excerpts) < 8:
                        excerpts.append(excerpt)
                source_evidence = cast(
                    dict[str, dict[str, object]],
                    row["source_evidence"],
                )
                for evidence in competitor.get("source_evidence", []):
                    if not isinstance(evidence, dict) or not isinstance(
                        evidence.get("url"),
                        str,
                    ):
                        continue
                    source_evidence.setdefault(cast(str, evidence["url"]), evidence)
        sources = platform.get("sources", [])
        if not isinstance(sources, list):
            continue
        for source in sources:
            if not isinstance(source, dict) or not isinstance(source.get("url"), str):
                continue
            url = cast(str, source["url"])
            source_urls.add(url)
            channel_id = str(source.get("channel_id", "other_web"))
            channel = channel_groups.setdefault(
                channel_id,
                {
                    "channel_id": channel_id,
                    "channel_name": source.get("channel_name", "其他公开网页"),
                    "platform_ids": set(),
                    "platform_names": set(),
                    "question_pairs": set(),
                    "urls": set(),
                    "competitor_reference_count": 0,
                    "evidence": [],
                },
            )
            cast(set[str], channel["platform_ids"]).add(platform_id)
            cast(set[str], channel["platform_names"]).add(platform_name)
            cast(set[str], channel["urls"]).add(url)
            for question_id in source.get("question_ids", []):
                if isinstance(question_id, str):
                    cast(set[str], channel["question_pairs"]).add(
                        f"{platform_id}:{question_id}",
                    )
            title = str(source.get("title", ""))
            if any(name in title.casefold() for name in competitor_groups):
                channel["competitor_reference_count"] = (
                    cast(int, channel["competitor_reference_count"]) + 1
                )
            evidence = cast(list[dict[str, object]], channel["evidence"])
            if len(evidence) < 8 and all(item.get("url") != url for item in evidence):
                evidence.append(
                    {"title": title or url, "url": url, "platform_name": platform_name},
                )

    competitor_rows: list[dict[str, object]] = []
    for row in competitor_groups.values():
        competitor_row: dict[str, object] = {
            "name": row["name"],
            "platform_count": len(cast(set[str], row["platform_ids"])),
            "platform_names": sorted(cast(set[str], row["platform_names"])),
            "mention_count": row["mention_count"],
            "recommendation_count": row["recommendation_count"],
            "appeared_before_client_count": row["appeared_before_client_count"],
            "source_count": len(cast(set[str], row["source_urls"])),
            "source_urls": sorted(cast(set[str], row["source_urls"])),
            "reasons": sorted(cast(set[str], row["reasons"])),
            "answer_excerpts": cast(list[str], row["answer_excerpts"]),
            "source_evidence": list(
                cast(dict[str, dict[str, object]], row["source_evidence"]).values(),
            ),
        }
        strength_signals, recommended_actions = _competitor_strength_analysis(
            competitor_row,
        )
        competitor_row["strength_signals"] = strength_signals
        competitor_row["recommended_actions"] = recommended_actions
        competitor_rows.append(competitor_row)
    competitor_rows.sort(
        key=lambda row: (
            cast(int, row["platform_count"]),
            cast(int, row["recommendation_count"]),
            cast(int, row["mention_count"]),
            cast(int, row["source_count"]),
        ),
        reverse=True,
    )

    max_source_count = max(
        (len(cast(set[str], row["urls"])) for row in channel_groups.values()),
        default=1,
    )
    max_question_count = max(
        (len(cast(set[str], row["question_pairs"])) for row in channel_groups.values()),
        default=1,
    )
    channel_rows: list[dict[str, object]] = []
    for row in channel_groups.values():
        platform_count = len(cast(set[str], row["platform_ids"]))
        count = len(cast(set[str], row["urls"]))
        question_count = len(cast(set[str], row["question_pairs"]))
        signal_score = round(
            platform_count / max(1, len(source_capable_platforms)) * 40
            + count / max_source_count * 35
            + question_count / max_question_count * 25,
        )
        confidence = (
            "high" if platform_count >= 2 and count >= 5 else "medium" if count >= 2 else "low"
        )
        channel_rows.append(
            {
                "channel_id": row["channel_id"],
                "channel_name": row["channel_name"],
                "signal_score": min(100, signal_score),
                "confidence": confidence,
                "source_count": count,
                "platform_count": platform_count,
                "platform_names": sorted(cast(set[str], row["platform_names"])),
                "question_count": question_count,
                "competitor_reference_count": row["competitor_reference_count"],
                "evidence": row["evidence"],
            },
        )
    channel_rows.sort(
        key=lambda row: (cast(int, row["signal_score"]), cast(int, row["source_count"])),
        reverse=True,
    )

    advice: list[dict[str, object]] = []
    if competitor_rows:
        leader = competitor_rows[0]
        strength_signals = cast(list[dict[str, str]], leader["strength_signals"])
        recommended_actions = cast(list[str], leader["recommended_actions"])
        advice.append(
            {
                "type": "competitor_gap",
                "title": f"补齐相对“{leader['name']}”的可见性差距",
                "reason": (
                    "；".join(
                        f"{signal['label']}（{signal['evidence']}）"
                        for signal in strength_signals[:4]
                    )
                    or "；".join(cast(list[str], leader["reasons"]))
                    or "该机构在本次回答中比客户品牌更突出。"
                ),
                "action": "；".join(recommended_actions[:3])
                or "补齐客户可核实的差异化事实，不复制竞品表述。",
                "confidence": (
                    "high"
                    if cast(int, leader["platform_count"]) >= 2
                    and cast(int, leader["source_count"]) >= 2
                    else "medium"
                    if strength_signals
                    else "low"
                ),
                "evidence_urls": leader["source_urls"],
            },
        )
    if channel_rows:
        channel = channel_rows[0]
        advice.append(
            {
                "type": "channel_signal",
                "title": f"优先验证 {channel['channel_name']} 的内容覆盖",
                "reason": (
                    f"本次观察到 {channel['source_count']} 条来源，覆盖 "
                    f"{channel['platform_count']} 个 AI 平台、"
                    f"{channel['question_count']} 个检测问题。"
                ),
                "action": (
                    "先发布或更新一篇事实清晰、主题单一、可公开访问的内容，"
                    "下一轮诊断观察该渠道是否继续成为来源。"
                ),
                "confidence": channel["confidence"],
                "evidence_urls": [
                    evidence["url"]
                    for evidence in cast(list[dict[str, object]], channel["evidence"])
                    if isinstance(evidence.get("url"), str)
                ],
            },
        )
    return {
        "evidence_platform_count": len(source_capable_platforms),
        "source_count": len(source_urls),
        "competitors": competitor_rows[:10],
        "channel_signals": channel_rows[:12],
        "advice": advice,
        "methodology_note": (
            "来源影响信号只反映本次 API 回答实际返回的来源分布，不是平台公开或内部排序权重。"
        ),
    }


def _evaluate_answer(
    *,
    question: AutoProbeQuestion,
    answer: str,
    brand_aliases: list[str],
    location_terms: list[str],
    service_terms: list[str],
    known_fact_terms: list[str],
    sources: tuple[ProviderSearchSource, ...] = (),
    source_capability: str = "available",
) -> dict[str, object]:
    normalized = answer.casefold()
    brand_found = any(alias in normalized for alias in brand_aliases)
    correctly_associated = brand_found and (
        any(term in normalized for term in location_terms)
        and any(term in normalized for term in service_terms)
    )
    recommended = (
        question["family"] == "recommendation"
        and brand_found
        and any(cue in normalized for cue in RECOMMENDATION_CUES)
        and not any(cue in normalized for cue in NEGATIVE_RECOMMENDATION_CUES)
    )
    visible_sources = SOURCE_URL_PATTERN.findall(answer)
    matched_terms = [term for term in known_fact_terms if term in normalized]
    return {
        "question_id": question["id"],
        "question_family": question["family"],
        "brand_found": brand_found,
        "correctly_associated": correctly_associated,
        "recommended": recommended,
        "matched_fact_count": len(matched_terms),
        "source_visible": bool(sources or visible_sources),
        "source_evaluable": source_capability != "not_supported",
    }


async def _call_platform(
    platform: PreparedPlatform,
    questions: list[AutoProbeQuestion],
) -> list[PlatformCall]:
    system_prompt = (
        "你是面向普通消费者的中文问答助手。独立、直接回答当前用户问题。"
        "不知道的信息要明确说明，不要为了迎合问题而强行提及企业，"
        "不要假设你正在参与品牌监测，也不要输出 JSON。"
    )
    calls: list[PlatformCall] = []
    client = ProviderClient()
    for question in questions:
        try:
            result = await client.diagnostic_chat(
                provider=platform.provider,
                base_url=platform.base_url,
                api_key=platform.api_key,
                model=platform.model,
                timeout_seconds=platform.timeout_seconds,
                system_prompt=system_prompt,
                user_prompt=question["text"],
                workspace_id=platform.workspace_id,
                max_tokens=1_200,
            )
            calls.append(
                PlatformCall(
                    question=question,
                    answer=result.content,
                    error=None,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    latency_ms=result.latency_ms,
                    sources=result.sources,
                    source_capability=result.source_capability,
                )
            )
        except ApiFailure as error:
            calls.append(
                PlatformCall(
                    question=question,
                    answer=None,
                    error=error.message,
                    input_tokens=0,
                    output_tokens=0,
                    latency_ms=0,
                    sources=(),
                    source_capability=(
                        "not_supported" if platform.provider == "deepseek" else "no_sources"
                    ),
                )
            )
    return calls


async def run_auto_diagnostic(
    database: AsyncSession,
    *,
    settings: Settings,
    client: Client,
    facts: list[Fact],
    measured_at: str,
) -> tuple[int | None, str, int, list[dict[str, object]]]:
    fact_values = {fact.key: fact.value.strip() for fact in facts}
    questions = build_auto_probe_questions(
        brand=client.short_name or client.standard_name,
        district=(
            fact_values.get("location.service_area")
            or fact_values.get("location.administrative_area")
            or client.district
        ),
        service=fact_values.get("service.primary") or client.industry_name,
        audience=fact_values.get("audience.primary") or "有相关需求的人",
    )
    placeholders: dict[str, dict[str, object]] = {}
    prepared: list[PreparedPlatform] = []
    if settings.model_execution_mode != "live" or settings.app_master_key is None:
        for platform in AUTO_DIAGNOSTIC_PLATFORMS:
            placeholders[platform["id"]] = _platform_placeholder(
                platform_id=platform["id"],
                platform_name=platform["name"],
                note=platform["note"],
                questions=questions,
                status="unconfigured",
                comment="当前环境未启用真实模型检测。",
            )
    else:
        cipher = SecretCipher(settings.app_master_key.get_secret_value())
        for platform in AUTO_DIAGNOSTIC_PLATFORMS:
            provider = platform["provider"]
            setting = await database.get(ProviderSetting, provider)
            model = _model_for(provider, setting) if setting is not None else None
            official_host = PROVIDER_OFFICIAL_HOSTS[provider]
            configured = (
                setting is not None
                and setting.enabled
                and setting.encrypted_api_key is not None
                and bool(model)
                and urlsplit(setting.base_url).hostname == official_host
            )
            if not configured or setting is None or model is None:
                placeholders[platform["id"]] = _platform_placeholder(
                    platform_id=platform["id"],
                    platform_name=platform["name"],
                    note=platform["note"],
                    questions=questions,
                    status="unconfigured",
                    comment=f"{platform['name']} API 尚未完整配置，未参与综合评分。",
                )
                continue
            try:
                reservation = await reserve_model_budget(
                    database,
                    provider=provider,
                    model=model,
                    purpose="geo_auto_diagnostic",
                    estimated_cny_fen=_budget_cost(provider, 1_500, 3_600),
                    client_id=client.id,
                    prompt_version=AUTO_DIAGNOSTIC_PROMPT_VERSION,
                    pricing_version=AUTO_DIAGNOSTIC_PRICING_VERSION,
                    commit=False,
                )
                prepared.append(
                    PreparedPlatform(
                        platform_id=platform["id"],
                        platform_name=platform["name"],
                        provider=provider,
                        note=platform["note"],
                        base_url=setting.base_url,
                        api_key=cipher.decrypt(
                            provider,
                            cast(bytes, setting.encrypted_api_key),
                        ),
                        model=model,
                        timeout_seconds=setting.timeout_seconds,
                        workspace_id=setting.workspace_id,
                        usage_id=reservation.usage_id,
                    )
                )
            except (ApiFailure, ValueError):
                placeholders[platform["id"]] = _platform_placeholder(
                    platform_id=platform["id"],
                    platform_name=platform["name"],
                    note=platform["note"],
                    questions=questions,
                    status="failed",
                    comment=f"{platform['name']} 当前配置或预算不可用，未参与综合评分。",
                )

    batches = (
        await asyncio.gather(*(_call_platform(platform, questions) for platform in prepared))
        if prepared
        else []
    )
    brand_aliases = _brand_aliases(client)
    location_terms = list(
        dict.fromkeys(
            value.casefold()
            for value in (
                client.district,
                client.city,
                fact_values.get("location.service_area"),
                fact_values.get("location.administrative_area"),
            )
            if value and len(value.strip()) >= 2
        )
    )
    service_terms = list(
        dict.fromkeys(
            value.casefold()
            for value in (
                client.industry_name,
                fact_values.get("identity.industry"),
                fact_values.get("service.primary"),
            )
            if value and len(value.strip()) >= 2
        )
    )
    known_fact_terms = _known_fact_terms(facts)
    results_by_id = dict(placeholders)
    for prepared_platform, calls in zip(prepared, batches, strict=True):
        successful = [call for call in calls if call.answer]
        total_input_tokens = sum(call.input_tokens for call in calls)
        total_output_tokens = sum(call.output_tokens for call in calls)
        total_latency = sum(call.latency_ms for call in calls)
        await finalize_model_usage(
            database,
            usage_id=prepared_platform.usage_id,
            status="succeeded" if successful else "failed",
            actual_cny_fen=(
                _budget_cost(
                    prepared_platform.provider,
                    total_input_tokens,
                    total_output_tokens,
                )
                if successful
                else 0
            ),
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            latency_ms=total_latency or None,
            input_hash=sha256(
                "\n".join(question["text"] for question in questions).encode()
            ).hexdigest(),
            output_hash=(
                sha256("\n".join(call.answer or "" for call in successful).encode()).hexdigest()
                if successful
                else None
            ),
            fallback_reason=None if successful else "all_probe_requests_failed",
            commit=False,
        )
        question_rows: list[dict[str, object]] = [
            {
                "id": call.question["id"],
                "family": call.question["family"],
                "label": call.question["label"],
                "text": call.question["text"],
                "answer_excerpt": (
                    re.sub(r"\s+", " ", call.answer).strip()[:500] if call.answer else None
                ),
                "status": "succeeded" if call.answer else "failed",
                "sources": [
                    {
                        "index": source.index,
                        "title": source.title,
                        "url": source.url,
                        "site_name": source.site_name,
                        "snippet": source.snippet,
                    }
                    for source in call.sources
                ],
            }
            for call in calls
        ]
        if not successful:
            results_by_id[prepared_platform.platform_id] = _platform_placeholder(
                platform_id=prepared_platform.platform_id,
                platform_name=prepared_platform.platform_name,
                note=prepared_platform.note,
                questions=questions,
                status="failed",
                comment="本次三个自动检测问题均未取得有效回答，失败不计入综合评分。",
            )
            results_by_id[prepared_platform.platform_id]["questions"] = question_rows
            continue
        evaluations = [
            _evaluate_answer(
                question=call.question,
                answer=cast(str, call.answer),
                brand_aliases=brand_aliases,
                location_terms=location_terms,
                service_terms=service_terms,
                known_fact_terms=known_fact_terms,
                sources=call.sources,
                source_capability=call.source_capability,
            )
            for call in successful
        ]
        result = calculate_platform_visibility(
            platform_id=prepared_platform.platform_id,
            platform_name=prepared_platform.platform_name,
            collection_mode="api",
            evaluations=evaluations,
            measured_at=measured_at,
            questions=question_rows,
        )
        result["platform_note"] = prepared_platform.note
        failed_count = len(calls) - len(successful)
        if failed_count:
            result["comment"] = (
                f"{result['comment']} 本次另有 {failed_count} 个问题请求失败，只按有效回答评分。"
            )
        sources = _source_rows(calls)
        competitors = _competitor_rows(calls, brand_aliases=brand_aliases)
        source_capability = next(
            (call.source_capability for call in calls if call.source_capability == "available"),
            next(
                (call.source_capability for call in calls if call.source_capability),
                "no_sources",
            ),
        )
        result["source_capability"] = source_capability
        result["source_count"] = len(sources)
        result["sources"] = sources
        result["competitors"] = competitors
        result["channel_signals"] = _channel_signal_rows(
            sources,
            competitors,
            total_question_count=len(questions),
        )
        results_by_id[prepared_platform.platform_id] = result

    platform_results = [
        results_by_id[platform["id"]]
        for platform in AUTO_DIAGNOSTIC_PLATFORMS
        if platform["id"] in results_by_id
    ]
    scored = [
        cast(int, result["score"])
        for result in platform_results
        if isinstance(result.get("score"), int)
    ]
    overall_score = round(sum(scored) / len(scored)) if scored else None
    effective_answer_count = sum(
        cast(int, result.get("valid_sample_count", 0)) for result in platform_results
    )
    level = "L0"
    if any(
        result.get("status") in {"mentioned", "associated", "recommended"}
        for result in platform_results
    ):
        level = "L1"
    if any(result.get("status") in {"associated", "recommended"} for result in platform_results):
        level = "L2"
    if any(result.get("status") == "recommended" for result in platform_results):
        level = "L3"
    recommended_platforms = sum(
        result.get("status") == "recommended" for result in platform_results
    )
    if overall_score is not None and overall_score >= 85 and recommended_platforms >= 3:
        level = "L4"
    return overall_score, level, effective_answer_count, platform_results
