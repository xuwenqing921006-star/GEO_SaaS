# ruff: noqa: RUF001

import re
from datetime import date
from typing import Annotated, Literal, TypedDict
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth import Authenticated, CsrfAuthenticated
from app.database import (
    DatabaseSession,
    PromptTemplate,
    PromptTemplateVersion,
)
from app.publishing_specs import platform_generation_instruction
from app.responses import ApiFailure, success_response

PromptCategory = Literal[
    "guardrail",
    "base",
    "content_form",
    "keyword_strategy",
    "channel_adapter",
]
ContactPolicy = Literal["allow", "official_only", "omit", "manual_review"]

AVAILABLE_VARIABLES = (
    "企业标准名称",
    "品牌简称",
    "所在地区",
    "所属行业",
    "主营业务",
    "企业介绍",
    "企业事实",
    "用户主问题",
    "主关键词",
    "关键词类型",
    "用户意图",
    "内容角度",
    "目标字数",
    "目标渠道",
)
VARIABLE_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


class PromptSeed(TypedDict):
    code: str
    category: PromptCategory
    name: str
    description: str
    text: str
    editable: bool
    variables: list[str]
    required_fact_keys: list[str]
    contact_policy: ContactPolicy | None
    default_contact_policy: ContactPolicy | None
    channel_id: str | None
    source_url: str | None
    verified_at: date | None


def _seed(
    *,
    code: str,
    category: PromptCategory,
    name: str,
    description: str,
    text: str,
    editable: bool = True,
    variables: list[str] | None = None,
    required_fact_keys: list[str] | None = None,
    contact_policy: ContactPolicy | None = None,
    channel_id: str | None = None,
    source_url: str | None = None,
    verified_at: date | None = None,
) -> PromptSeed:
    return {
        "code": code,
        "category": category,
        "name": name,
        "description": description,
        "text": text,
        "editable": editable,
        "variables": variables or [],
        "required_fact_keys": required_fact_keys or [],
        "contact_policy": contact_policy,
        "default_contact_policy": contact_policy,
        "channel_id": channel_id,
        "source_url": source_url,
        "verified_at": verified_at,
    }


