from datetime import date
from typing import Annotated, Literal, TypedDict
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth import Authenticated, CsrfAuthenticated
from app.database import (
    ChannelRecommendation,
    Client,
    ContentBrief,
    ContentDocument,
    DatabaseSession,
    DiagnosticIssue,
    DiagnosticRun,
    Evidence,
    Job,
    utc_now,
)
from app.knowledge_context import PUBLIC_AUTHORIZATIONS
from app.responses import error_response, success_response
from app.strategy import diagnostic_snapshot_change_count

CATALOG_VERSION = "2026.08.10-1"
CATALOG_VERIFIED_ON = date(2026, 8, 10)
NO_GUARANTEE = "内容公开发布不等于一定被任何大模型收录、引用或推荐，需通过持续监测验证效果。"

Ownership = Literal[
    "operator_publishable",
    "client_required",
    "partner_cooperation",
]
Cost = Literal["free", "optional_paid", "paid"]
Access = Literal["public_web", "mostly_in_app", "mixed"]
Priority = Literal["P0", "P1", "P2"]
ContactPolicy = Literal["allow", "official_only", "omit", "manual_review"]


class ChannelCatalogEntry(TypedDict):
    id: str
    name: str
    official_url: str
    ownership: Ownership
    access: Access
    cost: Cost
    ecosystem_tags: list[str]
    supported_content_types: list[str]
    client_requirements: list[str]
    risks: list[str]
    priority: Priority
    active: bool


def _default_ownership() -> list[Ownership]:
    return [
        "operator_publishable",
        "client_required",
        "partner_cooperation",
    ]


class ChannelGenerateInput(BaseModel):
    brief_ids: list[UUID] = Field(default_factory=list, max_length=100)
    include_ownership: list[Ownership] = Field(
        default_factory=_default_ownership,
        min_length=1,
        max_length=3,
    )


