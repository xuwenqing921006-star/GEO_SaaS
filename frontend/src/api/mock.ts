import type {
  ApiSuccess,
  ClientDetail,
  ClientSummary,
  ChannelData,
  ChannelRecommendationData,
  ConflictData,
  CreateClientInput,
  DashboardData,
  MonitoringBatchData,
  PlatformData,
  PromptTemplateData,
  PublishingChannelData,
  DiagnosticRunData,
  FactData,
  JobData,
  KnowledgeProfileData,
  MaterialData,
  SessionData,
  StrategyBundleData,
  StrategyItemData,
  SettingsData,
  ProviderSettingData,
  ProviderName,
} from "./dto";

const requestId = "00000000-0000-4000-8000-000000000001";
const mockLoginStateKey = "__geo_saas_dev_mock_authenticated";
const readMockLoginState = (): boolean => {
  try {
    return (
      typeof sessionStorage !== "undefined" &&
      sessionStorage.getItem(mockLoginStateKey) === "1"
    );
  } catch {
    return false;
  }
};
const writeMockLoginState = (loggedIn: boolean): void => {
  try {
    if (typeof sessionStorage === "undefined") return;
    if (loggedIn) sessionStorage.setItem(mockLoginStateKey, "1");
    else sessionStorage.removeItem(mockLoginStateKey);
  } catch {
    // Development Mock remains usable in memory when storage is unavailable.
  }
};
let isLoggedIn = readMockLoginState();

const session: SessionData = {
  user: {
    id: "00000000-0000-4000-8000-000000000010",
    username: "owner",
    display_name: "平台负责人",
  },
  csrf_token: "mock-csrf-token",
  expires_at: "2026-07-28T00:00:00Z",
};

const client: ClientDetail = {
  id: "00000000-0000-4000-8000-000000000101",
  standard_name: "莱恩美术",
  short_name: "莱恩",
  industry_code: "art_education",
  industry_name: "少儿美术",
  province: "山东省",
  city: "青岛市",
  district: "即墨区",
  status: "active",
  current_level: "L1",
  fact_completeness: 60,
  blocking_issue_count: 2,
  next_action: "补充服务范围",
  updated_at: "2026-07-27T00:00:00Z",
  version: 1,
  address: "待确认",
  contact_phone: null,
  contact_wechat: null,
  business_hours: null,
  service_radius: null,
  cooperation_started_on: "2026-01-01",
  notes: null,
  created_at: "2026-01-01T00:00:00Z",
};
const secondClient: ClientSummary = {
  ...client,
  id: "00000000-0000-4000-8000-000000000102",
  standard_name: "安心家政",
  short_name: "安心",
  industry_code: "housekeeping",
  industry_name: "家政服务",
};
let clients: ClientSummary[] = [client, secondClient];

const materials: MaterialData[] = [
  {
    id: "00000000-0000-4000-8000-000000000301",
    client_id: client.id,
    file_name: "莱恩美术服务说明.pdf",
    media_type: "application/pdf",
    size_bytes: 284_000,
    sha256: "mock-sha256-service",
    category: "service",
    authorization_status: "authorized",
    extraction_status: "succeeded",
    page_count: 4,
    fragment_count: 12,
    uploaded_at: "2026-07-20T08:00:00Z",
    file_url: null,
    version: 1,
  },
  {
    id: "00000000-0000-4000-8000-000000000302",
    client_id: client.id,
    file_name: "场地与师资资料.docx",
    media_type:
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    size_bytes: 198_000,
    sha256: "mock-sha256-team",
    category: "team",
    authorization_status: "restricted",
    extraction_status: "succeeded",
    page_count: 3,
    fragment_count: 8,
    uploaded_at: "2026-07-21T08:00:00Z",
    file_url: null,
    version: 1,
  },
];

const facts: FactData[] = [
  {
    id: "00000000-0000-4000-8000-000000000401",
    client_id: client.id,
    category: "identity",
    key: "standard_name",
    label: "机构标准名称",
    value: "莱恩美术",
    status: "confirmed",
    confidence: 100,
    valid_from: null,
    valid_until: null,
    evidence: [
      {
        id: "evidence-name",
        material_id: null,
        source_type: "manual",
        source_label: "客户确认",
        source_url: null,
        quote: "对外统一使用“莱恩美术”。",
        observed_at: "2026-07-20",
        authorization_status: "authorized",
      },
    ],
    version: 1,
    updated_at: "2026-07-20T08:00:00Z",
  },
  {
    id: "00000000-0000-4000-8000-000000000402",
    client_id: client.id,
    category: "service",
    key: "core_service",
    label: "核心服务",
    value: "少儿美术培训与创作课程",
    status: "confirmed",
    confidence: 92,
    valid_from: null,
    valid_until: null,
    evidence: [
      {
        id: "evidence-service",
        material_id: "00000000-0000-4000-8000-000000000301",
        source_type: "material",
        source_label: "莱恩美术服务说明.pdf 第 1 页",
        source_url: null,
        quote: "提供少儿美术培训与创作课程。",
        observed_at: "2026-07-20",
        authorization_status: "authorized",
      },
    ],
    version: 1,
    updated_at: "2026-07-20T08:00:00Z",
  },
  {
    id: "00000000-0000-4000-8000-000000000403",
    client_id: client.id,
    category: "audience",
    key: "target_audience",
    label: "适合人群",
    value: "待客户确认具体年龄段与基础要求",
    status: "client_provided",
    confidence: 58,
    valid_from: null,
    valid_until: null,
    evidence: [
      {
        id: "evidence-audience",
        material_id: "00000000-0000-4000-8000-000000000301",
        source_type: "material",
        source_label: "莱恩美术服务说明.pdf 第 2 页",
        source_url: null,
        quote: "面向少儿提供艺术学习服务。",
        observed_at: "2026-07-20",
        authorization_status: "not_authorized",
      },
    ],
    version: 1,
    updated_at: "2026-07-20T08:00:00Z",
  },
  {
    id: "00000000-0000-4000-8000-000000000404",
    client_id: client.id,
    category: "location",
    key: "service_radius",
    label: "服务范围",
    value: "待确认",
    status: "inferred",
    confidence: 35,
    valid_from: null,
    valid_until: null,
    evidence: [],
    version: 1,
    updated_at: "2026-07-21T08:00:00Z",
  },
];