CONTENT_FORM_SEEDS = (
    _seed(
        code="local_recommendation",
        category="content_form",
        name="本地推荐解答",
        description="回答“哪家好、推荐一家”等本地决策问题，但不伪造榜单或第三方背书。",
        text=(
            "围绕{{用户主问题}}先说明推荐时应核验的条件，再基于{{企业事实}}介绍"
            "{{品牌简称}}与这些条件的对应情况。明确哪些信息仍需用户自行确认，"
            "不得声称“最好、第一、首选”，不得伪装成第三方测评。"
        ),
        variables=["用户主问题", "企业事实", "品牌简称"],
        required_fact_keys=["identity", "location", "service"],
    ),
    _seed(
        code="selection_guide",
        category="content_form",
        name="选择指南",
        description="提供可执行的选择标准，并自然说明企业与标准的匹配情况。",
        text=(
            "直接回答{{用户主问题}}。先给出3至5项真实可核验的选择标准，"
            "再结合{{企业事实}}说明{{品牌简称}}目前可以确认的情况。"
            "文章以帮助决策为主，不写广告口号，不制造虚假对比。"
        ),
        variables=["用户主问题", "企业事实", "品牌简称"],
        required_fact_keys=["location", "service"],
    ),
    _seed(
        code="practical_guide",
        category="content_form",
        name="实用攻略",
        description="围绕办理、准备、避坑等问题提供步骤化建议。",
        text=(
            "把{{用户主问题}}写成一篇能直接照着执行的实用攻略。"
            "按准备、咨询、现场核验、决定四个阶段组织，穿插{{企业事实}}中的真实例子，"
            "不为凑字数重复关键词。"
        ),
        variables=["用户主问题", "企业事实"],
        required_fact_keys=["service"],
    ),
    _seed(
        code="service_explainer",
        category="content_form",
        name="服务说明",
        description="解释具体服务适合谁、如何进行以及咨询前需确认什么。",
        text=(
            "围绕{{主关键词}}说明{{主营业务}}具体解决什么问题、适合哪些人、"
            "通常如何开展以及咨询前要确认什么。涉及客户企业的内容只使用"
            "{{企业事实}}；行业通用说明可以合理补充，但不能写成该企业已提供的"
            "价格、效果、师资、课程设置或承诺。"
        ),
        variables=["主关键词", "主营业务", "企业事实"],
        required_fact_keys=["service"],
    ),
    _seed(
        code="scenario_solution",
        category="content_form",
        name="场景解决方案",
        description="从某类人群或具体情境出发，解释需求和判断方法。",
        text=(
            "以{{用户主问题}}所描述的真实场景开篇，先解释用户可能遇到的困难，"
            "再给出判断与行动建议。仅在与场景相关时引用{{品牌简称}}的{{企业事实}}，"
            "不强行植入企业名称。"
        ),
        variables=["用户主问题", "品牌简称", "企业事实"],
        required_fact_keys=["service"],
    ),
    _seed(
        code="faq",
        category="content_form",
        name="常见问题",
        description="用自然问答覆盖一个主问题及其合理追问。",
        text=(
            "以{{用户主问题}}为主问题，补充4至6个用户自然会继续追问的问题。"
            "每个回答先给短结论，再给依据；涉及{{品牌简称}}时只能引用{{企业事实}}。"
        ),
        variables=["用户主问题", "品牌简称", "企业事实"],
        required_fact_keys=["identity", "service"],
    ),
    _seed(
        code="local_presence",
        category="content_form",
        name="本地服务说明",
        description="强化地区、服务对象、主营业务之间的实体关联。",
        text=(
            "自然说明{{企业标准名称}}在{{所在地区}}提供的{{主营业务}}，"
            "重点回答本地用户如何判断服务是否适合自己。地区词与业务词各自然出现，"
            "不要在标题和段落中机械重复。"
        ),
        variables=["企业标准名称", "所在地区", "主营业务"],
        required_fact_keys=["identity", "location", "service"],
    ),
    _seed(
        code="entity_profile",
        category="content_form",
        name="企业事实介绍",
        description="形成清晰、可摘取的企业实体说明，不写成招商宣传稿。",
        text=(
            "根据{{企业事实}}介绍{{企业标准名称}}是谁、位于哪里、提供什么服务、"
            "适合哪些需求以及有哪些仍需咨询确认的信息。使用事实型小标题，"
            "不使用“领先、顶级、值得信赖”等无依据形容词。"
        ),
        variables=["企业事实", "企业标准名称"],
        required_fact_keys=["identity", "location", "service"],
    ),
    _seed(
        code="price_guide",
        category="content_form",
        name="费用与价格说明",
        description="解释价格构成和询价方法；没有价格事实时绝不编造数字。",
        text=(
            "回答{{用户主问题}}中的价格或费用意图。若{{企业事实}}没有确认价格，"
            "只解释常见影响因素和询价时应确认的项目，并明确以实际咨询为准；"
            "不得虚构区间、优惠或低价承诺。"
        ),
        variables=["用户主问题", "企业事实"],
        required_fact_keys=["service", "price"],
    ),
    _seed(
        code="service_process",
        category="content_form",
        name="服务流程说明",
        description="说明从咨询到交付的流程及每一步需要核验的信息。",
        text=(
            "围绕{{用户主问题}}按时间顺序说明可能的咨询和服务流程。"
            "已确认流程使用{{企业事实}}，行业通用建议必须标明为咨询核验项，"
            "不可把通用流程冒充成{{品牌简称}}已提供的承诺。"
        ),
        variables=["用户主问题", "企业事实", "品牌简称"],
        required_fact_keys=["service", "process"],
    ),
    _seed(
        code="comparison",
        category="content_form",
        name="方案对比",
        description="比较服务类型或选择路径，不攻击竞争对手、不伪造排名。",
        text=(
            "围绕{{用户主问题}}比较不同选择路径的适用情况、核验重点和可能代价。"
            "不点名贬低其他企业，不编造榜单；介绍{{品牌简称}}时只使用{{企业事实}}。"
        ),
        variables=["用户主问题", "品牌简称", "企业事实"],
        required_fact_keys=["service"],
    ),
    _seed(
        code="case_study",
        category="content_form",
        name="案例复盘",
        description="仅在知识库存在真实案例时使用，突出过程而非效果承诺。",
        text=(
            "只根据{{企业事实}}中已经确认的案例，说明背景、需求、过程和可复用经验。"
            "隐去个人敏感信息，不夸大结果；若没有完整案例事实，停止生成并提示补充资料。"
        ),
        variables=["企业事实"],
        required_fact_keys=["case"],
    ),
)

