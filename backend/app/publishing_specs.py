# ruff: noqa: RUF001

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class PublishingImageSpec:
    cover_size: tuple[int, int]
    max_width: int
    max_height: int
    max_bytes: int
    allowed_formats: tuple[str, ...]
    target_body_images: int
    minimum_body_images: int
    maximum_body_images: int
    requirement: str
    cover_source: str = "upload"


@dataclass(frozen=True)
class PublishingPlatformSpec:
    channel_id: str
    name: str
    title_min_characters: int
    title_max_characters: int
    generation_title_max_characters: int
    minimum_body_characters: int
    summary_max_characters: int | None
    image: PublishingImageSpec
    content_requirements: tuple[str, ...]
    source_urls: tuple[str, ...]
    verified_at: date
    daily_publication_limit: int | None = None


PUBLISHING_PLATFORM_SPECS: dict[str, PublishingPlatformSpec] = {
    "toutiao": PublishingPlatformSpec(
        channel_id="toutiao",
        name="头条号",
        title_min_characters=5,
        title_max_characters=100,
        generation_title_max_characters=38,
        minimum_body_characters=600,
        summary_max_characters=None,
        image=PublishingImageSpec(
            cover_size=(1200, 675),
            max_width=4096,
            max_height=4096,
            max_bytes=8 * 1024 * 1024,
            allowed_formats=("JPEG", "PNG"),
            target_body_images=2,
            minimum_body_images=0,
            maximum_body_images=2,
            requirement="单图封面使用16:9高清图；配图必须清晰、与正文直接相关且增加信息量。",
        ),
        content_requirements=(
            "标题准确反映正文，不使用夸张、悬念、恐吓或误导式标题。",
            "一篇只解决一个具体读者问题，正文至少3个有独立信息增量的内容部分。",
            "不得批量发布重复、高度相似或只替换地区、品牌、关键词的低质内容，"
            "同批文章不得复用相同开头、段落顺序和结论。",
            "正文至少85%用于专业知识、实用方法、真实观察或核验边界；"
            "企业标准名称最多自然出现2次，不得罗列企业全部课程、规模和优势。",
            "不得写成纯广告、推荐软文或消费转化内容；禁止报名、预约、到店、试听、"
            "促销优惠、效果承诺及诱导私信联系。",
            "正文删除电话、微信、二维码、群、公众号、站外链接及其他导流信息。",
            "封面、正文图片和话题必须与文章主体一致。",
            "如发布页要求作品声明，必须按真实创作过程如实选择，不错标或漏标。",
        ),
        source_urls=(
            "https://baike.toutiao.com/detail/236/238/0",
            "https://baike.toutiao.com/detail/211/212/214",
        ),
        verified_at=date(2026, 8, 10),
    ),
    "sohu": PublishingPlatformSpec(
        channel_id="sohu",
        name="搜狐号",
        title_min_characters=5,
        title_max_characters=72,
        generation_title_max_characters=38,
        minimum_body_characters=600,
        summary_max_characters=120,
        image=PublishingImageSpec(
            cover_size=(1200, 675),
            max_width=4096,
            max_height=4096,
            max_bytes=8 * 1024 * 1024,
            allowed_formats=("JPEG", "PNG"),
            target_body_images=1,
            minimum_body_images=1,
            maximum_body_images=1,
            requirement="封面必须大于450×300、清晰且非GIF；正文准备1张相关企业图片。",
        ),
        content_requirements=(
            "标题与正文一致，不写搜索词拼接式标题或硬性推荐。",
            "摘要不超过120字，话题、属性和栏目必须与正文主题匹配。",
            "正文以经验教程、知识科普或观点评论为主，避免营销软文和站外导流。",
        ),
        source_urls=(
            "https://mp.sohu.com/mpfe/v4/contentManagement/news/addarticle?contentStatus=1",
            "https://mp.sohu.com/",
        ),
        verified_at=date(2026, 8, 10),
    ),
    "baijia": PublishingPlatformSpec(
        channel_id="baijia",
        name="百家号",
        title_min_characters=2,
        title_max_characters=64,
        generation_title_max_characters=38,
        minimum_body_characters=600,
        summary_max_characters=None,
        image=PublishingImageSpec(
            cover_size=(1200, 800),
            max_width=4096,
            max_height=4096,
            max_bytes=5 * 1024 * 1024,
            allowed_formats=("JPEG", "PNG"),
            target_body_images=2,
            minimum_body_images=0,
            maximum_body_images=2,
            requirement=("单图封面按3:2生成，使用JPG或PNG且不超过5MB；正文最多插入2张相关图片。"),
        ),
        content_requirements=(
            "标题保持2—64字且与正文一致，不夸张、不虚构、不做效果承诺。",
            "正文可独立解决一个问题，企业名称只在解释已确认事实时自然出现。",
            "按平台要求设置创作声明，不在正文输出联系方式、二维码或站外导流。",
        ),
        source_urls=(
            "https://baijiahao.baidu.com/builder/rc/edit?type=news",
            "https://baijiahao.baidu.com/",
        ),
        verified_at=date(2026, 8, 10),
    ),
    "netease": PublishingPlatformSpec(
        channel_id="netease",
        name="网易号",
        title_min_characters=5,
        # The current ordinary-account publisher renders a 5—64 character
        # limit (some media account types allow 80).  Keep the portable 64
        # character ceiling so the same generated article is safe for every
        # account connected to this product.
        title_max_characters=64,
        generation_title_max_characters=38,
        minimum_body_characters=600,
        summary_max_characters=None,
        image=PublishingImageSpec(
            # We deliberately use NetEase's single-cover mode.  Its live
            # publisher requires at least 336x252 (4:3); generating at 1200x900
            # avoids the previous 16:9 crop mismatch while retaining clarity.
            cover_size=(1200, 900),
            max_width=4096,
            max_height=4096,
            max_bytes=5 * 1024 * 1024,
            allowed_formats=("JPEG", "PNG"),
            target_body_images=3,
            minimum_body_images=3,
            maximum_body_images=3,
            requirement=(
                "单图封面使用4:3高清图且不低于336×252；正文固定插入3张"
                "与内容直接相关的图片（系统封面图1张、企业图片2张），"
                "满足发文助手的配图检测且避免堆砌图片。"
            ),
        ),
        content_requirements=(
            "只写可独立阅读的专业知识、实用方法或真实观察，标题不得出现企业或品牌名称。",
            "正文至少600个有效字符并有真实信息增量，不套模板、不拼接搜索词；"
            "不得生成AI改写、拼接、空洞水文或同批高度相似内容。",
            "企业标准名称只允许在正文末尾的中性资料来源说明中出现1次，不继续使用"
            "“该机构”“其课程”等替代称谓展开介绍。",
            "不写广告、软文、推广、推荐或转化话术；禁止咨询、试听、到店、校区、"
            "报名、预约、课程体系、服务范围、优惠福利、联系方式和站外导流。",
            "知识库没有权威依据时，不写精确训练时长、身体角度、尺寸、医学或儿童发育"
            "因果，改用可观察、可核验的一般方法。",
            "正文不写如何选择机构、老师或课程，不介绍课程周期，也不提供报名上课建议。",
            "封面和正文配图必须与文章主题一致，不自动声明原创或虚构。",
        ),
        source_urls=(
            "https://mp.163.com/#/article-publish",
            "https://mp.163.com/#/content-manage",
            "https://mp.163.com/college.html#/guidence/audit/regulations",
        ),
        verified_at=date(2026, 8, 10),
    ),
    "penguin": PublishingPlatformSpec(
        channel_id="penguin",
        name="企鹅号",
        title_min_characters=5,
        title_max_characters=64,
        generation_title_max_characters=38,
        minimum_body_characters=600,
        summary_max_characters=None,
        image=PublishingImageSpec(
            cover_size=(1200, 900),
            max_width=4096,
            max_height=4096,
            max_bytes=5 * 1024 * 1024,
            allowed_formats=("JPEG", "PNG"),
            target_body_images=2,
            minimum_body_images=2,
            maximum_body_images=3,
            requirement=(
                "正文使用2张与主题直接相关的真实企业图片；封面从正文图片中选择，"
                "候选图不低于360×270，不使用GIF、二维码、文字密集图或无关装饰图。"
            ),
            cover_source="body",
        ),
        content_requirements=(
            "标题保持5—64字并准确对应正文，不使用标题党、悬念误导或搜索词堆砌。",
            "正文以专业知识、经验方法或真实观察为主，至少解决一个明确问题，不批量复用模板。",
            "企业信息只用于解释知识库中已确认的事实，不写排名、效果承诺、硬性推荐或营销招揽。",
            "删除手机号、微信号、QQ号、二维码、无关网址和关注、购买、私信等导流表达。",
            "如文章由模型生成，发布时主动声明使用AI生成内容，不虚假勾选原创或个人经历。",
        ),
        source_urls=(
            "https://kf.om.qq.com/detail/6eaf254f-4693-4891-bfdd-d4085d26a8b3",
            "https://kf.om.qq.com/detail/81e0687c-4a23-425c-aa23-5858f914ca59",
            "https://kf.om.qq.com/detail/f68d2d84-06be-4d6b-8058-6dfe83fb3693",
            "https://kf.om.qq.com/detail/35537dd9-a4a8-1813-32e8-97f739f2bdb4",
        ),
        verified_at=date(2026, 8, 10),
        daily_publication_limit=5,
    ),
    "yidian": PublishingPlatformSpec(
        channel_id="yidian",
        name="一点号",
        # 普通创作者后台的精确标题上限需在已登录编辑器中逐账号核验。
        # 这里采用系统保守标题合同，而不是把 40 字表述为平台官方阈值。
        title_min_characters=5,
        title_max_characters=40,
        generation_title_max_characters=30,
        minimum_body_characters=600,
        summary_max_characters=None,
        image=PublishingImageSpec(
            # 编辑器封面比例待真实账号验证。先使用清晰、通用的资讯封面尺寸，
            # 只作为本地预处理默认值，不代表一点号官方规格。
            cover_size=(1200, 675),
            max_width=4096,
            max_height=4096,
            max_bytes=5 * 1024 * 1024,
            allowed_formats=("JPEG", "PNG"),
            target_body_images=3,
            minimum_body_images=3,
            maximum_body_images=3,
            requirement=(
                "系统按保守资讯图规格预处理封面；正文准备3张清晰、与内容直接相关的"
                "图片，避免二维码、联系方式、营销图和无关装饰图。真实编辑器字段"
                "验证完成前，不自动执行最终提交。"
            ),
        ),
        content_requirements=(
            "标题准确表达正文主题，不使用特殊符号、错别字、夸张诱导或标题党表达，"
            "也不在标题出现企业或品牌名称。",
            "正文只解决一个具体读者问题，至少形成3个有信息增量的内容部分；不得批量"
            "复用标题、开头、段落顺序或结论。",
            "正文90%以上用于专业知识、经验方法、案例观察或故事化场景；企业名称仅可"
            "在末尾中性资料参考中自然出现1次。",
            "不得写广告、营销、业务介绍、推荐软文、咨询、报名、预约、试听、优惠、"
            "关注互动或任何导流表达；删除手机号、微信、二维码、网址和站外链接。",
            "图文必须相关、排版清晰；图片型文章不少于3张相关图片。模型生成内容在"
            "发布页必须如实选择“内容由AI生成”，不自动声明原创。",
        ),
        source_urls=(
            "https://mp.yidianzixun.com/static/opsspecs.html",
            "https://mp.yidianzixun.com/static/user_protocol.html",
            "https://mp.yidianzixun.com/static/punishment.html",
        ),
        verified_at=date(2026, 8, 10),
    ),
}