const conflicts: ConflictData[] = [
  {
    id: "00000000-0000-4000-8000-000000000501",
    client_id: client.id,
    fact_key: "service_radius",
    label: "服务范围",
    candidates: [
      {
        value: "即墨区",
        source_label: "服务说明",
        evidence_id: "evidence-service",
      },
      { value: "青岛市", source_label: "客户口述", evidence_id: null },
    ],
    status: "open",
    resolved_value: null,
    resolution_note: null,
    version: 1,
  },
];

const knowledgeProfile: KnowledgeProfileData = {
  client_id: client.id,
  services: [
    {
      id: "service-art",
      name: "少儿美术培训与创作课程",
      description: "以客户确认资料为准的线下艺术学习服务。",
      target_audience: "待确认年龄段与基础要求",
      price_statement: null,
      limitations: ["不使用未经确认的师资、班额或效果承诺"],
      active: true,
    },
  ],
  capabilities: [
    {
      id: "capability-1",
      type: "service",
      title: "创作课程服务",
      description: "已由服务说明材料支持。",
      evidence_ids: ["evidence-service"],
      authorization_status: "authorized",
    },
  ],
  prohibited_claims: [
    {
      id: "claim-1",
      phrase: "最专业、保证提升、全市第一",
      reason: "缺少可验证依据，且属于结果承诺或绝对化表达。",
      source: "system",
    },
  ],
  external_presences: [],
  missing_questions: [
    {
      id: "missing-radius",
      field_key: "service_radius",
      question: "主要服务即墨区、青岛市，还是其他范围？",
      reason: "地区 + 服务查询需要明确服务半径。",
      blocking: false,
    },
    {
      id: "missing-audience",
      field_key: "target_audience",
      question: "适合哪些年龄段或学习基础？",
      reason: "用于生成场景与人群问题。",
      blocking: false,
    },
  ],
  version: 1,
};