CHANNEL_CATALOG: tuple[ChannelCatalogEntry, ...] = (
    {
        "id": "sohu",
        "name": "搜狐号",
        "official_url": "https://mp.sohu.com/",
        "ownership": "operator_publishable",
        "access": "public_web",
        "cost": "free",
        "ecosystem_tags": ["公开网页", "综合资讯"],
        "supported_content_types": ["企业事实", "服务指南", "常见问题"],
        "client_requirements": ["授权可公开的企业资料"],
        "risks": [
            "地域搜索词式标题、营销软文、重复关键词和正文联系方式可能被判违规",
            "发布后仍需逐篇核验公开访问状态",
        ],
        "priority": "P0",
        "active": True,
    },
    {
        "id": "baijia",
        "name": "百家号",
        "official_url": "https://baijiahao.baidu.com/",
        "ownership": "operator_publishable",
        "access": "public_web",
        "cost": "free",
        "ecosystem_tags": ["百度搜索生态", "公开网页"],
        "supported_content_types": ["企业事实", "服务说明", "常见问题"],
        "client_requirements": ["授权可公开的企业资料"],
        "risks": [
            "不得编造评价、榜单或效果承诺",
            "避免二维码、营销电话、公众号、第三方网址和诱导联系",
        ],
        "priority": "P0",
        "active": True,
    },
    {
        "id": "toutiao",
        "name": "头条号",
        "official_url": "https://mp.toutiao.com/",
        "ownership": "operator_publishable",
        "access": "mixed",
        "cost": "free",
        "ecosystem_tags": ["字节内容生态", "图文与视频"],
        "supported_content_types": ["本地指南", "问答文章", "图文"],
        "client_requirements": ["授权可公开的企业资料"],
        "risks": [
            "电话、微信、QQ、群、公众号、二维码及站外导流可能构成违规推广",
            "平台内分发与公开网页访问状态可能不同",
        ],
        "priority": "P0",
        "active": True,
    },
    {
        "id": "netease",
        "name": "网易号",
        "official_url": "https://mp.163.com/",
        "ownership": "operator_publishable",
        "access": "public_web",
        "cost": "free",
        "ecosystem_tags": ["网易内容生态", "公开网页"],
        "supported_content_types": ["本地指南", "企业事实", "服务科普"],
        "client_requirements": ["授权可公开的企业资料"],
        "risks": [
            "各类广告、软文或推广信息会被扣减信用度，品牌名称只能作一次中性来源说明",
            "禁止咨询、试听、到店、报名、预约、联系方式和站外导流等转化表达",
            "AI改写拼接、空洞水文、同质化批量内容和程序化连续发布可能被限制或禁言",
            "提交成功不等同于审核通过，发布后仍需核验公开状态",
        ],
        "priority": "P0",
        "active": True,
    },
    {
        "id": "penguin",
        "name": "企鹅号",
        "official_url": "https://om.qq.com/",
        "ownership": "operator_publishable",
        "access": "mixed",
        "cost": "free",
        "ecosystem_tags": ["腾讯内容生态", "腾讯新闻与QQ浏览器"],
        "supported_content_types": ["知识科普", "经验方法", "本地观察"],
        "client_requirements": ["授权可公开的企业资料", "真实且与文章相关的企业图片"],
        "risks": [
            "标题党、低信息量批量稿、无关配图和营销导流可能影响审核与推荐",
            "正文不得出现手机号、微信号、QQ号、二维码、无关网址或诱导关注购买",
            "模型生成内容需在发布页如实声明，提交后仍需持续回查审核与公开状态",
        ],
        "priority": "P0",
        "active": True,
    },
    {
        "id": "zhihu",
        "name": "知乎机构号",
        "official_url": "https://www.zhihu.com/org/signup",
        "ownership": "operator_publishable",
        "access": "public_web",
        "cost": "free",
        "ecosystem_tags": ["问答内容", "公开网页"],
        "supported_content_types": ["选择指南", "专业问答", "避坑说明"],
        "client_requirements": ["机构资料授权", "遵守机构号认证要求"],
        "risks": ["内容应直接回答问题，避免广告式堆砌和重复引流"],
        "priority": "P0",
        "active": True,
    },
    {
        "id": "wechat",
        "name": "微信公众号",
        "official_url": "https://mp.weixin.qq.com/",
        "ownership": "operator_publishable",
        "access": "mixed",
        "cost": "free",
        "ecosystem_tags": ["微信内容生态", "长图文"],
        "supported_content_types": ["企业介绍", "服务指南", "案例说明"],
        "client_requirements": ["授权可公开的企业资料"],
        "risks": ["搜索与外部抓取可见性需发布后单独核验"],
        "priority": "P1",
        "active": True,
    },
    {
        "id": "bilibili",
        "name": "哔哩哔哩",
        "official_url": "https://member.bilibili.com/creator/home",
        "ownership": "operator_publishable",
        "access": "mixed",
        "cost": "free",
        "ecosystem_tags": ["视频生态", "知识内容"],
        "supported_content_types": ["讲解视频", "案例展示", "知识科普"],
        "client_requirements": ["视频或图文素材使用授权"],
        "risks": ["需要把长文改编为视频脚本或专栏格式，避免无关广告与过度营销"],
        "priority": "P1",
        "active": True,
    },
    {
        "id": "xiaohongshu",
        "name": "小红书",
        "official_url": "https://creator.xiaohongshu.com/",
        "ownership": "operator_publishable",
        "access": "mostly_in_app",
        "cost": "free",
        "ecosystem_tags": ["生活决策", "图文与短视频"],
        "supported_content_types": ["本地攻略", "场景问答", "图文笔记"],
        "client_requirements": ["图片或视频素材使用授权"],
        "risks": [
            "以平台内访问为主，不能等同于公开网页收录",
            "商业合作内容、站外导流和联系方式需按账号类型与最新规则复核",
        ],
        "priority": "P1",
        "active": True,
    },
    {
        "id": "douyin",
        "name": "抖音",
        "official_url": "https://creator.douyin.com/",
        "ownership": "operator_publishable",
        "access": "mostly_in_app",
        "cost": "free",
        "ecosystem_tags": ["字节内容生态", "短视频"],
        "supported_content_types": ["口播脚本", "场景解答", "案例视频"],
        "client_requirements": ["视频素材与出镜授权"],
        "risks": [
            "以平台内访问为主，需制作适合短视频的信息表达",
            "避免商业招揽、过度营销、夸张标题及未标识的易混淆 AI 内容",
        ],
        "priority": "P1",
        "active": True,
    },
    {
        "id": "baidu_maps",
        "name": "百度地图商户",
        "official_url": "https://map.baidu.com/",
        "ownership": "client_required",
        "access": "public_web",
        "cost": "optional_paid",
        "ecosystem_tags": ["本地实体", "百度生态"],
        "supported_content_types": ["地址", "营业信息", "服务范围"],
        "client_requirements": ["客户主体认证", "地址、电话与营业信息核验"],
        "risks": ["主体资料和门店信息变更需客户配合"],
        "priority": "P0",
        "active": True,
    },
    {
        "id": "amap",
        "name": "高德地图商户",
        "official_url": "https://ditu.amap.com/",
        "ownership": "client_required",
        "access": "public_web",
        "cost": "optional_paid",
        "ecosystem_tags": ["本地实体", "地图生态"],
        "supported_content_types": ["地址", "营业信息", "服务范围"],
        "client_requirements": ["客户主体认证", "地址、电话与营业信息核验"],
        "risks": ["主体资料和门店信息变更需客户配合"],
        "priority": "P1",
        "active": True,
    },
    {
        "id": "baidu_marketing",
        "name": "百度营销",
        "official_url": "https://e.baidu.com/",
        "ownership": "partner_cooperation",
        "access": "mixed",
        "cost": "paid",
        "ecosystem_tags": ["百度生态", "正式广告"],
        "supported_content_types": ["品牌说明", "服务落地页", "本地推广"],
        "client_requirements": ["客户主体资质", "预算与广告授权"],
        "risks": ["属于付费推广，不等同于自然收录或模型推荐"],
        "priority": "P2",
        "active": True,
    },
    {
        "id": "oceanengine",
        "name": "巨量引擎",
        "official_url": "https://www.oceanengine.com/",
        "ownership": "partner_cooperation",
        "access": "mixed",
        "cost": "paid",
        "ecosystem_tags": ["字节商业生态", "正式广告"],
        "supported_content_types": ["品牌说明", "短视频广告", "本地推广"],
        "client_requirements": ["客户主体资质", "预算与广告授权"],
        "risks": ["属于付费推广，不等同于自然收录或模型推荐"],
        "priority": "P2",
        "active": True,
    },
)
CATALOG_BY_ID = {str(item["id"]): item for item in CHANNEL_CATALOG}
CHANNEL_CONTACT_POLICIES: dict[str, ContactPolicy] = {
    "zhihu": "official_only",
    "sohu": "omit",
    "baijia": "omit",
    "toutiao": "omit",
    "netease": "omit",
    "penguin": "omit",
    "xiaohongshu": "omit",
    "douyin": "omit",
    "baidu_maps": "allow",
    "amap": "allow",
}
CONTACT_POLICY_LABELS: dict[ContactPolicy, str] = {
    "allow": "可保留已核验联系方式",
    "official_only": "仅保留官方主页入口",
    "omit": "删除手机号与微信",
    "manual_review": "发布前人工复核",
}
CONTACT_POLICY_NOTES: dict[ContactPolicy, str] = {
    "allow": "仅可使用企业知识库中已经确认的联系方式。",
    "official_only": "正文不出现手机号、微信号或二维码，只提示通过官方主页联系。",
    "omit": "生成渠道版本时自动删除手机号、微信号、二维码和站外导流表达。",
    "manual_review": "默认不主动加入直接联系方式，发布前按平台实时规则复核。",
}