def get_publishing_platform_spec(channel_id: str | None) -> PublishingPlatformSpec | None:
    if not channel_id:
        return None
    return PUBLISHING_PLATFORM_SPECS.get(channel_id)


def required_uploaded_body_images(spec: PublishingPlatformSpec) -> int:
    """Return how many enterprise images must exist before generation.

    NetEase reuses the generated editorial cover as the first body image.  Its
    three-image body contract therefore needs two uploaded enterprise images,
    while other platforms source every required body image from uploads.
    """

    generated_body_images = 1 if spec.channel_id in {"netease", "yidian"} else 0
    return max(0, spec.image.minimum_body_images - generated_body_images)


def platform_generation_instruction(channel_id: str) -> str:
    spec = PUBLISHING_PLATFORM_SPECS[channel_id]
    width, height = spec.image.cover_size
    content_rules = "；".join(spec.content_requirements)
    return (
        f"平台硬规格：标题{spec.title_min_characters}—{spec.title_max_characters}字，"
        f"本系统生成标题不超过{spec.generation_title_max_characters}字；"
        f"正文不少于{spec.minimum_body_characters}个有效字符。{content_rules}"
        f"发布素材将按{width}×{height}生成封面；{spec.image.requirement}"
        "不要在正文中输出图片占位符、尺寸说明或发布操作步骤。"
    )


def platform_prompt_contract(channel_id: str | None) -> dict[str, object] | None:
    spec = get_publishing_platform_spec(channel_id)
    if spec is None:
        return None
    return {
        "channel_id": spec.channel_id,
        "channel_name": spec.name,
        "title_min_characters": spec.title_min_characters,
        "title_max_characters": spec.title_max_characters,
        "generation_title_max_characters": spec.generation_title_max_characters,
        "minimum_body_characters": spec.minimum_body_characters,
        "summary_max_characters": spec.summary_max_characters,
        "content_requirements": list(spec.content_requirements),
        "image_requirements": {
            "cover_width": spec.image.cover_size[0],
            "cover_height": spec.image.cover_size[1],
            "maximum_bytes": spec.image.max_bytes,
            "allowed_formats": list(spec.image.allowed_formats),
            "target_body_images": spec.image.target_body_images,
            "minimum_body_images": spec.image.minimum_body_images,
            "maximum_body_images": spec.image.maximum_body_images,
            "requirement": spec.image.requirement,
            "cover_source": spec.image.cover_source,
        },
        "daily_publication_limit": spec.daily_publication_limit,
        "verified_at": spec.verified_at.isoformat(),
        "source_urls": list(spec.source_urls),
    }