const diagnostic: DiagnosticRunData = {
  id: "00000000-0000-4000-8000-000000000601",
  client_id: client.id,
  status: "succeeded",
  current_level: "L1",
  scores: {
    entity_completeness: 60,
    evidence_coverage: 55,
    content_coverage: 20,
    source_coverage: 15,
    ai_visibility: null,
  },
  scope: ["entity", "evidence", "content", "source", "visibility"],
  monitoring_window_days: 30,
  issues: [
    {
      id: "issue-radius",
      category: "entity",
      severity: "blocking",
      title: "服务范围尚未确认",
      explanation:
        "地区 + 服务的实体边界不完整，无法稳定关联即墨少儿美术需求。",
      evidence_ids: ["evidence-service"],
      suggested_action: "确认服务范围并用可公开证据支持。",
      target_page: "P02",
      status: "open",
      version: 1,
    },
    {
      id: "issue-source",
      category: "source",
      severity: "warning",
      title: "可引用公开来源不足",
      explanation: "当前可公开资料不足以支持平台理解机构服务与推荐理由。",
      evidence_ids: [],
      suggested_action: "补齐可公开的服务说明与实体资料。",
      target_page: "P04",
      status: "open",
      version: 1,
    },
  ],
  fact_snapshot_id: "00000000-0000-4000-8000-000000000701",
  is_stale: false,
  changed_fact_count: 0,
  completed_at: "2026-07-25T10:00:00Z",
};
const strategy: StrategyBundleData = {
  client_id: client.id,
  diagnostic_run_id: diagnostic.id,
  generated_at: "2026-07-26T08:00:00Z",
  version: 1,
  items: [
    {
      id: "q-discovery",
      kind: "question",
      text: "即墨少儿美术培训怎么选？",
      family: "discovery",
      keyword_type: null,
      provenance: "system_inference",
      target_level: "L2",
      priority: 1,
      rationale: "覆盖地区 + 服务发现问题，需用已确认实体事实回答。",
      locked: false,
      active: true,
      version: 1,
    },
    {
      id: "q-recommend",
      kind: "question",
      text: "即墨少儿美术培训推荐看哪些条件？",
      family: "recommendation",
      keyword_type: null,
      provenance: "system_inference",
      target_level: "L2",
      priority: 1,
      rationale: "先回答选择标准，不作无依据推荐承诺。",
      locked: true,
      active: true,
      version: 1,
    },
    {
      id: "q-scenario",
      kind: "question",
      text: "孩子刚开始接触美术，咨询前应确认哪些课程信息？",
      family: "scenario",
      keyword_type: null,
      provenance: "system_inference",
      target_level: "L2",
      priority: 2,
      rationale: "覆盖首次咨询场景，只列出需要向机构确认的信息。",
      locked: false,
      active: true,
      version: 1,
    },
    {
      id: "q-comparison",
      kind: "question",
      text: "即墨少儿美术培训机构比较时要看什么？",
      family: "comparison",
      keyword_type: null,
      provenance: "system_inference",
      target_level: "L2",
      priority: 2,
      rationale: "覆盖比较型提问，避免把未确认信息写成对比结论。",
      locked: false,
      active: true,
      version: 1,
    },
    {
      id: "q-brand-verification",
      kind: "question",
      text: "莱恩美术在即墨提供什么少儿美术服务？",
      family: "brand_verification",
      keyword_type: null,
      provenance: "client_provided",
      target_level: "L1",
      priority: 1,
      rationale: "用于验证机构名称、地区与核心服务能否被正确关联。",
      locked: false,
      active: true,
      version: 1,
    },
    {
      id: "kw-core",
      kind: "keyword",
      text: "即墨少儿美术",
      family: null,
      keyword_type: "core",
      provenance: "client_provided",
      target_level: "L2",
      priority: 1,
      rationale: "客户目标地区与核心服务组合；不是搜索量数据。",
      locked: false,
      active: true,
      version: 1,
    },
    {
      id: "kw-brand",
      kind: "keyword",
      text: "莱恩美术 即墨",
      family: null,
      keyword_type: "brand",
      provenance: "client_provided",
      target_level: "L1",
      priority: 2,
      rationale: "用于统一机构名称与地区关联。",
      locked: false,
      active: true,
      version: 1,
    },
    {
      id: "cluster-local-selection",
      kind: "cluster",
      text: "即墨少儿美术咨询与选择",
      family: null,
      keyword_type: null,
      provenance: "system_inference",
      target_level: "L2",
      priority: 1,
      rationale:
        "把发现、推荐、场景和比较问题组织为同一内容主题，而非堆砌关键词。",
      locked: false,
      active: true,
      version: 1,
    },
  ],
  briefs: [
    {
      id: "brief-entity",
      client_id: client.id,
      title: "莱恩美术：即墨少儿美术课程服务说明",
      content_type: "service_explainer",
      target_question_ids: ["q-discovery"],
      target_keywords: ["即墨少儿美术", "莱恩美术 即墨"],
      target_level: "L2",
      audience: "正在了解少儿美术培训的即墨家长",
      angle: "先明确机构、地区和服务边界，再说明适合人群与咨询前应确认的信息。",
      required_fact_ids: [
        "00000000-0000-4000-8000-000000000401",
        "00000000-0000-4000-8000-000000000402",
      ],
      required_evidence_ids: ["evidence-name", "evidence-service"],
      expected_recommendation_reason:
        "让回答可正确关联莱恩美术与少儿美术服务，不承诺推荐。",
      prohibited_claims: ["全市第一", "保证提升"],
      retest_questions: ["即墨少儿美术培训怎么选？"],
      suggested_channel_ids: ["zhihu", "sohu", "toutiao"],
      priority: 1,
      status: "planned",
      version: 1,
    },
  ],
};
const channels: ChannelData[] = [
  {
    id: "sohu",
    name: "搜狐号",
    official_url: "https://mp.sohu.com/",
    ownership: "operator_publishable",
    access: "public_web",
    cost: "free",
    ecosystem_tags: ["公开网页", "通用信源"],
    supported_content_types: ["企业事实", "服务指南", "FAQ"],
    client_requirements: ["授权企业资料"],
    risks: ["公开可访问性需逐篇核验"],
    verified_on: "2026-07-26",
    priority: "P0",
    active: true,
    contact_policy: "manual_review",
    contact_policy_label: "发布前人工复核",
    contact_policy_note: "默认不主动加入直接联系方式，发布前复核平台实时规则。",
  },
  {
    id: "toutiao",
    name: "头条号",
    official_url: "https://mp.toutiao.com/",
    ownership: "operator_publishable",
    access: "mixed",
    cost: "free",
    ecosystem_tags: ["字节内容生态"],
    supported_content_types: ["本地指南", "图文", "视频"],
    client_requirements: ["授权企业资料"],
    risks: ["不承诺被豆包引用"],
    verified_on: "2026-07-26",
    priority: "P0",
    active: true,
    contact_policy: "manual_review",
    contact_policy_label: "发布前人工复核",
    contact_policy_note: "默认不主动加入直接联系方式，发布前复核平台实时规则。",
  },
  {
    id: "baijia",
    name: "百家号",
    official_url: "https://baijiahao.baidu.com/",
    ownership: "operator_publishable",
    access: "public_web",
    cost: "free",
    ecosystem_tags: ["百度搜索", "百度 AI"],
    supported_content_types: ["企业事实", "服务说明", "FAQ"],
    client_requirements: ["授权企业资料"],
    risks: ["不得使用虚假评价或榜单"],
    verified_on: "2026-07-26",
    priority: "P0",
    active: true,
    contact_policy: "manual_review",
    contact_policy_label: "发布前人工复核",
    contact_policy_note: "默认不主动加入直接联系方式，发布前复核平台实时规则。",
  },
  {
    id: "maps",
    name: "地图与本地生活商户页",
    official_url: "https://map.baidu.com/",
    ownership: "client_required",
    access: "public_web",
    cost: "optional_paid",
    ecosystem_tags: ["本地实体", "地图生态"],
    supported_content_types: ["地址", "营业信息", "服务说明"],
    client_requirements: ["客户主体认证", "地址与电话核验"],
    risks: ["信息变更需由客户配合维护"],
    verified_on: "2026-07-26",
    priority: "P1",
    active: true,
    contact_policy: "allow",
    contact_policy_label: "可保留已核验联系方式",
    contact_policy_note: "仅使用企业知识库中已经确认的联系方式。",
  },
  {
    id: "local-media",
    name: "地方媒体投稿",
    official_url: "https://www.people.cn/",
    ownership: "partner_cooperation",
    access: "public_web",
    cost: "paid",
    ecosystem_tags: ["本地媒体", "第三方来源"],
    supported_content_types: ["服务案例", "本地专题"],
    client_requirements: ["真实素材与授权"],
    risks: ["合作价格与编辑规则需线下确认"],
    verified_on: "2026-07-26",
    priority: "P2",
    active: true,
    contact_policy: "manual_review",
    contact_policy_label: "发布前人工复核",
    contact_policy_note: "默认不主动加入直接联系方式，发布前复核平台实时规则。",
  },
];
const channelRecommendations: ChannelRecommendationData[] = channels
  .slice(0, 3)
  .map((channel, index) => ({
    id: `channel-rec-${channel.id}`,
    client_id: client.id,
    generation_id: "mock-channel-generation",
    brief_id: "brief-1",
    brief_title: "即墨少儿美术培训怎么选",
    brief_content_type: "selection_guide",
    content_document_id: null,
    channel,
    priority: index === 0 ? 1 : 2,
    fit_score: index === 0 ? 82 : 74,
    reasons: [
      "可承载地区 + 服务的可公开说明",
      "适合内容简报中的问答与服务说明",
    ],
    recommended_content_types: channel.supported_content_types,
    required_actions: channel.client_requirements,
    required_adaptation: "保留地区、服务和目标问题，并按渠道习惯调整段落。",
    account_positioning: "以即墨少儿美术服务指南定位的运营账号发布。",
    authorization_note: "引用的客户资料已获公开授权。",
    cost_note: channel.cost === "paid" ? "启用前确认预算。" : "基础发布免费。",
    risk_note: channel.risks.join("、"),
    target_ecosystems: channel.ecosystem_tags,
    catalog_version: "mock-2026.07",
    caveat: "能发布并不等于会被任何模型收录、引用或推荐。",
    generated_at: "2026-07-26T08:00:00Z",
  }));