INDUSTRY_CHANNEL_BOOSTS: dict[str, dict[str, int]] = {
    "art_education": {
        "xiaohongshu": 18,
        "douyin": 13,
        "bilibili": 10,
        "zhihu": 6,
    },
    "housekeeping": {
        "xiaohongshu": 18,
        "douyin": 22,
        "toutiao": 8,
        "baidu_maps": 8,
        "amap": 7,
    },
    "repair": {
        "baijia": 12,
        "zhihu": 10,
        "bilibili": 10,
        "toutiao": 8,
        "baidu_maps": 8,
        "amap": 7,
    },
}

CONTENT_TYPE_LABELS: dict[str, tuple[str, ...]] = {
    "entity_profile": ("企业事实", "企业介绍", "品牌说明"),
    "service_explainer": ("服务说明", "服务指南", "专业问答"),
    "selection_guide": ("选择指南", "避坑说明", "本地攻略"),
    "practical_guide": ("实用攻略", "避坑说明", "本地攻略"),
    "faq": ("常见问题", "专业问答", "问答文章", "场景问答"),
    "price_guide": ("服务指南", "专业问答", "本地攻略"),
    "service_process": ("服务说明", "服务指南", "专业问答"),
    "local_presence": ("本地指南", "本地攻略", "品牌说明"),
    "local_recommendation": ("选择指南", "本地攻略", "问答文章"),
    "scenario_solution": ("本地指南", "场景解答", "场景问答"),
    "comparison": ("选择指南", "避坑说明", "专业问答"),
    "case_study": ("案例说明", "案例展示", "案例视频"),
    "capability_proof": ("案例说明", "案例展示", "知识科普"),
    "case": ("案例说明", "案例展示", "案例视频"),
    "local_scenario": ("本地指南", "本地攻略", "场景解答", "场景问答"),
}