PROMPT_SEEDS: tuple[PromptSeed, ...] = (
    _seed(
        code="writer_guardrail",
        category="guardrail",
        name="内容安全保护层",
        description="系统只读规则，防止虚构事实、内部信息泄漏和渠道导流风险。",
        text=(
            "这是一次成稿任务，只能输出已经完成事实映射和发布前自检的最终稿，"
            "不得输出试稿或把常规问题留给运营人员。凡是描述客户企业自身的信息，"
            "只能使用系统提供的可发布企业事实；"
            "没有提供的价格、人数、校区数量、课程设置、师资、资质、排名、案例和"
            "效果不得推测或补写。可以补充合理的行业常识、选择方法、年龄阶段关注点"
            "和场景建议，但必须写成通用建议，不能冒充该企业已经提供的服务或承诺。"
            "不得输出UUID、client_id、"
            "fact_id、evidence_id或“来源:”等内部标记。不得把企业写成公认最好、"
            "第一或保证效果。手机号、微信、二维码和外链必须服从目标渠道规则。"
            "资讯平台成稿不得批量复用同一标题结构、开场、段落顺序或结论；若现有"
            "事实不足以形成有独立信息价值的文章，应停止生成，不能用空话凑稿。"
            "标题必须先服务读者，不得把地区、品类、品牌、年龄和服务清单拼在一起。"
            "故事或案例只能使用已经确认的真实材料；没有案例时只能写一般场景，"
            "不得冒充学员、家长或消费者的真实经历。输出前先在内部逐项核对企业"
            "主张、数字、费用、标题、正文信息量、模板化表达、品牌次数和渠道限制；"
            "发现问题必须先直接改完，只返回通过全部硬约束的最终标题和正文。"
        ),
        editable=False,
    ),
    _seed(
        code="writer_base",
        category="base",
        name="文章通用写作规则",
        description="所有内容形式共用的自然表达、可读性和GEO基础规则。",
        text=(
            "围绕{{用户主问题}}写一篇可以直接发布的自然中文信息稿。第一段先给出"
            "有用回答，再用短段落和具体小标题展开；不要写“本文将、全面解析、"
            "深度揭秘、值得关注”等套话。自然建立企业名称、所在地区、主营业务和"
            "适用需求之间的关系，让读者和AI都能清楚识别“谁、在哪里、提供什么、"
            "适合什么情况”。标题或首段应自然回答{{用户主问题}}，允许使用与"
            "{{主关键词}}相同语义的自然表达，不要求逐字复现；地区、服务对象和"
            "核心业务必须清楚。完整关键词仅在语句自然时出现，全文通常不超过三次，"
            "不连续堆叠近义关键词。企业只作为有事实依据的本地示例出现，"
            "不写成硬广告，不默认推荐，不重复罗列优势。企业硬事实与行业通用建议"
            "分开表达：行业常识、不同年龄或场景的关注点可以合理补充，并使用"
            "“一般来说、通常、可关注、可以考虑”等措辞；不得把这些建议写成该企业"
            "已有的课程设置、教学安排或效果承诺。结尾给出实用的核验或咨询建议，"
            "不得讨论GEO、AI收录、关键词优化或文章生成过程。每篇只解决一个具体"
            "读者问题，并给出可执行步骤、容易忽略的边界或核验方法。企业名称全文"
            "通常出现1—3次，不得每段重复；不得套用“与其问哪家好，不如先看几个"
            "标准”“没有绝对最好”“先看这几点再决定”等批量稿模板。"
            "每篇同时给出3个不同方向的候选标题，优先从专业知识、真实生活场景、"
            "本地决策、自然问答、品牌核验中选择适合正文的方向。三条标题不能只"
            "替换同义词；关键词只作为选题依据，不要求逐字写进标题。正文以解决"
            "问题和提供专业信息为主，企业信息只作为可核验的本地例子自然出现，"
            "大部分篇幅用于专业方法、判断步骤、真实边界和核验建议，企业相关内容"
            "通常不超过正文约20%。不单设大段推销，不用报名、优惠、推荐或联系咨询"
            "作为结尾。生成完成后必须先执行事实、自然表达、关键词密度和目标平台规则"
            "自检，能安全修复的问题直接重写，不能把常规风险留给运营人员处理。"
            "企业数字和费用政策采用白名单：没有在可发布企业事实中明确出现的数字、"
            "数量、价格、免费或收费结论一律不写。资讯平台正文至少形成三个有信息"
            "增量的部分，标题与正文必须解决同一个具体问题。只输出一次成稿结果，"
            "不得输出草稿、检查表、修改说明或仍需调整的候选。"
        ),
        variables=["用户主问题", "主关键词", "关键词类型", "用户意图"],
    ),
    _seed(
        code="keyword_strategy",
        category="keyword_strategy",
        name="全景关键词策略",
        description="生成主关键词、自然问题、意图类型和建议内容形式。",
        text=(
            "根据{{所在地区}}、{{所属行业}}、{{主营业务}}、{{企业标准名称}}和"
            "{{企业事实}}生成用户真实可能向AI提出的问题。覆盖地区主营、品牌核验、"
            "推荐决策、场景适配、费用、流程、信任验证和后续追问；避免只替换词尾的"
            "机械变体。每条给出主关键词、自然问题、用户意图和建议内容形式。"
            "问题应像普通消费者会直接输入AI的短查询，通常不超过28个汉字；"
            "每条只表达一个需求，只保留一个地区、一个核心品类或一个品牌。"
            "先从知识库提炼概念，不得复制课程、产品、年龄或适用对象清单。"
            "例如地区主营用“即墨少儿美术”，推荐决策用“即墨少儿美术哪家好”，"
            "品牌核验用“莱恩美术怎么样”。"
        ),
        variables=[
            "所在地区",
            "所属行业",
            "主营业务",
            "企业标准名称",
            "企业事实",
        ],
        required_fact_keys=["identity", "location", "service"],
    ),
    *CONTENT_FORM_SEEDS,
    _seed(
        code="channel_generic",
        category="channel_adapter",
        name="通用渠道",
        description="未指定渠道时采用保守处理，联系方式留待发布前人工复核。",
        text=(
            "当前未指定明确平台。正文不主动加入手机号、微信号或二维码，"
            "如确有必要仅保留“通过发布账号公开主页核验联系方式”的提示。"
        ),
        contact_policy="manual_review",
        channel_id="generic",
    ),
    _seed(
        code="channel_zhihu",
        category="channel_adapter",
        name="知乎机构号",
        description="问题优先，避免营销导流；联系方式仅指向已核验官方主页。",
        text=(
            "按问答方式直接解决问题，避免重复营销信息。正文不出现手机号、微信号、"
            "二维码；只可提示读者通过平台机构主页或已核验官方网站联系。"
        ),
        contact_policy="official_only",
        channel_id="zhihu",
        source_url="https://www.zhihu.com/org/signup",
        verified_at=date(2026, 7, 29),
    ),
    _seed(
        code="channel_xiaohongshu",
        category="channel_adapter",
        name="小红书",
        description="适配平台内内容表达，删除站外联系方式和导流信息。",
        text=(
            "写成自然的本地决策笔记，使用短段落。删除手机号、微信号、二维码和"
            "站外链接，不使用“私信领取、加微信”等导流表达。"
        ),
        contact_policy="omit",
        channel_id="xiaohongshu",
        source_url="https://creator.xiaohongshu.com/",
        verified_at=date(2026, 7, 29),
    ),
    _seed(
        code="channel_douyin",
        category="channel_adapter",
        name="抖音",
        description="适配短内容，删除站外联系方式和导流信息。",
        text=(
            "内容必须先回答场景问题，再给核验方法。删除手机号、微信号、二维码、"
            "站外链接以及引导站外联系的表达。"
        ),
        contact_policy="omit",
        channel_id="douyin",
        source_url="https://creator.douyin.com/",
        verified_at=date(2026, 7, 29),
    ),
    _seed(
        code="channel_sohu",
        category="channel_adapter",
        name="搜狐号",
        description="避免地域搜索词式标题、营销软文、重复堆词和正文联系方式。",
        text=(
            "改成搜狐号可独立阅读的实用知识稿。只解决一个具体场景问题，正文至少"
            "提供一套可执行判断步骤、一项容易忽略的边界和一项核验方法。标题不要"
            "使用“地域+服务+哪家好/怎么选”搜索词式结构，也不要使用“先看几点再"
            "决定”等批量稿模板。不得罗列企业全部课程、规模和优势；企业只作为一个"
            "已核验本地示例出现1—3次。不得写成推荐、报名、预约、咨询、售卖或营销"
            "软文。删除手机号、微信号、二维码、外链和其他导流表达。"
            + platform_generation_instruction("sohu")
        ),
        contact_policy="omit",
        channel_id="sohu",
        source_url="https://mp.sohu.com/mpfe/v4/contentManagement/news/addarticle?contentStatus=1",
        verified_at=date(2026, 8, 10),
    ),
    _seed(
        code="channel_baijia",
        category="channel_adapter",
        name="百家号",
        description="强调事实准确和题文一致，删除推广联系方式与站外导流。",
        text=(
            "改成百家号可独立阅读的信息文章。标题与正文必须一致，不夸张、不虚构，"
            "不使用价格促销、排名或效果承诺。企业名称只在解释事实时出现，避免硬性推荐。"
            "删除手机号、微信号、二维码、公众号、第三方网址和引导联系表达。"
            + platform_generation_instruction("baijia")
        ),
        contact_policy="omit",
        channel_id="baijia",
        source_url="https://baijiahao.baidu.com/builder/rc/edit?type=news",
        verified_at=date(2026, 8, 10),
    ),
    _seed(
        code="channel_toutiao",
        category="channel_adapter",
        name="头条号",
        description="先提供用户价值，删除商业招揽、联系方式与联合推广式表达。",
        text=(
            "改成头条号原创信息图文，开头从一个具体生活场景直接进入，不用“与其"
            "问哪家好，不如先看几点”“没有绝对最好”等模板开场。文章必须给读者"
            "带来可执行方法、清楚边界或一手事实中的至少两类信息增量，不能只是改写"
            "企业介绍。正文至少85%用于专业知识、实用方法、真实观察或核验边界，"
            "至少形成3个有独立信息增量的内容部分。企业名称最多自然出现2次，不得"
            "罗列企业全部课程、规模、师资和优势。不得批量复用近期文章的标题角度、"
            "开头、段落顺序和结论，也不得只替换地区、品牌或关键词。不得写纯广告、"
            "推荐软文、商业招揽、课程促销、报名预约、到店试听、效果承诺或诱导私信。"
            "删除电话、微信、QQ、群、公众号、二维码、站外链接和其他导流表达。"
            + platform_generation_instruction("toutiao")
        ),
        contact_policy="omit",
        channel_id="toutiao",
        source_url="https://baike.toutiao.com/detail/236/238/0",
        verified_at=date(2026, 8, 10),
    ),
    _seed(
        code="channel_netease",
        category="channel_adapter",
        name="网易号",
        description="采用非营销知识稿，品牌仅作一次中性来源说明并删除全部转化表达。",
        text=(
            "改成网易号可独立阅读的专业知识、实用方法或真实观察稿。标题不得出现"
            "企业名称、品牌名称或搜索词堆砌。正文90%以上用于解决一个具体问题，"
            "不得围绕机构选择、课程推荐或消费转化展开。企业标准名称只在正文末尾"
            "用一句中性资料来源说明出现1次，不介绍其服务、课程、校区、优势或适合"
            "人群，也不得在后文用“该机构”“其课程”等称谓继续曝光。完全删除咨询、"
            "试听、到店、报名、预约、课程体系、服务范围、优惠福利、手机号、微信号、"
            "二维码、第三方网址、私信及其他广告、软文、推广和导流表达。不得使用"
            "AI改写拼接、模板化段落或同批相似结构。知识库没有权威依据时，不得编写"
            "精确训练时长、身体角度、尺寸、医学或儿童发育因果；改用可观察、可核验的"
            "一般方法。正文不得出现如何选择机构、老师或课程，不介绍课程周期，也不写"
            "报名上课建议。" + platform_generation_instruction("netease")
        ),
        contact_policy="omit",
        channel_id="netease",
        source_url="https://mp.163.com/college.html#/guidence/audit/regulations",
        verified_at=date(2026, 8, 10),
    ),
    _seed(
        code="channel_penguin",
        category="channel_adapter",
        name="企鹅号",
        description="采用可独立阅读的腾讯内容生态知识稿，删除导流并如实声明AI生成。",
        text=(
            "改成企鹅号可独立阅读的知识、经验或观察类文章。标题准确对应正文，"
            "不要使用标题党、搜索词堆砌、榜单排名、虚假效果承诺或批量稿模板。"
            "正文至少85%用于解决一个明确问题，提供可执行方法、真实观察或核验边界；"
            "企业名称只在说明知识库已确认事实时自然出现，不罗列全部服务和优势。"
            "完全删除手机号、微信号、QQ号、二维码、无关网址、关注、购买、私信及"
            "其他导流表达。不得虚构个人体验或原创过程；文章由模型生成时，发布页"
            "必须如实勾选AI生成声明。" + platform_generation_instruction("penguin")
        ),
        contact_policy="omit",
        channel_id="penguin",
        source_url="https://kf.om.qq.com/detail/f68d2d84-06be-4d6b-8058-6dfe83fb3693",
        verified_at=date(2026, 8, 10),
    ),
    _seed(
        code="channel_yidian",
        category="channel_adapter",
        name="一点号",
        description="采用非营销知识稿，删除全部导流和商业介绍，并如实声明 AI 生成。",
        text=(
            "改成一点号可独立阅读的知识、经验、案例观察或故事化场景文章。标题只写"
            "一个具体问题或结论，不得出现企业或品牌名称、特殊符号、标题党、搜索词"
            "堆砌或诱导点击表达。正文90%以上用于解决一个实际问题，至少提供3个具有"
            "不同信息增量的部分；不得复用近期文章的开头、段落顺序和结论，也不得只"
            "替换地区、品牌或关键词。企业标准名称只能在正文末尾“资料参考”句中出现"
            "1次，不介绍课程、服务、校区、业务或优势。完全删除广告、营销、推荐、"
            "报名、预约、咨询、试听、优惠、关注、点赞、转发、私信、手机号、微信、"
            "二维码、网址、站外链接和其他导流表达。不得虚构个人经历或原创过程；文章"
            "由模型生成时，发布页必须如实勾选“内容由AI生成”。"
            + platform_generation_instruction("yidian")
        ),
        contact_policy="omit",
        channel_id="yidian",
        source_url="https://mp.yidianzixun.com/static/opsspecs.html",
        verified_at=date(2026, 8, 10),
    ),
    _seed(
        code="channel_wechat",
        category="channel_adapter",
        name="微信公众号",
        description="适配公众号长文，发布前复核导流、外链和行业资质。",
        text=(
            "改成公众号长文，增加简短导读、清晰段落和核验清单。避免诱导分享、"
            "夸张标题、虚假承诺和伪装系统按钮；联系方式和外链发布前按账号能力复核。"
        ),
        contact_policy="manual_review",
        channel_id="wechat",
    ),
    _seed(
        code="channel_bilibili",
        category="channel_adapter",
        name="哔哩哔哩",
        description="强调知识价值，避免广告、过度营销和无关导流。",
        text=(
            "改成有实际知识价值的专栏或视频文稿，先解释方法、事实和限制，再少量说明"
            "企业示例。不要发布广告、过度营销、诱导点击或未经许可的互相推广；"
            "联系方式发布前人工复核。"
        ),
        contact_policy="manual_review",
        channel_id="bilibili",
        source_url="https://link.bilibili.com/h5/im/im-specification",
        verified_at=date(2026, 7, 29),
    ),
)
PROMPT_SEEDS_BY_CODE = {item["code"]: item for item in PROMPT_SEEDS}