const platforms: PlatformData[] = [
  {
    id: "deepseek",
    name: "DeepSeek",
    mode: "api",
    priority: "P0",
    provider: "deepseek",
    consumer_entry_url: "https://chat.deepseek.com/",
    sample_count_default: 3,
    active: true,
    verified_on: "2026-07-26",
    mode_label: "API 自动采样",
    note: "API 样本不等同于消费者端回答。",
  },
  {
    id: "qwen",
    name: "通义千问",
    mode: "api",
    priority: "P0",
    provider: "qwen",
    consumer_entry_url: "https://www.qianwen.com/",
    sample_count_default: 3,
    active: true,
    verified_on: "2026-07-26",
    mode_label: "API 自动采样",
    note: "API 样本不等同于消费者端回答。",
  },
  {
    id: "doubao",
    name: "豆包",
    mode: "api",
    priority: "P0",
    provider: "doubao",
    consumer_entry_url: "https://www.doubao.com/",
    sample_count_default: 3,
    active: true,
    verified_on: "2026-07-26",
    mode_label: "API 自动检测",
    note: "通过火山方舟 API 自动检测。",
  },
];
const monitoringBatch: MonitoringBatchData = {
  id: "monitoring-batch-1",
  client_id: client.id,
  question_set_id: "mock-question-set",
  question_set_version: 1,
  status: "partial",
  platform_ids: ["deepseek", "qwen", "doubao"],
  api_sample_count: 1,
  created_at: "2026-07-26T08:55:00Z",
  completed_at: "2026-07-26T09:15:00Z",
  samples: [
    {
      id: "sample-deepseek",
      batch_id: "monitoring-batch-1",
      platform_id: "deepseek",
      platform_name: "DeepSeek",
      collection_mode: "api",
      question_id: "question-recommendation",
      question_text: "即墨少儿美术培训推荐哪家？",
      question_family: "recommendation",
      is_brand_query: false,
      priority: 1,
      attempt: 1,
      status: "succeeded",
      raw_answer: "可以了解莱恩美术，并结合公开资料确认课程和服务范围。",
      asked_at: "2026-07-26T09:00:00Z",
      failure_reason: null,
      evaluation: {
        id: "evaluation-deepseek",
        sample_id: "sample-deepseek",
        brand_found: true,
        correctly_associated: true,
        recommended: true,
        recommendation_supported: null,
        facts_accurate: null,
        source_visible: false,
        mentioned_name: "莱恩美术",
        reasons: ["品牌被正确关联并进入推荐表达"],
        incorrect_facts: [],
        visible_sources: [],
        note: null,
        evaluator: "system",
        version: 1,
        updated_at: "2026-07-26T09:00:00Z",
      },
    },
    {
      id: "sample-qwen",
      batch_id: "monitoring-batch-1",
      platform_id: "qwen",
      platform_name: "通义千问",
      collection_mode: "api",
      question_id: "question-discovery",
      question_text: "即墨少儿美术培训怎么选？",
      question_family: "category_discovery",
      is_brand_query: false,
      priority: 1,
      attempt: 1,
      status: "succeeded",
      raw_answer: "莱恩美术位于即墨，可核对服务范围后再做选择。",
      asked_at: "2026-07-26T09:03:00Z",
      failure_reason: null,
      evaluation: {
        id: "evaluation-qwen",
        sample_id: "sample-qwen",
        brand_found: true,
        correctly_associated: true,
        recommended: false,
        recommendation_supported: null,
        facts_accurate: null,
        source_visible: false,
        mentioned_name: "莱恩美术",
        reasons: ["提及品牌但未形成推荐"],
        incorrect_facts: [],
        visible_sources: [],
        note: null,
        evaluator: "system",
        version: 1,
        updated_at: "2026-07-26T09:03:00Z",
      },
    },
    {
      id: "sample-doubao",
      batch_id: "monitoring-batch-1",
      platform_id: "doubao",
      platform_name: "豆包",
      collection_mode: "api",
      question_id: "question-comparison",
      question_text: "即墨少儿美术培训机构比较时要看什么？",
      question_family: "comparison",
      is_brand_query: false,
      priority: 2,
      attempt: 1,
      status: "succeeded",
      raw_answer: "可以比较课程、距离、价格和实际体验。",
      asked_at: "2026-07-26T09:10:00Z",
      failure_reason: null,
      evaluation: {
        id: "evaluation-doubao",
        sample_id: "sample-doubao",
        brand_found: false,
        correctly_associated: false,
        recommended: false,
        recommendation_supported: null,
        facts_accurate: null,
        source_visible: false,
        mentioned_name: null,
        reasons: ["回答中未发现客户名称"],
        incorrect_facts: [],
        visible_sources: [],
        note: null,
        evaluator: "system",
        version: 1,
        updated_at: "2026-07-26T09:10:00Z",
      },
    },
  ],
  summary: {
    sample_count: 3,
    effective_sample_count: 3,
    failed_count: 0,
    not_executed_count: 0,
    brand_found_rate: null,
    correct_association_rate: null,
    recommendation_rate: null,
    recommendation_supported_rate: null,
    fact_accuracy_rate: null,
    source_coverage_rate: null,
    repeat_appearance_rate: null,
    metric_details: {},
    mode_breakdown: {
      api: {
        sample_count: 2,
        effective_sample_count: 2,
        failed_count: 0,
        not_executed_count: 0,
        brand_found_rate: 100,
        correct_association_rate: 100,
        recommendation_rate: 50,
        recommendation_supported_rate: null,
        fact_accuracy_rate: null,
        source_coverage_rate: 0,
        repeat_appearance_rate: null,
        metric_details: {},
      },
      manual_consumer: {
        sample_count: 3,
        effective_sample_count: 1,
        failed_count: 1,
        not_executed_count: 1,
        brand_found_rate: 0,
        correct_association_rate: null,
        recommendation_rate: 0,
        recommendation_supported_rate: null,
        fact_accuracy_rate: null,
        source_coverage_rate: 0,
        repeat_appearance_rate: null,
        metric_details: {},
      },
    },
  },
};