def _channel_data(channel: ChannelCatalogEntry) -> dict[str, object]:
    contact_policy = CHANNEL_CONTACT_POLICIES.get(channel["id"], "manual_review")
    return {
        **channel,
        "verified_on": CATALOG_VERIFIED_ON.isoformat(),
        "contact_policy": contact_policy,
        "contact_policy_label": CONTACT_POLICY_LABELS[contact_policy],
        "contact_policy_note": CONTACT_POLICY_NOTES[contact_policy],
    }


def _brief_content_types(brief: ContentBrief) -> list[str]:
    return list(CONTENT_TYPE_LABELS.get(brief.content_type, ("服务指南",)))


def _required_adaptation(channel_id: str, brief: ContentBrief) -> str:
    target = brief.target_keywords[0] if brief.target_keywords else brief.title
    rules = {
        "zhihu": f"改成直接回答“{target}”的问答结构，开头先给选择标准，再用已授权事实举例。",
        "xiaohongshu": "改成 6—9 个短段落的本地决策笔记，配真实授权图片，避免广告口号和标签堆砌。",
        "douyin": "改成 60—90 秒口播脚本，前三秒提出用户问题，正文只讲可核验事实并给出核验动作。",
        "bilibili": "改成 3—5 分钟知识讲解脚本，增加章节标题、事实来源说明和结尾核验清单。",
        "wechat": "保留完整长文和来源说明，增加摘要、目录与可复制的常见问题区。",
        "baidu_maps": (
            "提取机构名称、地址、营业时间、电话和服务范围等结构化实体信息，不发布长文章。"
        ),
        "amap": ("提取机构名称、地址、营业时间、电话和服务范围等结构化实体信息，不发布长文章。"),
    }
    return rules.get(
        channel_id,
        "保留地区、服务和目标问题，在开头给出简短结论，正文使用小标题、事实来源和常见问题结构。",
    )


def _account_positioning(channel: ChannelCatalogEntry, client: Client) -> str:
    area = client.district or client.city
    if channel["ownership"] == "client_required":
        return f"使用“{client.standard_name}”经主体认证的商户账号，保持名称、地址和电话一致。"
    if channel["ownership"] == "partner_cooperation":
        return f"以正规合作内容标识发布，说明服务地区为{area}，不伪装成新闻报道或自然推荐。"
    return (
        f"以“{area}{client.industry_name}服务指南”定位的运营账号发布，"
        f"可引用{client.standard_name}的授权事实，但不得冒充客户官方账号。"
    )


def _target_ecosystems(channel: ChannelCatalogEntry) -> list[str]:
    return list(channel["ecosystem_tags"])