class PromptTemplateUpdate(BaseModel):
    version: int = Field(ge=1)
    template_text: str = Field(min_length=2, max_length=12_000)
    active: bool = True
    contact_policy: ContactPolicy | None = None
    change_note: str = Field(min_length=2, max_length=300)


class PromptTemplateRestore(BaseModel):
    version: int = Field(ge=1)


def _template_data(template: PromptTemplate) -> dict[str, object]:
    return {
        "id": str(template.id),
        "code": template.code,
        "category": template.category,
        "name": template.name,
        "description": template.description,
        "template_text": template.template_text,
        "editable": template.editable,
        "active": template.active,
        "variable_keys": list(template.variable_keys or []),
        "required_fact_keys": list(template.required_fact_keys or []),
        "contact_policy": template.contact_policy,
        "default_contact_policy": template.default_contact_policy,
        "channel_id": template.channel_id,
        "source_url": template.source_url,
        "verified_at": (
            template.verified_at.isoformat() if template.verified_at is not None else None
        ),
        "current_version": template.current_version,
        "version": template.version,
        "updated_at": template.updated_at.isoformat(),
    }


def _version_data(version: PromptTemplateVersion) -> dict[str, object]:
    return {
        "id": str(version.id),
        "template_id": str(version.template_id),
        "version_number": version.version_number,
        "template_text": version.template_text,
        "contact_policy": version.contact_policy,
        "change_note": version.change_note,
        "created_at": version.created_at.isoformat(),
    }