let providerSettings: ProviderSettingData[] = [
  {
    provider: "deepseek",
    enabled: true,
    base_url: "https://api.deepseek.com/v1",
    workspace_id: null,
    writer_model: "doubao-seed-2-0-lite-260215",
    reviewer_model: "deepseek-v4-pro",
    fallback_model: "deepseek-v4-flash",
    daily_budget_cny_fen: 3_000,
    timeout_seconds: 45,
    secret_configured: true,
    secret_mask: "••••7K2Q",
    last_tested_at: "2026-08-05T10:00:00Z",
    last_test_status: "success",
    version: 1,
  },
  {
    provider: "qwen",
    enabled: false,
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    workspace_id: null,
    writer_model: "qwen3.7-plus",
    reviewer_model: null,
    fallback_model: null,
    daily_budget_cny_fen: 3_000,
    timeout_seconds: 45,
    secret_configured: false,
    secret_mask: null,
    last_tested_at: null,
    last_test_status: "not_tested",
    version: 1,
  },
  {
    provider: "doubao",
    enabled: false,
    base_url: "https://ark.cn-beijing.volces.com/api/v3",
    workspace_id: null,
    writer_model: null,
    reviewer_model: null,
    fallback_model: null,
    daily_budget_cny_fen: 3_000,
    timeout_seconds: 60,
    secret_configured: false,
    secret_mask: null,
    last_tested_at: null,
    last_test_status: "not_tested",
    version: 1,
  },
  {
    provider: "wenxin",
    enabled: false,
    base_url: "https://qianfan.baidubce.com/v2",
    workspace_id: null,
    writer_model: "ernie-4.5-turbo-32k",
    reviewer_model: null,
    fallback_model: null,
    daily_budget_cny_fen: 3_000,
    timeout_seconds: 60,
    secret_configured: false,
    secret_mask: null,
    last_tested_at: null,
    last_test_status: "not_tested",
    version: 1,
  },
];
let runtimeSettings: SettingsData["runtime"] = {
  timezone: "Asia/Shanghai",
  max_upload_mb: 30,
  max_upload_files: 20,
  job_retry_limit: 3,
  job_poll_seconds: 2,
  default_client_monthly_budget_cny_fen: 30_000,
  version: 1,
};

const publishingChannelSpecs: Array<
  [PublishingChannelData["id"], string, string]
> = [
  ["toutiao", "头条号", "今日头条创作者平台"],
  ["baijia", "百家号", "百度内容创作平台"],
  ["netease", "网易号", "网易媒体开放平台"],
  ["sohu", "搜狐号", "搜狐内容创作平台"],
  ["penguin", "企鹅号", "腾讯内容开放平台"],
  ["yidian", "一点号", "一点资讯创作平台"],
];
const publishingChannels: PublishingChannelData[] = publishingChannelSpecs.map(
  ([id, name, description]) => ({
    id,
    name,
    description,
    official_url: "https://example.com",
    login_url:
      id === "netease"
        ? "https://mp.163.com/"
        : id === "yidian"
          ? "https://mp.yidianzixun.com/"
          : id === "penguin"
            ? "https://om.qq.com/"
            : "https://example.com/login",
    manage_url: "https://example.com/manage",
    implementation_status: "available",
    generation_spec: {
      channel_id: id,
      channel_name: name,
      title_min_characters: id === "baijia" ? 2 : 5,
      title_max_characters: id === "toutiao" ? 100 : id === "sohu" ? 72 : 64,
      generation_title_max_characters: id === "yidian" ? 30 : 38,
      minimum_body_characters: 600,
      summary_max_characters: id === "sohu" ? 120 : null,
      daily_publication_limit: id === "penguin" ? 5 : null,
      content_requirements: [
        "标题与正文一致，正文提供真实信息增量并避免硬性推广。",
      ],
      image_requirements: {
        cover_width: 1200,
        cover_height: id === "netease" ? 900 : id === "baijia" ? 800 : 675,
        maximum_bytes: 5 * 1024 * 1024,
        allowed_formats: ["JPEG", "PNG"],
        target_body_images:
          id === "netease" || id === "yidian" ? 3 : id === "sohu" ? 1 : 2,
        minimum_body_images:
          id === "netease" || id === "yidian" ? 3 : id === "sohu" ? 1 : 0,
        maximum_body_images:
          id === "netease" || id === "yidian" ? 3 : id === "sohu" ? 1 : 2,
        requirement: "图片必须清晰、与正文直接相关且不包含站外导流信息。",
        cover_source: id === "penguin" ? "body" : "upload",
      },
      verified_at: "2026-08-10",
      source_urls: ["https://example.com"],
    },
    can_configure: true,
    max_accounts: 5,
    account_count: 0,
    connected_count: 0,
    enabled_count: 0,
    attention_count: 0,
    accounts: [],
  }),
);
const promptTemplates: PromptTemplateData[] = [
  {
    id: "mock-content-form-selection-guide",
    code: "selection_guide",
    category: "content_form",
    name: "选择指南",
    description: "围绕真实选择问题给出客观、可执行的信息。",
    template_text: "根据企业事实回答用户问题，不虚构、不堆砌关键词。",
    editable: true,
    active: true,
    variable_keys: ["enterprise_facts", "keyword", "user_intent"],
    required_fact_keys: ["standard_name", "core_service"],
    contact_policy: null,
    default_contact_policy: null,
    channel_id: null,
    source_url: null,
    verified_at: "2026-08-05T00:00:00Z",
    current_version: 1,
    version: 1,
    updated_at: "2026-08-05T00:00:00Z",
  },
];