def _score_channel(
    channel: ChannelCatalogEntry,
    brief: ContentBrief,
    client: Client,
    diagnostic_issue_categories: set[str],
) -> tuple[int, list[str]]:
    ownership = str(channel["ownership"])
    access = str(channel["access"])
    cost = str(channel["cost"])
    score = {
        "operator_publishable": 60,
        "client_required": 50,
        "partner_cooperation": 38,
    }[ownership]
    reasons: list[str] = []
    if ownership == "operator_publishable":
        reasons.append("运营方可以统一注册并人工发布，客户只需授权企业资料")
    elif ownership == "client_required":
        reasons.append("能补强本地实体信息，但主体认证和门店核验需要客户配合")
    else:
        reasons.append("适合作为可选付费合作，不进入首批自然内容发布清单")
    if access == "public_web":
        score += 14
        reasons.append("内容或实体信息可通过公开网页访问，便于后续核验可见性")
    elif access == "mixed":
        score += 7
        reasons.append("同时覆盖平台生态与部分公开访问场景")
    else:
        reasons.append("主要在平台内访问，适合补充用户决策触点")
    if cost == "free":
        score += 5
    elif cost == "paid":
        score -= 8
    score += {"P0": 6, "P1": 0, "P2": -4}[channel["priority"]]
    if channel["id"] in (brief.suggested_channel_ids or []):
        score += 8
        reasons.append("已被客户当前内容简报列为建议渠道")
    industry_boost = INDUSTRY_CHANNEL_BOOSTS.get(client.industry_code, {}).get(
        channel["id"],
        0,
    )
    if industry_boost:
        score += industry_boost
        reasons.append(f"与{client.industry_name}行业的常见内容形态匹配")
    brief_types = _brief_content_types(brief)
    matched_types = [value for value in channel["supported_content_types"] if value in brief_types]
    if matched_types:
        score += 10
        reasons.append(f"适合本篇“{brief.title}”的{matched_types[0]}表达")
    local_context = " ".join([brief.title, brief.audience, *brief.target_keywords])
    targets_local_area = any(
        area and area in local_context for area in (client.city, client.district)
    )
    if targets_local_area and "本地实体" in channel["ecosystem_tags"]:
        score += 8
        reasons.append(f"可补强{client.district or client.city}本地实体信息")
    if "source" in diagnostic_issue_categories and access == "public_web":
        score += 5
        reasons.append("当前诊断存在来源缺口，公开网页渠道优先")
    if "entity" in diagnostic_issue_categories and "本地实体" in channel["ecosystem_tags"]:
        score += 5
        reasons.append("当前诊断存在实体缺口，地图商户信息可作为补充")
    if "visibility" in diagnostic_issue_categories and channel["ecosystem_tags"]:
        score += 2
    return max(0, min(score, 100)), reasons[:4]


def _recommendation_data(
    recommendation: ChannelRecommendation,
) -> dict[str, object] | None:
    channel_snapshot = recommendation.channel_snapshot
    if not channel_snapshot:
        return None
    brief_snapshot = recommendation.brief_snapshot
    return {
        "id": str(recommendation.id),
        "client_id": str(recommendation.client_id),
        "generation_id": (
            str(recommendation.generation_id) if recommendation.generation_id is not None else None
        ),
        "brief_id": str(recommendation.brief_id) if recommendation.brief_id else None,
        "brief_title": brief_snapshot.get("title", "历史内容简报"),
        "brief_content_type": brief_snapshot.get("content_type"),
        "content_document_id": (
            str(recommendation.content_document_id) if recommendation.content_document_id else None
        ),
        "channel": channel_snapshot,
        "priority": recommendation.priority,
        "fit_score": recommendation.fit_score,
        "reasons": recommendation.reasons,
        "recommended_content_types": recommendation.recommended_content_types,
        "required_actions": recommendation.required_actions,
        "required_adaptation": recommendation.required_adaptation,
        "account_positioning": recommendation.account_positioning,
        "authorization_note": recommendation.authorization_note,
        "cost_note": recommendation.cost_note,
        "risk_note": recommendation.risk_note,
        "target_ecosystems": recommendation.target_ecosystems,
        "catalog_version": recommendation.catalog_version,
        "caveat": recommendation.caveat,
        "generated_at": recommendation.generated_at.isoformat(),
    }