def _validate_variables(template_text: str) -> None:
    variables = {item.strip() for item in VARIABLE_PATTERN.findall(template_text)}
    unknown = variables.difference(AVAILABLE_VARIABLES)
    if unknown:
        raise ApiFailure(
            status_code=422,
            code=42201,
            message=f"提示词包含未知变量：{'、'.join(sorted(unknown))}",
        )


async def ensure_prompt_templates(database: DatabaseSession) -> list[PromptTemplate]:
    existing = {
        item.code: item
        for item in (
            await database.scalars(
                select(PromptTemplate).order_by(
                    PromptTemplate.category,
                    PromptTemplate.name,
                ),
            )
        ).all()
    }
    created = False
    for seed in PROMPT_SEEDS:
        if seed["code"] in existing:
            continue
        template = PromptTemplate(
            code=seed["code"],
            category=seed["category"],
            name=seed["name"],
            description=seed["description"],
            template_text=seed["text"],
            default_text=seed["text"],
            editable=seed["editable"],
            active=True,
            variable_keys=seed["variables"],
            required_fact_keys=seed["required_fact_keys"],
            contact_policy=seed["contact_policy"],
            default_contact_policy=seed["default_contact_policy"],
            channel_id=seed["channel_id"],
            source_url=seed["source_url"],
            verified_at=seed["verified_at"],
            current_version=1,
            version=1,
        )
        database.add(template)
        await database.flush()
        database.add(
            PromptTemplateVersion(
                template_id=template.id,
                version_number=1,
                template_text=template.template_text,
                contact_policy=template.contact_policy,
                change_note="系统初始版本",
            ),
        )
        existing[template.code] = template
        created = True
    for code, template in existing.items():
        existing_seed = PROMPT_SEEDS_BY_CODE.get(code)
        if existing_seed is None:
            continue
        previous_default = template.default_text
        if previous_default != existing_seed["text"]:
            template.default_text = existing_seed["text"]
            if template.template_text == previous_default:
                template.template_text = existing_seed["text"]
                template.current_version += 1
                template.version += 1
                database.add(
                    PromptTemplateVersion(
                        template_id=template.id,
                        version_number=template.current_version,
                        template_text=template.template_text,
                        contact_policy=template.contact_policy,
                        change_note="系统默认提示词升级",
                    ),
                )
            created = True
        if template.default_contact_policy is None:
            template.default_contact_policy = existing_seed["default_contact_policy"]
            created = True
        metadata_updates = {
            "description": existing_seed["description"],
            "variable_keys": existing_seed["variables"],
            "required_fact_keys": existing_seed["required_fact_keys"],
            "channel_id": existing_seed["channel_id"],
            "source_url": existing_seed["source_url"],
            "verified_at": existing_seed["verified_at"],
        }
        for field_name, field_value in metadata_updates.items():
            if getattr(template, field_name) != field_value:
                setattr(template, field_name, field_value)
                created = True
    if created:
        try:
            await database.commit()
        except IntegrityError:
            await database.rollback()
    return list(
        (
            await database.scalars(
                select(PromptTemplate).order_by(
                    PromptTemplate.category,
                    PromptTemplate.name,
                ),
            )
        ).all(),
    )