const mockJobs = new Map<string, JobData>();
const acceptedJob = (
  clientId: string,
  type: "diagnostic" | "strategy_generate",
  resourceType: "diagnostic" | "strategy",
): Response => {
  const id = crypto.randomUUID();
  mockJobs.set(id, {
    id,
    client_id: clientId,
    type,
    status: "succeeded",
    progress: 100,
    current_step: "已完成",
    attempt: 1,
    max_attempts: 3,
    error_message: null,
    retryable: false,
  });
  return new Response(
    JSON.stringify({
      code: 202,
      message: "accepted",
      data: {
        job_id: id,
        status: "queued",
        progress: 0,
        resource_type: resourceType,
        resource_id: null,
      },
      request_id: requestId,
    }),
    { status: 202, headers: { "Content-Type": "application/json" } },
  );
};

const success = <T>(data: T, code: 200 | 201 = 200): ApiSuccess<T> => ({
  code,
  message: code === 201 ? "created" : "success",
  data,
  request_id: requestId,
});
const failure = (
  message: string,
  status: number,
  code = status === 409 ? 40901 : 40101,
): Response =>
  new Response(
    JSON.stringify({
      code,
      message,
      data: {
        field_errors: [],
        retryable: false,
        provider: null,
        job_id: null,
      },
      request_id: requestId,
    }),
    { status, headers: { "Content-Type": "application/json" } },
  );