def _job_accepted(job: Job) -> dict[str, object]:
    return {
        "job_id": str(job.id),
        "status": job.status,
        "progress": job.progress,
        "resource_type": "channel_recommendation",
        "resource_id": None,
    }


async def process_channel_job(
    session_factory: async_sessionmaker[AsyncSession],
    claimed_job: Job,
) -> bool:
    now = utc_now()
    async with session_factory() as database:
        async with database.begin():
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
            if job is None:
                return False
            client = await database.scalar(
                select(Client).where(Client.id == job.client_id).with_for_update(),
            )
            if client is None:
                job.status = "failed"
                job.progress = 100
                job.error_message = "客户不存在"
                job.lease_until = None
                job.completed_at = now
                return True
            raw_brief_ids = job.payload.get("brief_ids", [])
            raw_ownership = job.payload.get("include_ownership", [])
            if not isinstance(raw_brief_ids, list) or not isinstance(
                raw_ownership,
                list,
            ):
                job.status = "failed"
                job.progress = 100
                job.error_message = "渠道推荐任务参数无效"
                job.lease_until = None
                job.completed_at = now
                return True
            brief_ids = [UUID(str(value)) for value in raw_brief_ids]
            brief_query = (
                select(ContentBrief)
                .where(
                    ContentBrief.client_id == job.client_id,
                )
                .order_by(ContentBrief.priority, ContentBrief.id)
                .with_for_update()
            )
            if brief_ids:
                brief_query = brief_query.where(ContentBrief.id.in_(brief_ids))
            briefs = list((await database.scalars(brief_query)).all())
            if not briefs:
                job.status = "failed"
                job.progress = 100
                job.error_message = "客户暂无可用内容简报"
                job.lease_until = None
                job.completed_at = now
                return True
            included = {str(value) for value in raw_ownership}
            latest_diagnostic = await database.scalar(
                select(DiagnosticRun)
                .where(DiagnosticRun.client_id == job.client_id)
                .order_by(DiagnosticRun.created_at.desc(), DiagnosticRun.id.desc())
                .limit(1),
            )
            if latest_diagnostic is None:
                job.status = "failed"
                job.progress = 100
                job.error_message = "请先完成 GEO 诊断"
                job.lease_until = None
                job.completed_at = now
                return True
            if await diagnostic_snapshot_change_count(database, latest_diagnostic):
                job.status = "failed"
                job.progress = 100
                job.error_message = "知识库已更新，请先重新运行 GEO 诊断"
                job.lease_until = None
                job.completed_at = now
                return True
            diagnostic_issue_categories: set[str] = set()
            diagnostic_issue_categories = set(
                (
                    await database.scalars(
                        select(DiagnosticIssue.category).where(
                            DiagnosticIssue.diagnostic_run_id == latest_diagnostic.id,
                            DiagnosticIssue.status == "open",
                        ),
                    )
                ).all(),
            )
            evidence_ids = {
                UUID(value) for brief in briefs for value in (brief.required_evidence_ids or [])
            }
            evidence_authorizations = {
                evidence.id: evidence.authorization_status
                for evidence in (
                    (
                        await database.scalars(
                            select(Evidence).where(Evidence.id.in_(evidence_ids)),
                        )
                    ).all()
                    if evidence_ids
                    else []
                )
            }
            documents = {
                document.brief_id: document
                for document in (
                    await database.scalars(
                        select(ContentDocument).where(
                            ContentDocument.client_id == job.client_id,
                            ContentDocument.brief_id.in_([brief.id for brief in briefs]),
                        ),
                    )
                ).all()
            }
            generation_id = uuid4()
            await database.execute(
                update(ChannelRecommendation)
                .where(
                    ChannelRecommendation.client_id == job.client_id,
                    ChannelRecommendation.active.is_(True),
                )
                .values(active=False),
            )
            limits = {
                "operator_publishable": 4,
                "client_required": 2,
                "partner_cooperation": 1,
            }
            for brief in briefs:
                scored = [
                    (
                        channel,
                        *_score_channel(
                            channel,
                            brief,
                            client,
                            diagnostic_issue_categories,
                        ),
                    )
                    for channel in CHANNEL_CATALOG
                    if channel["active"] and channel["ownership"] in included
                ]
                scored.sort(key=lambda item: (-item[1], str(item[0]["id"])))
                selected: list[tuple[ChannelCatalogEntry, int, list[str]]] = []
                for ownership in _default_ownership():
                    selected.extend(
                        [item for item in scored if item[0]["ownership"] == ownership][
                            : limits[ownership]
                        ],
                    )
                recommended_channel_ids = [
                    channel["id"]
                    for channel, _score, _reasons in selected
                    if channel["ownership"] == "operator_publishable"
                ][: limits["operator_publishable"]]
                if recommended_channel_ids and (
                    brief.suggested_channel_ids != recommended_channel_ids
                ):
                    brief.suggested_channel_ids = recommended_channel_ids
                    brief.version += 1
                brief_evidence_ids = [UUID(value) for value in (brief.required_evidence_ids or [])]
                authorized_count = sum(
                    evidence_authorizations.get(evidence_id) in PUBLIC_AUTHORIZATIONS
                    for evidence_id in brief_evidence_ids
                )
                authorization_note = (
                    f"本篇引用的 {authorized_count} 条来源已满足可公开条件。"
                    if authorized_count == len(brief_evidence_ids)
                    else (
                        f"本篇 {len(brief_evidence_ids)} 条来源中有 "
                        f"{len(brief_evidence_ids) - authorized_count} 条需补充公开授权，"
                        "授权完成前不得发布。"
                    )
                )
                for channel, score, reasons in selected:
                    priority = (
                        1
                        if channel["ownership"] == "operator_publishable"
                        else 2
                        if channel["ownership"] == "client_required"
                        else 3
                    )
                    required_actions = list(channel["client_requirements"])
                    if channel["ownership"] == "operator_publishable":
                        required_actions = [
                            "运营方人工注册并按平台规则发布",
                            *required_actions,
                        ]
                    if authorized_count != len(brief_evidence_ids):
                        required_actions.insert(0, "先补齐本篇所用来源的公开授权")
                    content_types = _brief_content_types(brief)
                    document = documents.get(brief.id)
                    database.add(
                        ChannelRecommendation(
                            client_id=job.client_id,
                            generation_id=generation_id,
                            brief_id=brief.id,
                            content_document_id=document.id if document else None,
                            channel_id=channel["id"],
                            catalog_version=CATALOG_VERSION,
                            channel_snapshot=_channel_data(channel),
                            brief_snapshot={
                                "id": str(brief.id),
                                "title": brief.title,
                                "content_type": brief.content_type,
                                "target_keywords": list(brief.target_keywords),
                                "angle": brief.angle,
                                "version": brief.version,
                            },
                            priority=priority,
                            fit_score=score,
                            reasons=reasons,
                            recommended_content_types=[
                                value
                                for value in channel["supported_content_types"]
                                if value in content_types
                            ]
                            or list(channel["supported_content_types"])[:2],
                            required_actions=required_actions,
                            required_adaptation=_required_adaptation(
                                channel["id"],
                                brief,
                            ),
                            account_positioning=_account_positioning(channel, client),
                            authorization_note=authorization_note,
                            cost_note=(
                                "基础发布免费，增值推广以平台实时规则为准。"
                                if channel["cost"] == "optional_paid"
                                else "基础发布免费，不包含人工制作与运营成本。"
                                if channel["cost"] == "free"
                                else "属于付费合作，启用前必须人工确认预算和合同。"
                            ),
                            risk_note="、".join(channel["risks"]),
                            target_ecosystems=_target_ecosystems(channel),
                            caveat=NO_GUARANTEE,
                            source_brief_ids=[str(brief.id)],
                            generated_at=now,
                        ),
                    )
            job.status = "succeeded"
            job.progress = 100
            job.lease_until = None
            job.completed_at = now
        return True