async def _get_template(
    database: DatabaseSession,
    template_id: UUID,
) -> PromptTemplate:
    template = await database.get(PromptTemplate, template_id)
    if template is None:
        raise ApiFailure(status_code=404, code=40401, message="提示词模板不存在")
    return template


def build_prompt_templates_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/prompt-templates", tags=["prompt-templates"])

    @router.get("")
    async def list_prompt_templates(
        request: Request,
        database: DatabaseSession,
        authentication: Authenticated,
        category: Annotated[PromptCategory | None, Query()] = None,
    ) -> Response:
        del authentication
        templates = await ensure_prompt_templates(database)
        if category is not None:
            templates = [item for item in templates if item.category == category]
        return success_response(
            request,
            {
                "items": [_template_data(item) for item in templates],
                "available_variables": list(AVAILABLE_VARIABLES),
                "guardrails": {
                    "editable": False,
                    "summary": (
                        "系统保护层禁止编造企业事实、输出UUID等内部标记，"
                        "并强制执行渠道联系方式规则。"
                    ),
                },
            },
        )

    @router.get("/{template_id}/versions")
    async def list_prompt_template_versions(
        request: Request,
        template_id: UUID,
        database: DatabaseSession,
        authentication: Authenticated,
    ) -> Response:
        del authentication
        await _get_template(database, template_id)
        versions = (
            await database.scalars(
                select(PromptTemplateVersion)
                .where(PromptTemplateVersion.template_id == template_id)
                .order_by(PromptTemplateVersion.version_number.desc()),
            )
        ).all()
        return success_response(
            request,
            {"items": [_version_data(item) for item in versions]},
        )

    @router.patch("/{template_id}")
    async def update_prompt_template(
        request: Request,
        template_id: UUID,
        payload: PromptTemplateUpdate,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        del authentication
        template = await _get_template(database, template_id)
        if not template.editable:
            raise ApiFailure(
                status_code=422,
                code=42201,
                message="系统保护层为只读提示词，不能编辑",
            )
        if template.version != payload.version:
            raise ApiFailure(
                status_code=409,
                code=40901,
                message="提示词已被更新，请刷新后重试",
            )
        _validate_variables(payload.template_text)
        if payload.contact_policy is not None and template.category != "channel_adapter":
            raise ApiFailure(
                status_code=422,
                code=42201,
                message="只有渠道适配模板可以设置联系方式规则",
            )
        template.template_text = payload.template_text.strip()
        template.active = payload.active
        contact_policy_changed = (
            payload.contact_policy is not None and payload.contact_policy != template.contact_policy
        )
        if payload.contact_policy is not None:
            template.contact_policy = payload.contact_policy
        if contact_policy_changed:
            template.source_url = None
            template.verified_at = None
        template.current_version += 1
        template.version += 1
        database.add(
            PromptTemplateVersion(
                template_id=template.id,
                version_number=template.current_version,
                template_text=template.template_text,
                contact_policy=template.contact_policy,
                change_note=payload.change_note.strip(),
            ),
        )
        try:
            await database.commit()
        except IntegrityError as error:
            await database.rollback()
            raise ApiFailure(
                status_code=409,
                code=40901,
                message="提示词已被更新，请刷新后重试",
            ) from error
        await database.refresh(template)
        return success_response(request, _template_data(template))

    @router.post("/{template_id}/restore")
    async def restore_prompt_template(
        request: Request,
        template_id: UUID,
        payload: PromptTemplateRestore,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        del authentication
        template = await _get_template(database, template_id)
        if not template.editable:
            raise ApiFailure(
                status_code=422,
                code=42201,
                message="系统保护层为只读提示词，不能恢复",
            )
        if template.version != payload.version:
            raise ApiFailure(
                status_code=409,
                code=40901,
                message="提示词已被更新，请刷新后重试",
            )
        template.template_text = template.default_text
        template.active = True
        seed = PROMPT_SEEDS_BY_CODE.get(template.code)
        template.contact_policy = (
            seed["default_contact_policy"] if seed is not None else template.default_contact_policy
        )
        template.source_url = seed["source_url"] if seed is not None else None
        template.verified_at = seed["verified_at"] if seed is not None else None
        template.current_version += 1
        template.version += 1
        database.add(
            PromptTemplateVersion(
                template_id=template.id,
                version_number=template.current_version,
                template_text=template.template_text,
                contact_policy=template.contact_policy,
                change_note="恢复系统默认提示词",
            ),
        )
        try:
            await database.commit()
        except IntegrityError as error:
            await database.rollback()
            raise ApiFailure(
                status_code=409,
                code=40901,
                message="提示词已被更新，请刷新后重试",
            ) from error
        await database.refresh(template)
        return success_response(request, _template_data(template))

    return router