export const mockRequest = async (
  path: string,
  init: RequestInit,
): Promise<Response> => {
  const requestUrl = new URL(path, "http://mock.local");
  const pathname = requestUrl.pathname;
  if (path === "/api/v1/auth/session" && init.method === "GET")
    return isLoggedIn
      ? json(success(session))
      : failure("登录已失效，请重新登录", 401);
  if (path === "/api/v1/auth/login" && init.method === "POST") {
    isLoggedIn = true;
    writeMockLoginState(true);
    return json(success(session));
  }
  if (path === "/api/v1/auth/session" && init.method === "DELETE") {
    isLoggedIn = false;
    writeMockLoginState(false);
    return json(success({ logged_out: true }));
  }
  if (path === "/api/v1/auth/password" && init.method === "PUT") {
    isLoggedIn = false;
    writeMockLoginState(false);
    return json(success({ changed: true, relogin_required: true }));
  }
  if (path === "/api/v1/settings" && init.method === "GET")
    return json(
      success({
        providers: providerSettings,
        runtime: runtimeSettings,
        catalogs: {
          provider_catalog_version: "2026-07-27",
          model_policy_version: "v1",
        },
      }),
    );
  if (pathname === "/api/v1/prompt-templates" && init.method === "GET")
    return json(
      success({
        items: promptTemplates,
        available_variables: ["enterprise_facts", "keyword", "user_intent"],
        guardrails: {
          editable: false,
          summary: "企业事实边界与平台合规规则始终生效。",
        },
      }),
    );
  if (pathname === "/api/v1/publishing/channels" && init.method === "GET")
    return json(success({ items: publishingChannels }));
  const documentsRoute = pathname.match(
    /^\/api\/v1\/clients\/([^/]+)\/documents$/,
  );
  if (documentsRoute && init.method === "GET")
    return json(success({ items: [], page: 1, page_size: 100, total: 0 }));
  if (path === "/api/v1/settings/runtime" && init.method === "PATCH") {
    const input = JSON.parse(String(init.body)) as {
      version: number;
      default_client_monthly_budget_cny_fen: number;
    };
    if (input.version !== runtimeSettings.version)
      return failure("运行设置已被更新，请刷新后重试", 409, 40901);
    runtimeSettings = {
      ...runtimeSettings,
      default_client_monthly_budget_cny_fen:
        input.default_client_monthly_budget_cny_fen,
      version: runtimeSettings.version + 1,
    };
    return json(success(runtimeSettings));
  }
  const providerRoute = path.match(
    /^\/api\/v1\/settings\/providers\/(qwen|deepseek|doubao|wenxin)$/,
  );
  if (providerRoute && init.method === "PUT") {
    const provider = providerRoute[1] as ProviderName;
    const current = providerSettings.find((item) => item.provider === provider);
    const input = JSON.parse(String(init.body)) as {
      version: number;
      enabled: boolean;
      base_url: string;
      workspace_id: string | null;
      writer_model: string | null;
      reviewer_model: string | null;
      fallback_model: string | null;
      daily_budget_cny_fen: number;
      timeout_seconds: number;
      api_key: string | null;
    };
    if (!current || current.version !== input.version)
      return failure("模型配置已被更新，请刷新后重试", 409, 40901);
    if (input.enabled && !input.api_key && !current.secret_configured)
      return failure("启用真实模型前必须先配置 API 密钥", 422, 42201);
    const updated: ProviderSettingData = {
      ...current,
      enabled: input.enabled,
      base_url: input.base_url,
      workspace_id: input.workspace_id,
      writer_model: input.writer_model,
      reviewer_model: input.reviewer_model,
      fallback_model: input.fallback_model,
      daily_budget_cny_fen: input.daily_budget_cny_fen,
      timeout_seconds: input.timeout_seconds,
      secret_configured: Boolean(input.api_key) || current.secret_configured,
      secret_mask: input.api_key
        ? `••••${input.api_key.slice(-4)}`
        : current.secret_mask,
      last_test_status: input.api_key ? "not_tested" : current.last_test_status,
      last_tested_at: input.api_key ? null : current.last_tested_at,
      version: current.version + 1,
    };
    providerSettings = providerSettings.map((item) =>
      item.provider === provider ? updated : item,
    );
    return json(success(updated));
  }
  const providerTestRoute = path.match(
    /^\/api\/v1\/settings\/providers\/(qwen|deepseek|doubao|wenxin)\/test$/,
  );
  if (providerTestRoute && init.method === "POST")
    return failure(
      "当前为开发 Mock，未调用真实模型，不能标记连接成功",
      503,
      50301,
    );
  if (path === "/api/v1/clients" && init.method === "POST") {
    const input = JSON.parse(String(init.body)) as CreateClientInput;
    const created: ClientDetail = {
      ...client,
      ...input,
      id: crypto.randomUUID(),
      industry_name: input.industry_code,
      version: 1,
    };
    clients = [created, ...clients];
    return json(success(created, 201), 201);
  }
  const diagnosticCreateRoute = path.match(
    /^\/api\/v1\/clients\/([^/]+)\/diagnostics$/,
  );
  if (diagnosticCreateRoute && init.method === "POST")
    return acceptedJob(
      diagnosticCreateRoute[1] ?? "",
      "diagnostic",
      "diagnostic",
    );
  const strategyCreateRoute = path.match(
    /^\/api\/v1\/clients\/([^/]+)\/strategy\/generate$/,
  );
  if (strategyCreateRoute && init.method === "POST")
    return acceptedJob(
      strategyCreateRoute[1] ?? "",
      "strategy_generate",
      "strategy",
    );
  const jobRoute = path.match(/^\/api\/v1\/jobs\/([^/]+)$/);
  if (jobRoute && init.method === "GET") {
    const job = mockJobs.get(jobRoute[1] ?? "");
    return job ? json(success(job)) : failure("任务不存在", 404, 40401);
  }
  const issueRoute = path.match(/^\/api\/v1\/diagnostic-issues\/([^/]+)$/);
  if (issueRoute && init.method === "PATCH") {
    const issue = diagnostic.issues.find((item) => item.id === issueRoute[1]);
    if (!issue) return failure("诊断问题不存在", 404, 40401);
    const input = JSON.parse(String(init.body)) as {
      version: number;
      status: "resolved" | "ignored";
    };
    if (input.version !== issue.version)
      return failure("诊断问题已被更新，请刷新后重试", 409, 40901);
    issue.status = input.status;
    issue.version += 1;
    return json(success(issue));
  }
  const strategyItemRoute = path.match(/^\/api\/v1\/strategy-items\/([^/]+)$/);
  if (strategyItemRoute && init.method === "PATCH") {
    const item = strategy.items.find(
      (value) => value.id === strategyItemRoute[1],
    );
    if (!item) return failure("策略项不存在", 404, 40401);
    const input = JSON.parse(String(init.body)) as {
      version: number;
      text?: string;
      main_keyword?: string;
      user_intent?: string;
      keyword_type?: StrategyItemData["keyword_type"];
      recommended_content_type?: StrategyItemData["recommended_content_type"];
      priority?: 1 | 2 | 3;
      locked?: boolean;
      selected?: boolean;
      active?: boolean;
    };
    if (input.version !== item.version)
      return failure("策略项已被更新，请刷新后重试", 409, 40901);
    if (input.text !== undefined) item.text = input.text;
    if (input.main_keyword !== undefined)
      item.main_keyword = input.main_keyword;
    if (input.user_intent !== undefined) item.user_intent = input.user_intent;
    if (input.keyword_type !== undefined)
      item.keyword_type = input.keyword_type;
    if (input.recommended_content_type !== undefined)
      item.recommended_content_type = input.recommended_content_type;
    if (input.priority !== undefined) item.priority = input.priority;
    if (input.locked !== undefined) item.locked = input.locked;
    if (input.selected !== undefined) item.selected = input.selected;
    if (input.active !== undefined) item.active = input.active;
    item.version += 1;
    return json(success(item));
  }
  const knowledgeRoute = pathname.match(
    /^\/api\/v1\/clients\/([^/]+)\/(materials|facts|conflicts|knowledge-profile|diagnostics\/latest)$/,
  );
  if (knowledgeRoute && init.method === "GET") {
    const [, clientId, resource] = knowledgeRoute;
    if (!clients.some((item) => item.id === clientId))
      return failure("客户不存在", 404, 40401);
    if (resource === "materials") {
      const items = materials.filter((item) => item.client_id === clientId);
      return json(
        success({
          items,
          total: items.length,
          page: 1,
          page_size: 100,
          has_next: false,
        }),
      );
    }
    if (resource === "facts") {
      const items = facts.filter((item) => item.client_id === clientId);
      return json(
        success({
          items,
          total: items.length,
          page: 1,
          page_size: 100,
          has_next: false,
        }),
      );
    }
    if (resource === "conflicts")
      return json(
        success({
          items: conflicts.filter((item) => item.client_id === clientId),
        }),
      );
    if (resource === "knowledge-profile")
      return json(
        success(
          clientId === client.id
            ? knowledgeProfile
            : {
                ...knowledgeProfile,
                client_id: clientId,
                services: [],
                capabilities: [],
                prohibited_claims: [],
                missing_questions: [
                  {
                    id: "missing-core",
                    field_key: "core_service",
                    question: "请先补充客户的核心服务。",
                    reason: "无法构建企业知识库。",
                    blocking: true,
                  },
                ],
              },
        ),
      );
    return json(success(clientId === client.id ? diagnostic : null));
  }
  const strategyRoute = path.match(/^\/api\/v1\/clients\/([^/]+)\/strategy$/);
  if (strategyRoute && init.method === "GET") {
    const clientId = strategyRoute[1];
    if (!clients.some((item) => item.id === clientId))
      return failure("客户不存在", 404, 40401);
    return json(success(clientId === client.id ? strategy : null));
  }
  if (path === "/api/v1/channels" && init.method === "GET")
    return json(success({ items: channels, catalog_version: "2026-07-26" }));
  const channelRecommendationRoute = path.match(
    /^\/api\/v1\/clients\/([^/]+)\/channel-recommendations$/,
  );
  if (channelRecommendationRoute && init.method === "GET") {
    const clientId = channelRecommendationRoute[1];
    if (!clients.some((item) => item.id === clientId))
      return failure("客户不存在", 404, 40401);
    return json(
      success({
        items: clientId === client.id ? channelRecommendations : [],
        generated_at: clientId === client.id ? "2026-07-26T08:00:00Z" : null,
      }),
    );
  }
  if (path === "/api/v1/monitoring/platforms" && init.method === "GET")
    return json(success({ items: platforms, catalog_version: "2026-07-26" }));
  const monitoringRoute = path.match(
    /^\/api\/v1\/clients\/([^/]+)\/monitoring-batches\/latest$/,
  );
  if (monitoringRoute && init.method === "GET") {
    const clientId = monitoringRoute[1];
    if (!clients.some((item) => item.id === clientId))
      return failure("客户不存在", 404, 40401);
    return json(success(clientId === client.id ? monitoringBatch : null));
  }
  if (path.startsWith("/api/v1/clients/") && path.endsWith("/dashboard")) {
    const clientId = path.split("/")[4];
    const current = clients.find((item) => item.id === clientId) ?? client;
    const data: DashboardData = {
      client: current,
      counts: {
        materials: 3,
        confirmed_facts: 3,
        unresolved_conflicts: 0,
        planned_contents: 0,
        draft_contents: 0,
        monitoring_samples_30d: 0,
      },
      level_progress: {
        current: "L1",
        next: "L2",
        missing_conditions: ["补充服务范围"],
      },
      next_actions: [
        {
          id: "00000000-0000-4000-8000-000000000201",
          title: "补充服务范围",
          reason: "当前服务半径尚未确认",
          target_level: "L2",
          target_page: "P02",
          priority: 1,
        },
      ],
      recent_jobs: [],
    };
    return json(success(data));
  }
  const lifecycle = path.match(
    /^\/api\/v1\/clients\/([^/]+)\/(archive|restore)$/,
  );
  if (lifecycle && init.method === "POST") {
    const [, clientId, action] = lifecycle;
    const body = JSON.parse(String(init.body)) as { version: number };
    const current = clients.find((item) => item.id === clientId);
    if (!current || current.version !== body.version)
      return failure("客户状态已变化，请刷新后重试", 409);
    const updated = {
      ...current,
      status: action === "archive" ? "archived" : "active",
      version: current.version + 1,
    } as ClientDetail;
    clients = clients.map((item) => (item.id === clientId ? updated : item));
    return json(success(updated));
  }
  const detail = path.match(/^\/api\/v1\/clients\/([^/]+)$/);
  if (detail && init.method === "GET") {
    const current = clients.find((item) => item.id === detail[1]);
    return current ? json(success(current)) : failure("客户不存在", 404, 40401);
  }
  if (detail && init.method === "PATCH") {
    const body = JSON.parse(String(init.body)) as Partial<CreateClientInput> & {
      version: number;
      status?: "active" | "paused";
    };
    const current = clients.find((item) => item.id === detail[1]);
    if (!current || current.version !== body.version)
      return failure("客户已更新，请刷新后重试", 409);
    const changes = Object.fromEntries(
      Object.entries(body).filter(([key]) => key !== "version"),
    );
    if (!Object.keys(changes).length)
      return failure("请提供至少一个可编辑字段", 400, 40001);
    const updated = {
      ...current,
      ...changes,
      version: current.version + 1,
    } as ClientDetail;
    clients = clients.map((item) => (item.id === detail[1] ? updated : item));
    return json(success(updated));
  }
  const url = new URL(path, window.location.origin);
  const query = url.searchParams.get("q")?.trim() ?? "";
  const status = url.searchParams.get("status") ?? "";
  const sort = url.searchParams.get("sort") ?? "-updated_at";
  const page = Math.max(1, Number(url.searchParams.get("page")) || 1);
  const pageSize = [10, 20, 50, 100].includes(
    Number(url.searchParams.get("page_size")),
  )
    ? Number(url.searchParams.get("page_size"))
    : 20;
  const filtered = query
    ? clients.filter((item) => item.standard_name.includes(query))
    : clients;
  const statusFiltered = status
    ? filtered.filter((item) => item.status === status)
    : filtered.filter((item) => item.status !== "archived");
  const sorted = [...statusFiltered].sort((left, right) =>
    sort === "standard_name"
      ? left.standard_name.localeCompare(right.standard_name, "zh-CN")
      : right.updated_at.localeCompare(left.updated_at),
  );
  const start = (page - 1) * pageSize;
  const items = sorted.slice(start, start + pageSize);
  return json(
    success({
      items,
      page,
      page_size: pageSize,
      total: sorted.length,
      has_next: start + pageSize < sorted.length,
    }),
  );
};

const json = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