def build_channels_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["channels"])

    @router.get("/channels")
    async def get_channels(
        request: Request,
        authentication: Authenticated,
        ownership: Annotated[Ownership | None, Query()] = None,
        cost: Annotated[Cost | None, Query()] = None,
        content_type: Annotated[str | None, Query(max_length=100)] = None,
        active: Annotated[bool, Query()] = True,
    ) -> Response:
        items = [
            _channel_data(channel)
            for channel in CHANNEL_CATALOG
            if (not active or channel["active"])
            and (ownership is None or channel["ownership"] == ownership)
            and (cost is None or channel["cost"] == cost)
            and (content_type is None or content_type in channel["supported_content_types"])
        ]
        return success_response(
            request,
            {"items": items, "catalog_version": CATALOG_VERSION},
        )

    @router.get("/clients/{client_id}/channel-recommendations")
    async def get_recommendations(
        request: Request,
        client_id: UUID,
        database: DatabaseSession,
        authentication: Authenticated,
        active_only: Annotated[bool, Query()] = True,
    ) -> Response:
        if await database.get(Client, client_id) is None:
            return error_response(
                request,
                status_code=404,
                code=40401,
                message="客户不存在",
            )
        query = select(ChannelRecommendation).where(
            ChannelRecommendation.client_id == client_id,
        )
        if active_only:
            query = query.where(ChannelRecommendation.active.is_(True))
        recommendations = list(
            (
                await database.scalars(
                    query.order_by(
                        ChannelRecommendation.priority,
                        ChannelRecommendation.fit_score.desc(),
                        ChannelRecommendation.channel_id,
                    ),
                )
            ).all(),
        )
        items = [
            item
            for recommendation in recommendations
            if (item := _recommendation_data(recommendation)) is not None
        ]
        return success_response(
            request,
            {
                "items": items,
                "generated_at": (
                    max(value.generated_at for value in recommendations).isoformat()
                    if recommendations
                    else None
                ),
            },
        )

    @router.post("/clients/{client_id}/channel-recommendations/generate")
    async def generate_recommendations(
        request: Request,
        client_id: UUID,
        body: ChannelGenerateInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
        idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    ) -> Response:
        client = await database.get(Client, client_id)
        if client is None:
            return error_response(
                request,
                status_code=404,
                code=40401,
                message="客户不存在",
            )
        if client.status != "active":
            return error_response(
                request,
                status_code=409,
                code=40901,
                message="客户已暂停或归档，不能生成渠道建议",
            )
        brief_query = (
            select(ContentBrief.id)
            .where(
                ContentBrief.client_id == client_id,
            )
            .order_by(ContentBrief.priority, ContentBrief.id)
        )
        if body.brief_ids:
            brief_query = brief_query.where(ContentBrief.id.in_(body.brief_ids))
        available_briefs = sorted(
            (await database.scalars(brief_query)).all(),
            key=str,
        )
        if not available_briefs or (
            body.brief_ids and set(available_briefs) != set(body.brief_ids)
        ):
            return error_response(
                request,
                status_code=422,
                code=42201,
                message="客户暂无可用内容简报，请先生成内容策略",
            )
        payload = {
            "brief_ids": [str(value) for value in available_briefs],
            "include_ownership": sorted(set(body.include_ownership)),
            "catalog_version": CATALOG_VERSION,
        }
        key = str(idempotency_key)
        existing = await database.scalar(
            select(Job).where(
                Job.client_id == client_id,
                Job.job_type == "channel_recommend",
                Job.idempotency_key == key,
            ),
        )
        if existing is not None:
            if existing.payload != payload:
                return error_response(
                    request,
                    status_code=409,
                    code=40903,
                    message="幂等键已用于不同的渠道推荐参数",
                )
            return success_response(
                request,
                _job_accepted(existing),
                status_code=202,
            )
        job = Job(
            client_id=client_id,
            job_type="channel_recommend",
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
                    Job.job_type == "channel_recommend",
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
                    message="幂等键已用于不同的渠道推荐参数",
                )
            job = existing
        return success_response(
            request,
            _job_accepted(job),
            status_code=202,
        )

    return router
