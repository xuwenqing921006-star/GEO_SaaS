# 接口契约

Status: 阶段 C 定稿  
版本：v1  
更新时间：2026-07-30

> 本文件是 Web Mock、前端 DTO、后端实现和契约测试的唯一对齐依据。任何字段或行为变更必须先修改本文件。

## 1. 通用约定

### 1.1 根路径与格式

- API 根路径：`/api/v1`
- JSON：`Content-Type: application/json; charset=utf-8`
- 上传：`multipart/form-data`
- 时间：UTC ISO 8601，例如 `2026-07-27T08:30:00Z`
- ID：UUID 字符串
- 金额：整数分，币种固定 `CNY`
- 可空字段明确写为 `null`；未声明可空的字段必须返回
- 客户业务资源不属于当前客户时统一返回 404，不暴露资源是否存在

### 1.2 成功包络

```ts
type Success<T> = {
  code: 200 | 201 | 202;
  message: "success" | "created" | "accepted";
  data: T;
  request_id: string;
};
```

### 1.3 错误包络

```ts
type FieldError = { field: string; message: string };
type ErrorData = {
  field_errors?: FieldError[];
  retryable: boolean;
  provider?: "deepseek" | "qwen" | null;
  job_id?: string | null;
};
type ErrorResponse = {
  code: number;
  message: string;
  data: ErrorData;
  request_id: string;
};
```

每个接口表中的错误代码使用以上完整结构。示例：

```json
{
  "code": 40001,
  "message": "参数校验失败",
  "data": {
    "field_errors": [
      {
        "field": "standard_name",
        "message": "企业标准名称不能为空"
      }
    ],
    "retryable": false,
    "provider": null,
    "job_id": null
  },
  "request_id": "7f37f99d-8db0-4a5b-92aa-d4eed9c6d3f2"
}
```

| HTTP | 业务代码 | 含义 |
|---:|---:|---|
| 400 | 40001 | 参数校验失败 |
| 400 | 40002 | 缺少幂等键 |
| 401 | 40101 | 未登录或会话失效 |
| 401 | 40102 | 用户名或密码错误 |
| 403 | 40301 | CSRF 校验失败 |
| 403 | 40302 | 操作被安全策略拒绝 |
| 404 | 40401 | 资源不存在 |
| 409 | 40901 | 版本冲突 |
| 409 | 40902 | 当前状态不允许操作 |
| 409 | 40903 | 相同幂等键对应不同请求 |
| 413 | 41301 | 文件数量或体积超过限制 |
| 415 | 41501 | 文件类型或签名不允许 |
| 422 | 42201 | 企业事实不足 |
| 422 | 42202 | 存在事实或合规阻断 |
| 429 | 42901 | 系统操作过于频繁 |
| 429 | 42902 | 模型日预算已达到上限 |
| 500 | 50001 | 系统内部错误 |
| 502 | 50201 | 外部模型返回异常 |
| 503 | 50301 | 依赖服务不可用 |
| 504 | 50401 | 外部模型调用超时 |

### 1.4 认证、CSRF 与版本

- 除 `/health/live`、`/health/ready`、`/auth/login` 外，均要求 `geo_session` HttpOnly Cookie。
- 登录成功同时返回 `csrf_token`；所有 POST、PATCH、PUT、DELETE 请求携带 `X-CSRF-Token`。
- 可编辑资源的更新体必须携带当前 `version`；成功后版本加一。
- Session 12 小时无操作过期，最长 7 天。

### 1.5 分页

```ts
type Page<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
};
```

默认 `page=1&page_size=20`，最大 `page_size=100`。排序参数格式为 `sort=-updated_at`，前缀 `-` 表示降序。

### 1.6 异步任务

解析、诊断、策略生成、内容操作、渠道推荐和监测批次必须携带 UUID 格式的 `Idempotency-Key`。

```ts
type JobAccepted = {
  job_id: string;
  status: "queued";
  progress: 0;
};

type PublicationBatchJobData = {
  job_id: string;
  status: "queued";
  progress: 0;
  account_id: string;
  account_name: string;
  channel_id: "toutiao" | "baijia" | "netease" | "sohu" | "penguin" | "yidian";
};

type PublicationBatchAccepted = {
  items: PublicationBatchJobData[];
  queued_count: number;
};
```

同一账号、客户、接口和幂等键的相同请求返回原任务；请求体不同返回 40903。前端每 2 秒查询任务，不因页面关闭取消。

## 2. 共享枚举

```ts
type ClientStatus = "active" | "paused" | "archived";
type FactStatus = "confirmed" | "client_provided" | "external_source" | "inferred" | "conflict" | "private";
type AuthorizationStatus = "authorized" | "restricted" | "not_authorized" | "not_required";
type ResultLevel = "L0" | "L1" | "L2" | "L3" | "L4";
type Severity = "info" | "warning" | "blocking";
type Provenance = "measured" | "client_provided" | "external_source" | "system_inference" | "ai_generated";
type QuestionFamily = "discovery" | "recommendation" | "scenario" | "comparison" | "brand_verification";
type ContentStatus = "brief" | "generating" | "draft" | "blocked" | "failed" | "checked" | "optimized" | "exported" | "published" | "archived";
type PlatformMode = "api" | "manual_consumer";
type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";
type CheckStatus = "passed" | "warning" | "blocked";
```

## 3. 共享响应数据结构

```ts
type SessionData = {
  user: { id: string; username: string; display_name: string };
  csrf_token: string;
  expires_at: string;
};

type ClientSummary = {
  id: string;
  standard_name: string;
  short_name: string | null;
  industry_code: string;
  industry_name: string;
  province: string;
  city: string;
  district: string;
  status: ClientStatus;
  current_level: ResultLevel;
  fact_completeness: number;
  blocking_issue_count: number;
  next_action: string;
  updated_at: string;
  version: number;
};

type ClientDetail = ClientSummary & {
  address: string;
  contact_phone: string | null;
  contact_wechat: string | null;
  business_hours: string | null;
  service_radius: string | null;
  cooperation_started_on: string;
  notes: string | null;
  created_at: string;
};

type DashboardData = {
  client: ClientSummary;
  counts: {
    materials: number;
    confirmed_facts: number;
    unresolved_conflicts: number;
    planned_contents: number;
    draft_contents: number;
    monitoring_samples_30d: number;
  };
  level_progress: {
    current: ResultLevel;
    next: ResultLevel | null;
    missing_conditions: string[];
  };
  next_actions: {
    id: string;
    title: string;
    reason: string;
    target_level: ResultLevel;
    target_page: "P02" | "P03" | "P04" | "P05" | "P06" | "P07";
    priority: 1 | 2 | 3;
  }[];
  recent_jobs: JobData[];
};

type MaterialData = {
  id: string;
  client_id: string;
  file_name: string;
  media_type: string;
  size_bytes: number;
  sha256: string;
  category: "license" | "service" | "price" | "team" | "case" | "channel" | "other" | "image";
  authorization_status: AuthorizationStatus;
  extraction_status: "not_started" | "queued" | "running" | "succeeded" | "failed";
  page_count: number | null;
  fragment_count: number;
  uploaded_at: string;
  file_url: string | null;
  version: number;
};

type EvidenceData = {
  id: string;
  material_id: string | null;
  source_type: "material" | "manual" | "public_url";
  source_label: string;
  source_url: string | null;
  quote: string;
  observed_at: string;
  authorization_status: AuthorizationStatus;
};

type FactData = {
  id: string;
  client_id: string;
  category: "identity" | "location" | "service" | "audience" | "price" | "process" | "capability" | "case" | "contact" | "restriction";
  key: string;
  label: string;
  value: string;
  status: FactStatus;
  confidence: number;
  valid_from: string | null;
  valid_until: string | null;
  evidence: EvidenceData[];
  version: number;
  updated_at: string;
};

type ConflictData = {
  id: string;
  client_id: string;
  fact_key: string;
  label: string;
  candidates: {
    value: string;
    source_label: string;
    evidence_id: string | null;
  }[];
  status: "open" | "resolved" | "ignored";
  resolved_value: string | null;
  resolution_note: string | null;
  version: number;
};

type KnowledgeProfileData = {
  client_id: string;
  services: {
    id: string;
    name: string;
    description: string;
    target_audience: string;
    price_statement: string | null;
    limitations: string[];
    active: boolean;
  }[];
  capabilities: {
    id: string;
    type: string;
    title: string;
    description: string;
    evidence_ids: string[];
    authorization_status: AuthorizationStatus;
  }[];
  prohibited_claims: {
    id: string;
    phrase: string;
    reason: string;
    source: "system" | "user";
  }[];
  external_presences: {
    id: string;
    platform: string;
    account_name: string;
    public_url: string;
    ownership: "operator" | "client" | "partner";
    verified_on: string;
  }[];
  missing_questions: {
    id: string;
    field_key: string;
    question: string;
    reason: string;
    blocking: boolean;
  }[];
  version: number;
};

type DiagnosticRunData = {
  id: string;
  client_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  current_level: ResultLevel;
  scope?: ("entity" | "evidence" | "content" | "source" | "visibility")[];
  monitoring_window_days?: number;
  scores: {
    entity_completeness: number | null;
    evidence_coverage: number | null;
    content_coverage: number | null;
    source_coverage: number | null;
    ai_visibility: number | null;
  };
  overall_score: number | null;
  overall_grade: "excellent" | "good" | "medium" | "poor" | null;
  evaluated_platform_count: number;
  total_platform_count: number;
  effective_sample_count: number;
  platform_results: {
    platform_id: string;
    platform_name: string;
    collection_mode: PlatformMode;
    status: "untested" | "failed" | "not_found" | "mentioned" | "associated" | "recommended";
    score: number | null;
    grade: "excellent" | "good" | "medium" | "poor" | null;
    comment: string;
    valid_sample_count: number;
    measured_at: string | null;
    metrics: {
      mention_rate: number | null;
      association_rate: number | null;
      recommendation_rate: number | null;
      accuracy_rate: number | null;
      stability_rate: number | null;
    };
  }[];
  issues: {
    id: string;
    category: "entity" | "evidence" | "content" | "source" | "visibility";
    severity: Severity;
    title: string;
    explanation: string;
    evidence_ids: string[];
    suggested_action: string;
    target_page: "P02" | "P04" | "P05" | "P06" | "P07";
    status: "open" | "resolved" | "ignored";
    version: number;
  }[];
  fact_snapshot_id: string;
  is_stale: boolean;
  changed_fact_count: number;
  completed_at: string | null;
};

type StrategyItemData = {
  id: string;
  kind: "keyword" | "question" | "cluster";
  text: string;
  family: QuestionFamily | null;
  keyword_type: "core" | "brand" | "decision" | "service" | "geo_longtail" | "local_service" | "recommendation" | "scenario" | "service_detail" | "comparison" | "transaction" | "trust" | null;
  provenance: Provenance;
  target_level: ResultLevel;
  priority: 1 | 2 | 3;
  rationale: string;
  main_keyword: string | null;
  user_intent: string | null;
  recommended_content_type: string | null;
  locked: boolean;
  selected: boolean;
  active: boolean;
  generated_count: number;
  version: number;
};

type ContentBriefData = {
  id: string;
  client_id: string;
  title: string;
  content_type: "local_recommendation" | "entity_profile" | "service_explainer" | "selection_guide" | "practical_guide" | "scenario_solution" | "faq" | "price_guide" | "service_process" | "comparison" | "case_study" | "local_presence" | "capability_proof" | "case" | "local_scenario";
  target_question_ids: string[];
  target_keywords: string[];
  target_level: ResultLevel;
  audience: string;
  angle: string;
  required_fact_ids: string[];
  required_evidence_ids: string[];
  expected_recommendation_reason: string;
  prohibited_claims: string[];
  retest_questions: string[];
  suggested_channel_ids: string[];
  priority: 1 | 2 | 3;
  status: "planned" | "in_production" | "completed" | "archived";
  keyword_strategy_id: string | null;
  keyword_type: string | null;
  prompt_template_code: string | null;
  prompt_template_version: number | null;
  target_channel_id: string | null;
  contact_policy: string | null;
  prompt_layers_snapshot: Record<string, unknown>[];
  contact_allowed_urls: string[];
  version: number;
};

type StrategyBundleData = {
  client_id: string;
  diagnostic_run_id: string | null;
  items: StrategyItemData[];
  briefs: ContentBriefData[];
  prompt_template_code: string | null;
  prompt_template_version: number | null;
  generated_at: string;
  version: number;
};

type KeywordProfileData = {
  primary_keyword: string;
  regions: string[];
  secondary_keywords: string[];
  keyword_types: ("local_service" | "brand" | "recommendation" | "scenario" | "service_detail" | "comparison" | "transaction" | "trust")[];
  recommended_count: number;
  knowledge_fingerprint: string;
  version: number;
  updated_at: string | null;
  inferred: boolean;
};

type KeywordCandidateData = {
  id: string;
  generation_id: string;
  text: string;
  normalized_text: string;
  main_keyword: string;
  keyword_type: "local_service" | "brand" | "recommendation" | "scenario" | "service_detail" | "comparison" | "transaction" | "trust";
  user_intent: string;
  region: string | null;
  secondary_keyword: string | null;
  recommended_content_type: string;
  priority: 1 | 2 | 3;
  selected: boolean;
  active: boolean;
  confirmed_item_id: string | null;
  version: number;
};

type KeywordGenerationData = {
  id: string;
  client_id: string;
  job_id: string | null;
  primary_keyword: string;
  regions: string[];
  secondary_keywords: string[];
  keyword_types: string[];
  target_count: number;
  status: "queued" | "running" | "awaiting_confirmation" | "confirmed" | "failed";
  generated_count: number;
  filtered_count: number;
  confirmed_count: number;
  error_message: string | null;
  archived: boolean;
  created_at: string;
  completed_at: string | null;
  confirmed_at: string | null;
  version: number;
  candidates?: KeywordCandidateData[] | null;
};

type ConfirmedKeywordData = {
  id: string;
  text: string;
  keyword_type: string | null;
  main_keyword: string | null;
  selected: boolean;
  active: boolean;
  version: number;
};

type KeywordWorkspaceData = {
  profile: KeywordProfileData;
  generations: KeywordGenerationData[];
  confirmed_keywords: ConfirmedKeywordData[];
};

type KeywordGenerationAcceptedData = {
  job_id: string;
  generation_id: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  progress: number;
};

type QualityCheckData = {
  id: string;
  document_version_id: string;
  overall_status: CheckStatus;
  dimensions: {
    key: "fact_consistency" | "question_relevance" | "entity_clarity" | "answer_extractability" | "source_traceability" | "natural_language" | "channel_fit" | "compliance";
    status: CheckStatus;
    score: number;
    explanation: string;
  }[];
  findings: {
    id: string;
    severity: Severity;
    category: string;
    message: string;
    paragraph_id: string | null;
    fact_id: string | null;
    suggested_fix: string;
  }[];
  provider: "deepseek" | "qwen" | "rules";
  model: string | null;
  created_at: string;
};

type DocumentVersionData = {
  id: string;
  document_id: string;
  version_number: number;
  title: string;
  body_markdown: string;
  change_type: "generated" | "manual_edit" | "geo_optimized" | "naturalized" | "regenerated" | "restored" | "channel_variant";
  provider: "deepseek" | "qwen" | "user" | "rules";
  model: string | null;
  fact_snapshot_id: string;
  prompt_version: string | null;
  prompt_template_code: string | null;
  prompt_template_version: number | null;
  target_channel_id: string | null;
  contact_policy: "allow" | "official_only" | "omit" | "manual_review" | null;
  prompt_layers_snapshot: Record<string, unknown>[];
  contact_allowed_urls: string[];
  contact_sanitization_report: Record<string, unknown>;
  image_material_ids: string[];
  input_tokens?: number;
  output_tokens?: number;
  fallback_reason?: string | null;
  created_at: string;
};

type DocumentData = {
  id: string;
  client_id: string;
  brief_id: string;
  generation_task_id: string | null;
  generation_task_confirmed_at: string | null;
  title: string;
  status: ContentStatus;
  generation_status: "pending" | "generating" | "generated" | "failed";
  publication_status: "unpublished" | "queued" | "publishing" | "pending_review" | "published" | "failed" | "needs_login" | "needs_verification" | "rejected";
  publication_error: string | null;
  keyword: string | null;
  keyword_type: string | null;
  current_version: DocumentVersionData | null;
  latest_check: QualityCheckData | null;
  fact_snapshot?: Record<string, unknown> | null;
  channel_variants: {
    id: string;
    channel_id: string;
    version_id: string;
    adaptation_note: string;
  }[];
  latest_publication: PublicationData | null;
  publications?: PublicationData[];
  current_version_published: boolean;
  updated_at: string;
  version: number;
};

type ContentGenerationTaskData = {
  id: string;
  client_id: string;
  platform_type: "self_media";
  keyword_snapshots: Record<string, unknown>[];
  channel_ids: string[];
  article_count_per_channel: number;
  length: "short" | "medium" | "long";
  content_form_codes: string[];
  total_count: number;
  completed_count: number;
  failed_count: number;
  progress: number;
  status: "queued" | "generating" | "completed" | "partial" | "failed";
  confirmed_at: string | null;
  created_at: string;
  version: number;
  documents?: DocumentData[];
};

type PublicationData = {
  id: string;
  document_version_id: string;
  channel_id: string | null;
  publishing_account_id?: string | null;
  account_name?: string | null;
  status: "queued" | "publishing" | "pending_review" | "published" | "failed" | "needs_login" | "needs_verification" | "rejected";
  public_url: string | null;
  error_message: string | null;
  submitted_at: string | null;
  published_at: string | null;
};

type DocumentsCreatedData = {
  task: ContentGenerationTaskData;
  items: DocumentData[];
  total: number;
};

type ChannelData = {
  id: string;
  name: string;
  official_url: string;
  ownership: "operator_publishable" | "client_required" | "partner_cooperation";
  access: "public_web" | "mostly_in_app" | "mixed";
  cost: "free" | "optional_paid" | "paid";
  ecosystem_tags: string[];
  supported_content_types: string[];
  client_requirements: string[];
  risks: string[];
  verified_on: string;
  priority: "P0" | "P1" | "P2";
  active: boolean;
  contact_policy: "allow" | "official_only" | "omit" | "manual_review";
  contact_policy_label: string;
  contact_policy_note: string;
};

type PublishingChannelData = {
  id: string;
  name: string;
  description: string;
  official_url: string;
  login_url: string;
  manage_url: string;
  implementation_status: "available";
  can_configure: boolean;
  max_accounts: 5;
  account_count: number;
  connected_count: number;
  enabled_count: number;
  attention_count: number;
  accounts: PublishingAccountData[];
};

type PublishingAccountData = {
  id: string;
  channel_id: "toutiao" | "baijia" | "netease" | "sohu" | "penguin" | "yidian";
  display_name: string;
  enabled: boolean;
  connection_status: "disconnected" | "awaiting_login" | "connected" | "needs_login" | "needs_verification" | "error";
  account_name: string | null;
  last_checked_at: string | null;
  last_error: string | null;
  session_health: "healthy" | "check_due_soon" | "check_due" | "awaiting_login" | "expired" | "verification_required" | "error" | "not_checked";
  session_health_label: string;
  session_health_message: string;
  next_automatic_check_at: string | null;
  automatic_check_interval_hours: 24;
  version: number;
  created_at: string;
  updated_at: string;
};

type PublishingChannelListData = {
  items: PublishingChannelData[];
};

type ChannelRecommendationData = {
  id: string;
  client_id: string;
  generation_id: string | null;
  brief_id: string | null;
  brief_title: string;
  brief_content_type: ContentBriefData["content_type"] | null;
  content_document_id: string | null;
  channel: ChannelData;
  priority: 1 | 2 | 3;
  fit_score: number;
  reasons: string[];
  recommended_content_types: string[];
  required_actions: string[];
  required_adaptation: string;
  account_positioning: string;
  authorization_note: string;
  cost_note: string;
  risk_note: string;
  target_ecosystems: string[];
  catalog_version: string;
  caveat: string;
  generated_at: string;
};

type PlatformData = {
  id: string;
  name: string;
  mode: PlatformMode;
  priority: "P0" | "P1";
  provider: "deepseek" | "qwen" | null;
  consumer_entry_url: string | null;
  sample_count_default: number;
  active: boolean;
  verified_on: string;
  mode_label?: string;
  note?: string;
};

type MonitoringQuestionData = {
  id: string;
  text: string;
  family: "category_discovery" | "recommendation" | "scenario" | "comparison" | "brand_verification";
  is_brand_query: boolean;
  expected_facts?: string[];
  target_level: "L1" | "L2" | "L3";
  priority?: number;
};

type QuestionInput = {
  id?: string | null;
  text: string;
  family: "category_discovery" | "recommendation" | "scenario" | "comparison" | "brand_verification";
  is_brand_query?: boolean;
  target_level?: "L1" | "L2" | "L3";
  priority?: number;
};

type ManualSampleInput = {
  sample_id: string;
  status: "succeeded" | "failed";
  raw_answer?: string | null;
  failure_reason?: string | null;
  asked_at: string;
};

type QuestionSetData = {
  id: string;
  client_id: string;
  name: string;
  frozen: boolean;
  questions: MonitoringQuestionData[];
  version: number;
  created_at?: string;
  updated_at: string;
};

type SuggestedMonitoringActionData = {
  action_type: "add_fact_task" | "add_content_brief" | "update_channel_priority" | "increase_sample";
  title: string;
  reason: string;
  target_level: "L1" | "L2" | "L3";
  target_page: "P02" | "P04" | "P06" | "P07";
};

type SampleEvaluationData = {
  id: string;
  sample_id: string;
  brand_found: boolean;
  correctly_associated: boolean;
  recommended: boolean;
  recommendation_supported: boolean | null;
  facts_accurate: boolean | null;
  source_visible: boolean;
  mentioned_name: string | null;
  reasons: string[];
  incorrect_facts: Record<string, unknown>[];
  visible_sources: Record<string, unknown>[];
  note: string | null;
  evaluator: "system" | "user";
  version: number;
  updated_at: string;
  suggested_actions?: SuggestedMonitoringActionData[];
};

type MonitoringSampleData = {
  id: string;
  batch_id: string;
  platform_id: string;
  platform_name: string;
  collection_mode: PlatformMode;
  question_id: string;
  question_text: string;
  question_family: "category_discovery" | "recommendation" | "scenario" | "comparison" | "brand_verification";
  is_brand_query: boolean;
  priority: number;
  attempt: number;
  status: "succeeded" | "failed" | "not_executed";
  raw_answer: string | null;
  asked_at: string | null;
  failure_reason: string | null;
  evaluation: SampleEvaluationData | null;
};

type MonitoringMetricDetail = {
  numerator: number | null;
  denominator: number | null;
  rate: number | null;
};

type MonitoringSummaryData = {
  sample_count: number;
  effective_sample_count: number;
  failed_count: number;
  not_executed_count: number;
  brand_found_rate: number | null;
  correct_association_rate: number | null;
  recommendation_rate: number | null;
  recommendation_supported_rate: number | null;
  fact_accuracy_rate: number | null;
  source_coverage_rate: number | null;
  repeat_appearance_rate: number | null;
  metric_details: Record<string, MonitoringMetricDetail>;
  mode_breakdown: Record<string, Record<string, unknown>>;
};

type MonitoringBatchData = {
  id: string;
  client_id: string;
  question_set_id: string;
  question_set_version: number;
  status: "queued" | "running" | "partial" | "succeeded" | "failed";
  platform_ids: string[];
  api_sample_count: number;
  created_at: string;
  completed_at: string | null;
  samples: MonitoringSampleData[];
  summary: MonitoringSummaryData;
};

type MonitoringMetricsData = {
  sample_count: number;
  effective_sample_count: number;
  failed_count: number;
  not_executed_count: number;
  brand_found_rate: number | null;
  correct_association_rate: number | null;
  recommendation_rate: number | null;
  recommendation_supported_rate: number | null;
  fact_accuracy_rate: number | null;
  source_coverage_rate: number | null;
  repeat_appearance_rate: number | null;
  metric_details: Record<string, MonitoringMetricDetail>;
  mode_breakdown: Record<string, Record<string, unknown>>;
  time_range: { from: string; to: string };
  platform_ids: string[];
  question_families: ("category_discovery" | "recommendation" | "scenario" | "comparison" | "brand_verification")[];
};

type OptimizationActionData = {
  id: string;
  client_id: string;
  source: "monitoring_feedback" | "monitoring_evaluation";
  source_id: string;
  action_type: "add_fact_task" | "add_content_brief" | "update_channel_priority" | "increase_sample";
  title: string;
  reason: string;
  target_level: "L1" | "L2" | "L3";
  target_page: "P02" | "P04" | "P06" | "P07";
  status: "open";
  created_at: string;
};

type ProviderSettingData = {
  provider: "deepseek" | "qwen";
  enabled: boolean;
  base_url: string;
  workspace_id: string | null;
  writer_model: string | null;
  reviewer_model: string | null;
  fallback_model: string | null;
  daily_budget_cny_fen: number;
  timeout_seconds: number;
  secret_configured: boolean;
  secret_mask: string | null;
  last_tested_at: string | null;
  last_test_status: "success" | "failed" | "not_tested";
  version: number;
};

type RuntimeSettingsData = {
  timezone: "Asia/Shanghai";
  max_upload_mb: 30;
  max_upload_files: 20;
  job_retry_limit: 3;
  job_poll_seconds: 2;
  default_client_monthly_budget_cny_fen: number;
  version: number;
};

type SettingsData = {
  providers: ProviderSettingData[];
  runtime: RuntimeSettingsData;
  catalogs: {
    industry_template_version: string;
    prompt_template_version: string;
    channel_catalog_version: string;
    platform_catalog_version: string;
  };
};

type IndustryTemplateData = {
  id: string;
  industry_code: string;
  industry_name: string;
  required_fact_keys: string[];
  optional_fields: {
    key: string;
    label: string;
    value_type: "text" | "number" | "boolean" | "date" | "list";
    help_text: string;
  }[];
  consumer_concerns: string[];
  content_type_labels: {
    content_type: ContentBriefData["content_type"];
    display_name: string;
  }[];
  prohibited_claims: string[];
  active: boolean;
};

type PromptTemplateData = {
  id: string;
  code: string;
  category: "guardrail" | "base" | "content_form" | "keyword_strategy" | "channel_adapter";
  name: string;
  description: string;
  template_text: string;
  editable: boolean;
  active: boolean;
  variable_keys: string[];
  required_fact_keys: string[];
  contact_policy: "allow" | "official_only" | "omit" | "manual_review" | null;
  default_contact_policy: "allow" | "official_only" | "omit" | "manual_review" | null;
  channel_id: string | null;
  source_url: string | null;
  verified_at: string | null;
  current_version: number;
  version: number;
  updated_at: string;
};

type PromptTemplateListData = {
  items: PromptTemplateData[];
  available_variables: string[];
  guardrails: {
    editable: false;
    summary: string;
  };
};

type PromptTemplateVersionData = {
  id: string;
  template_id: string;
  version_number: number;
  template_text: string;
  contact_policy: "allow" | "official_only" | "omit" | "manual_review" | null;
  change_note: string;
  created_at: string;
};

type JobData = {
  id: string;
  client_id: string | null;
  type: "material_extract" | "diagnostic" | "strategy_generate" | "document_operation" | "content_publish" | "channel_recommend" | "monitoring_batch";
  status: JobStatus;
  progress: number;
  current_step: string;
  attempt: number;
  max_attempts: number;
  result_resource_type: string | null;
  result_resource_id: string | null;
  error_code: number | null;
  error_message: string | null;
  retryable: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};
```

## 4. 系统与认证接口

### 4.1 GET `/health/live`

- 请求：无请求体，无认证。
- 成功 200：`Success<{ status: "ok"; service: "geo-api"; version: string }>`。
- 错误 500：`ErrorResponse`，代码 50001。

### 4.2 GET `/health/ready`

- 请求：无请求体，无认证。
- 成功 200：`Success<{ status: "ready"; database: "ok"; storage: "ok"; worker_heartbeat: "ok" | "stale" }>`。
- 错误 503：`ErrorResponse`，代码 50301，`message="数据库或文件存储不可用"`。

### 4.3 POST `/auth/login`

- 请求体：`{ username: string; password: string }`；用户名 3—64 字符，密码 12—128 字符。
- 成功 200：`Success<SessionData>`，并设置 `geo_session` Cookie。
- 错误 401：`ErrorResponse`，代码 40102，`message="用户名或密码错误"`。

### 4.4 GET `/auth/session`

- 请求：无请求体。
- 成功 200：`Success<SessionData>`。
- 错误 401：`ErrorResponse`，代码 40101，`message="登录已失效，请重新登录"`。

### 4.5 DELETE `/auth/session`

- 请求：无请求体；要求 CSRF。
- 成功 200：`Success<{ logged_out: true }>`，清除 Session Cookie。
- 错误 403：`ErrorResponse`，代码 40301，`message="安全校验失败，请刷新页面"`。

### 4.6 PUT `/auth/password`

- 请求体：`{ current_password: string; new_password: string }`；新密码 12—128 字符且不得与旧密码相同。
- 成功 200：`Success<{ changed: true; relogin_required: true }>`，撤销全部 Session。
- 错误 422：`ErrorResponse`，代码 40001，`message="新密码不符合安全要求"`。

## 5. 客户与工作台接口

### 5.1 GET `/clients`

- 请求：查询参数 `q?: string`、`status?: ClientStatus`、`page?: number`、`page_size?: number`、`sort?: "-updated_at" | "standard_name"`；无请求体。
- 成功 200：`Success<Page<ClientSummary>>`。
- `fact_completeness` 每次读取时按企业名称、行业、地区、主营服务、企业介绍、
  目标客户、企业优势和联系方式八组当前基础资料计算，不读取遗留缓存值。
- 错误 400：`ErrorResponse`，代码 40001，`message="分页或筛选参数无效"`。

### 5.2 POST `/clients`

- 请求体：`{ standard_name: string; short_name: string | null; industry_code: string; province: string; city: string; district: string; address: string; contact_phone: string | null; contact_wechat: string | null; business_hours: string | null; service_radius: string | null; cooperation_started_on: string; notes: string | null }`。
- 成功 201：`Success<ClientDetail>`。
- 错误 400：`ErrorResponse`，代码 40001，`message="客户资料校验失败"`。

### 5.3 GET `/clients/{client_id}`

- 请求：路径参数 `client_id: string`；无请求体。
- 成功 200：`Success<ClientDetail>`。
- `fact_completeness` 与客户列表使用相同的八组实时计算规则。
- 错误 404：`ErrorResponse`，代码 40401，`message="客户不存在"`。

### 5.4 PATCH `/clients/{client_id}`

- 请求体：`{ version: number; standard_name?: string; short_name?: string | null; industry_code?: string; province?: string; city?: string; district?: string; address?: string; contact_phone?: string | null; contact_wechat?: string | null; business_hours?: string | null; service_radius?: string | null; cooperation_started_on?: string; notes?: string | null; status?: "active" | "paused" }`；至少一个可编辑字段。
- 成功 200：`Success<ClientDetail>`。
- 错误 409：`ErrorResponse`，代码 40901，`message="客户资料已被更新，请刷新后重试"`。

### 5.5 POST `/clients/{client_id}/archive`

- 请求体：`{ version: number; reason: string }`，原因 2—200 字符。
- 成功 200：`Success<ClientDetail>`，`status="archived"`。
- 错误 409：`ErrorResponse`，代码 40902，`message="客户存在运行中任务，暂时不能归档"`。

### 5.6 POST `/clients/{client_id}/restore`

- 请求体：`{ version: number }`。
- 成功 200：`Success<ClientDetail>`，`status="active"`。
- 错误 409：`ErrorResponse`，代码 40901，`message="客户状态已变化，请刷新后重试"`。

### 5.7 GET `/clients/{client_id}/dashboard`

- 请求：路径参数 `client_id: string`；无请求体。
- 成功 200：`Success<DashboardData>`。
- 错误 404：`ErrorResponse`，代码 40401，`message="客户不存在"`。

## 6. 企业知识库接口

### 6.1 GET `/clients/{client_id}/materials`

- 请求：查询参数 `category?: MaterialData["category"]`、`extraction_status?: MaterialData["extraction_status"]`、`page?: number`、`page_size?: number`；无请求体。
- 成功 200：`Success<Page<MaterialData>>`。
- 错误 400：`ErrorResponse`，代码 40001，`message="资料筛选参数无效"`。

### 6.2 POST `/clients/{client_id}/materials`

- 请求：`multipart/form-data`；字段 `files` 为 1—20 个文件，`category` 为 `MaterialData["category"]`，`authorization_status` 为 `AuthorizationStatus`。单文件不超过 30 MB。
- 成功 201：`Success<{ items: MaterialData[] }>`。
- 错误 413：`ErrorResponse`，代码 41301，`message="文件数量或体积超过限制"`。
- 错误 415：`ErrorResponse`，代码 41501，`message="文件类型或实际内容不允许上传"`。

### 6.3 GET `/materials/{material_id}`

- 请求：路径参数 `material_id: string`；无请求体。
- 成功 200：`Success<{ material: MaterialData; fragments: { id: string; page: number | null; text: string; extraction_method: "text" | "ocr" | "manual" }[] }>`。
- 错误 404：`ErrorResponse`，代码 40401，`message="资料不存在"`。

### 6.4 GET `/materials/{material_id}/file`

- 请求：路径参数 `material_id: string`；仅用于已登录运营人员预览企业图片。
- 成功 200：返回 `image/png` 或 `image/jpeg` 文件流，不使用 JSON 成功包络。
- 错误 404：`ErrorResponse`，代码 40401，`message="图片不存在"`。

### 6.5 DELETE `/materials/{material_id}`

- 仅允许删除企业图片；删除后同步移除所有文章版本中的图片引用，并删除存储文件。
- 成功 200：`Success<{ id: string; deleted: true }>`。
- 错误 404：`ErrorResponse`，代码 40401，`message="图片不存在"`。

### 6.6 POST `/materials/{material_id}/extract`

- 请求头：`Idempotency-Key`；请求体 `{ force: boolean; languages: ["zh-CN"] }`。
- 成功 202：`Success<JobAccepted>`。
- 错误 409：`ErrorResponse`，代码 40902，`message="该资料正在解析"`。

### 6.7 GET `/clients/{client_id}/facts`

- 请求：查询参数 `category?: FactData["category"]`、`status?: FactStatus`、`q?: string`、`page?: number`、`page_size?: number`；无请求体。
- 成功 200：`Success<Page<FactData>>`。
- 错误 400：`ErrorResponse`，代码 40001，`message="事实筛选参数无效"`。

### 6.8 POST `/clients/{client_id}/facts`

- 请求体：`{ category: FactData["category"]; key: string; label: string; value: string; status: "confirmed" | "client_provided" | "private"; valid_from: string | null; valid_until: string | null; evidence_ids: string[] }`。
- 成功 201：`Success<FactData>`。
- 错误 422：`ErrorResponse`，代码 42202，`message="确认事实缺少可用证据"`。

### 6.9 PATCH `/facts/{fact_id}`

- 请求体：`{ version: number; label?: string; value?: string; status?: FactStatus; valid_from?: string | null; valid_until?: string | null }`；至少一个可编辑字段。
- 成功 200：`Success<FactData>`。
- 错误 409：`ErrorResponse`，代码 40901，`message="该事实已被更新，请刷新后重试"`。

### 6.10 POST `/facts/{fact_id}/evidence`

- 请求体：`{ source_type: "material" | "manual" | "public_url"; material_id: string | null; source_label: string; source_url: string | null; quote: string; observed_at: string; authorization_status: AuthorizationStatus }`；`material` 类型要求 `material_id`，`public_url` 类型要求 HTTPS URL。
- 成功 201：`Success<FactData>`。
- 错误 400：`ErrorResponse`，代码 40001，`message="证据来源与字段不匹配"`。

### 6.11 POST `/facts/{fact_id}/confirm`

- 请求体：`{ version: number; evidence_ids: string[]; confirmation_note: string }`。
- 成功 200：`Success<FactData>`，`status="confirmed"`。
- 错误 422：`ErrorResponse`，代码 42202，`message="该事实存在冲突或证据不可公开"`。

### 6.12 GET `/clients/{client_id}/conflicts`

- 请求：查询参数 `status?: "open" | "resolved" | "ignored"`；无请求体。
- 成功 200：`Success<{ items: ConflictData[] }>`。
- 错误 404：`ErrorResponse`，代码 40401，`message="客户不存在"`。

### 6.13 POST `/conflicts/{conflict_id}/resolve`

- 请求体：`{ version: number; action: "select" | "manual" | "ignore"; selected_evidence_id: string | null; manual_value: string | null; resolution_note: string }`。`select` 要求证据 ID，`manual` 要求手工值。
- 成功 200：`Success<ConflictData>`。
- 错误 409：`ErrorResponse`，代码 40901，`message="冲突状态已变化，请刷新后重试"`。

### 6.14 GET `/clients/{client_id}/knowledge-profile`

- 请求：路径参数 `client_id: string`；无请求体。
- 成功 200：`Success<KnowledgeProfileData>`。
- 错误 404：`ErrorResponse`，代码 40401，`message="客户知识库不存在"`。

### 6.15 PATCH `/clients/{client_id}/knowledge-profile`

- 请求体：`{ version: number; services: KnowledgeProfileData["services"]; capabilities: KnowledgeProfileData["capabilities"]; prohibited_claims: KnowledgeProfileData["prohibited_claims"]; external_presences: KnowledgeProfileData["external_presences"] }`。数组发送完整期望状态，服务端按 ID 更新。
- 成功 200：`Success<KnowledgeProfileData>`。
- 错误 409：`ErrorResponse`，代码 40901，`message="知识库已被更新，请刷新后重试"`。

## 7. 诊断、策略与简报接口

### 7.1 POST `/clients/{client_id}/diagnostics`

- 请求头：`Idempotency-Key`；请求体 `{ scope: ["entity", "evidence", "content", "source", "visibility"]; monitoring_window_days: 30 }`。
- 成功 202：`Success<JobAccepted>`。
- 错误 422：`ErrorResponse`，代码 42201，`message="企业名称、地区或服务事实不足，无法诊断"`。

### 7.2 GET `/clients/{client_id}/diagnostics/latest`

- 请求：路径参数 `client_id: string`；无请求体。
- 成功 200：`Success<DiagnosticRunData | null>`；从未诊断时 `data=null`。
- 错误 404：`ErrorResponse`，代码 40401，`message="客户不存在"`。

### 7.3 PATCH `/diagnostic-issues/{issue_id}`

- 请求体：`{ version: number; status: "resolved" | "ignored"; note: string }`。
- 成功 200：`Success<DiagnosticRunData["issues"][number]>`。
- 错误 409：`ErrorResponse`，代码 40901，`message="诊断问题已被更新，请刷新后重试"`。

### 7.4 POST `/clients/{client_id}/strategy/generate`

- 请求头：`Idempotency-Key`；请求体 `{ diagnostic_run_id: string; include_families: ["discovery", "recommendation", "scenario", "comparison", "brand_verification"]; brief_count: number }`；`brief_count` 为 1—30。
- 成功 202：`Success<JobAccepted>`。
- 错误 422：`ErrorResponse`，代码 42201，`message="诊断或事实不满足策略生成条件"`。

### 7.5 GET `/clients/{client_id}/strategy`

- 请求：查询参数 `active_only?: boolean`；无请求体。
- 成功 200：`Success<StrategyBundleData | null>`；未生成策略时 `data=null`。
- 错误 404：`ErrorResponse`，代码 40401，`message="客户不存在"`。

### 7.6 PATCH `/strategy-items/{item_id}`

- 请求体：`{ version: number; text?: string; priority?: 1 | 2 | 3; locked?: boolean; active?: boolean }`；至少一个可编辑字段。
- 成功 200：`Success<StrategyItemData>`。
- 错误 409：`ErrorResponse`，代码 40901，`message="策略项已被更新，请刷新后重试"`。

### 7.7 GET `/clients/{client_id}/keyword-workspace`

- 请求：路径参数 `client_id: string`；无请求体。
- 成功 200：`Success<KeywordWorkspaceData>`；首次访问返回 `version=0` 的 AI 初始建议，但不会自动写入正式关键词库。
- 错误 404：`ErrorResponse`，代码 40401，`message="客户不存在"`。

### 7.8 PUT `/clients/{client_id}/keyword-profile`

- 请求体：`{ version: number; primary_keyword: string; regions: string[]; secondary_keywords: string[]; keyword_types: string[] }`；地区 1—5 个，二级关键词最多 10 个，至少选择一种关键词类型。
- 成功 200：`Success<KeywordProfileData>`。
- 错误 404：`ErrorResponse`，代码 40401，`message="客户不存在"`。
- 错误 409：`ErrorResponse`，代码 40901，`message="关键词配置已被更新，请刷新后重试"`。
- 错误 422：`ErrorResponse`，代码 42201，`message="关键词参数校验失败"`。

### 7.9 POST `/clients/{client_id}/keyword-generations`

- 请求头：`Idempotency-Key`；请求体 `{ profile_version: number; target_count: number }`，`target_count` 为 5—50。
- 成功 202：`Success<KeywordGenerationAcceptedData>`；系统最多进行两轮 AI 补充生成，并在质量过滤后允许实际数量少于期望数量。
- 错误 404：`ErrorResponse`，代码 40401，`message="客户不存在"`。
- 错误 409：`ErrorResponse`，代码 40901 或 40903，关键词配置已变化或幂等键冲突。
- 错误 422：`ErrorResponse`，代码 42201，`message="关键词参数校验失败"`。

### 7.10 GET `/keyword-generations/{generation_id}`

- 请求：路径参数 `generation_id: string`；无请求体。
- 成功 200：`Success<KeywordGenerationData>`；包含本次任务候选关键词。
- 错误 404：`ErrorResponse`，代码 40401，`message="关键词任务不存在"`。

### 7.11 PATCH `/keyword-candidates/{candidate_id}`

- 请求体：`{ version: number; selected: boolean; active: boolean }`；`active=false` 表示从候选列表删除，但保留归一化指纹用于基础去重。
- 成功 200：`Success<KeywordCandidateData>`。
- 错误 404：`ErrorResponse`，代码 40401，`message="候选关键词不存在"`。
- 错误 409：`ErrorResponse`，代码 40901，候选词版本或任务状态冲突。
- 错误 422：`ErrorResponse`，代码 42201，`message="关键词参数校验失败"`。

### 7.12 POST `/keyword-generations/{generation_id}/confirm`

- 请求体：`{ version: number; candidate_ids: string[] }`；只保存当前任务中仍有效的候选关键词。
- 成功 200：`Success<KeywordGenerationData>`；被确认关键词同步进入正式策略项并默认选中。
- 错误 404：`ErrorResponse`，代码 40401，`message="关键词任务不存在"`。
- 错误 409：`ErrorResponse`，代码 40901，任务版本或状态冲突。
- 错误 422：`ErrorResponse`，代码 42201，候选关键词无效或请求参数校验失败。

### 7.13 DELETE `/keyword-generations/{generation_id}`

- 请求：查询参数 `version: number`；无请求体。删除为归档，不删除候选词去重指纹。
- 成功 200：`Success<KeywordGenerationData>`。
- 错误 404：`ErrorResponse`，代码 40401，`message="关键词任务不存在"`。
- 错误 409：`ErrorResponse`，代码 40901，`message="关键词任务已被更新，请刷新后重试"`。

### 7.14 POST `/clients/{client_id}/briefs`

- 请求体：`{ title: string; content_type: ContentBriefData["content_type"]; target_question_ids: string[]; target_keywords: string[]; target_level: ResultLevel; audience: string; angle: string; required_fact_ids: string[]; required_evidence_ids: string[]; expected_recommendation_reason: string; prohibited_claims: string[]; retest_questions: string[]; suggested_channel_ids: string[]; priority: 1 | 2 | 3 }`。
- 成功 201：`Success<ContentBriefData>`。
- 错误 422：`ErrorResponse`，代码 42201，`message="简报缺少目标问题或必需事实"`。

### 7.15 GET `/briefs/{brief_id}`

- 请求：路径参数 `brief_id: string`；无请求体。
- 成功 200：`Success<ContentBriefData>`。
- 错误 404：`ErrorResponse`，代码 40401，`message="内容简报不存在"`。

### 7.16 PATCH `/briefs/{brief_id}`

- 请求体：`{ version: number; title?: string; audience?: string; angle?: string; required_fact_ids?: string[]; required_evidence_ids?: string[]; expected_recommendation_reason?: string; prohibited_claims?: string[]; retest_questions?: string[]; suggested_channel_ids?: string[]; priority?: 1 | 2 | 3; status?: ContentBriefData["status"] }`。
- 成功 200：`Success<ContentBriefData>`。
- 错误 409：`ErrorResponse`，代码 40901，`message="内容简报已被更新，请刷新后重试"`。

## 8. 内容工作台接口

### 8.1 GET `/clients/{client_id}/documents`

- 请求：查询参数 `status?: ContentStatus`、`brief_id?: string`、`page?: number`、`page_size?: number`；无请求体。
- 成功 200：`Success<Page<DocumentData>>`。
- 错误 400：`ErrorResponse`，代码 40001，`message="内容筛选参数无效"`。

### 8.2 GET `/clients/{client_id}/content-generation-tasks`

- 请求：查询参数 `page?: number`、`page_size?: number`；无请求体。
- 成功 200：`Success<Page<ContentGenerationTaskData>>`。任务状态根据关联文章的实际后台生成状态聚合，无活动任务时不轮询。
- 错误 400：`ErrorResponse`。

### 8.3 GET `/content-generation-tasks/{task_id}`

- 请求：路径参数 `task_id: string`；无请求体。
- 成功 200：`Success<ContentGenerationTaskData>`，`documents` 返回本次任务创建的完整文章列表。
- 错误 404：`ErrorResponse`，代码 40401，`message="内容生成任务不存在"`。

### 8.4 POST `/content-generation-tasks/{task_id}/confirm`

- 请求体：`{ version: number }`。
- 成功 200：`Success<ContentGenerationTaskData>`，写入 `confirmed_at`；该任务下已通过质量检查的文章从此进入文章发布工作区。
- 错误 404：`ErrorResponse`，代码 40401，`message="内容生成任务不存在"`。
- 错误 409：`ErrorResponse`，代码 40901，`message="生成任务已更新，请刷新后重试"`。
- 错误 422：`ErrorResponse`，代码 42202，`message="文章尚未全部生成并达到可发布标准，暂时不能确认"`。

### 8.5 POST `/clients/{client_id}/documents`

- 请求体：`{ brief_id: string; title: string }`。
- 成功 201：`Success<DocumentData>`，`status="brief"` 且 `current_version=null`。
- 错误 422：`ErrorResponse`，代码 42201，`message="简报不属于当前客户或已归档"`。
- Web 不向用户开放 `current_version=null` 的空白编辑器。创建成功后必须自动按顺序发起 `outline` 与 `draft` 操作；`draft` 成功并产生首个 AI 版本后才进入可编辑状态。

### 8.6 POST `/clients/{client_id}/documents/batch`

- 请求体：`{ keyword_ids: string[]; platform_type: "self_media"; article_count: number; length: "short" | "medium" | "long"; style: "auto" | "guide" | "faq" | "service" | "scenario"; content_form_codes: string[]; target_channel_ids: string[] }`。`article_count` 范围为 1—20，表示每个平台的文章数量，总数为 `article_count × target_channel_ids.length`，不再乘以关键词数量。关键词取当前客户正式关键词库中的有效条目，不要求先在关键词页勾选。内容形式可多选，并在每个平台内均衡轮换；所选平台必须至少有一个已连接且已启用的账号；本批次最多创建 100 篇。为兼容历史调用仍接受 `content_form`、`target_channel_id` 和通用稿。
- 成功 201：`Success<DocumentsCreatedData>`，返回不可变配置快照 `task`，并为每篇文章创建独立事实快照和后台 AI 生成任务。
- 错误 422：`ErrorResponse`，代码 42201，`message="企业资料已经更新，请先重新运行 GEO 诊断"`、`message="所选关键词不存在、已删除或不属于当前客户"`、`message="未配置可用账号的平台：…"` 或 `message="知识库没有可用于生成文章的企业资料"`。

### 8.7 GET `/documents/{document_id}`

- 请求：路径参数 `document_id: string`；无请求体。
- 成功 200：`Success<DocumentData>`。
- 错误 404：`ErrorResponse`，代码 40401，`message="内容不存在"`。

### 8.8 PATCH `/documents/{document_id}`

- 请求体：`{ version: number; title: string; body_markdown: string; save_reason: string; source_version_id?: string; channel_id?: string }`。正文最多 100000 字符。编辑普通主稿时不传后两个字段；从具名渠道成品进入编辑时两者必须同时传入，保存后更新该渠道的最新版本映射并重新执行质量检查。
- 成功 200：`Success<DocumentData>`，创建 `manual_edit` 版本。
- 错误 409：`ErrorResponse`，代码 40901，`message="内容已在其他位置保存，请刷新并比较版本"`。
- 错误 422：`ErrorResponse`，代码 42202，`message="AI 初稿尚未完成，不能人工编辑"`。

### 8.9 POST `/documents/{document_id}/operations`

- 请求头：`Idempotency-Key`。
- 请求体是以下联合类型：

```ts
type DocumentOperationRequest =
  | { operation: "outline"; source_version_id: string | null }
  | { operation: "draft"; source_version_id: string | null }
  | { operation: "check"; source_version_id: string }
  | { operation: "geo_optimize"; source_version_id: string; target_question_ids: string[] }
  | { operation: "naturalize"; source_version_id: string; content_type: ContentBriefData["content_type"]; intensity: "light" | "standard" }
  | { operation: "channel_variant"; source_version_id: string; channel_ids: string[] }
  | { operation: "regenerate"; source_version_id: string; revision_instruction: string; target_channel_id: string | null }
  | { operation: "export"; source_version_id: string; format: "markdown" | "docx"; include_sources: boolean };
```

- 成功 202：`Success<JobAccepted>`。
- 错误 422：`ErrorResponse`，代码 42202，`message="当前内容存在事实或合规阻断，不能执行该操作"`。
- 错误 429：`ErrorResponse`，代码 42902，`message="今日模型预算已达到上限"`。

### 8.10 GET `/documents/{document_id}/versions`

- 请求：查询参数 `page?: number`、`page_size?: number`；无请求体。
- 成功 200：`Success<Page<DocumentVersionData>>`。
- 错误 404：`ErrorResponse`，代码 40401，`message="内容不存在"`。

### 8.11 POST `/documents/{document_id}/versions/{version_id}/restore`

- 请求体：`{ document_version: number; reason: string }`。
- 成功 201：`Success<DocumentData>`，创建 `restored` 新版本。
- 错误 409：`ErrorResponse`，代码 40901，`message="内容已被更新，请刷新后再恢复"`。

### 8.12 GET `/documents/{document_id}/quality-checks`

- 请求：查询参数 `version_id?: string`、`page?: number`、`page_size?: number`；无请求体。
- 成功 200：`Success<Page<QualityCheckData>>`。
- 错误 404：`ErrorResponse`，代码 40401，`message="内容不存在"`。

### 8.13 POST `/documents/{document_id}/publish`

- 请求头：`Idempotency-Key`；请求体：`{ version: number; account_ids: string[] }`。`account_ids` 可同时选择头条号、百家号、网易号、搜狐号、企鹅号和一点号的多个已连接账号，最多 20 个。一点号在首个真实账号完成发布页字段验证前，会停止最终提交并返回明确提示。
- 服务端按账号所属平台选择相同 `channel_id` 的文章渠道版本；缺少任一渠道版本时整次请求不入队。
- 成功 202：`Success<PublicationBatchAccepted>`。每个账号拥有独立发布记录和 Worker 任务；文章的 `generation_status` 不变。
- 错误 404：`ErrorResponse`，代码 40401，`message="内容不存在"`。
- 错误 409：`ErrorResponse`，代码 40901 或 40902，表示内容已更新或所选账号均已发布对应版本。
- 错误 422：`ErrorResponse`，代码 42202，表示正文不可发布、账号未连接启用、账号不存在，或文章缺少对应渠道版本。

### 8.14 DELETE `/documents/{document_id}`

- 请求：查询参数 `version: number`；无请求体。删除采用可恢复的软归档。
- 成功 200：`Success<DocumentData>`，`status="archived"`，默认文章列表不再返回。
- 错误 404：`ErrorResponse`，代码 40401，`message="内容不存在"`。
- 错误 409：`ErrorResponse`，代码 40901，`message="内容已被更新，请刷新后重试"`。

### 8.15 POST `/documents/{document_id}/restore`

- 请求体：`{ version: number }`。只恢复已软删除的文章；有正文时根据最新质量检查恢复为可继续使用的状态，无正文时恢复为等待生成。
- 成功 200：`Success<DocumentData>`，文章重新出现在默认文章列表。
- 错误 404：`ErrorResponse`，代码 40401，`message="内容不存在"`。
- 错误 409：`ErrorResponse`，代码 40901，`message="内容已更新，请刷新后重试"`。
- 错误 422：`ErrorResponse`，代码 42202，`message="只有已删除文章可以恢复"`。

### 8.16 GET `/exports/{export_id}/download`

- 请求：路径参数 `export_id: string`；无请求体。响应为文件流，不使用 JSON 成功包络；响应头包含 `Content-Disposition`、`Content-Type`、`X-Request-Id`。
- 成功 200：Markdown 使用 `text/markdown; charset=utf-8`，DOCX 使用 `application/vnd.openxmlformats-officedocument.wordprocessingml.document`。
- 错误 404：`ErrorResponse`，代码 40401，`message="导出文件不存在或已清理"`。
- 错误 409：`ErrorResponse`，代码 40902，`message="导出任务尚未完成"`。

### 8.17 GET `/documents/{document_id}/versions/{version_id}/cover`

- 请求：路径参数 `document_id: string`、`version_id: string`；查询参数
  `style?: "azure" | "sunrise" | "mint"`、`download?: boolean`。
- 成功 200：返回 1200 × 675 的 `image/png` 文件流，不使用 JSON 成功包络；
  `download=true` 时使用可读文件名触发下载，否则用于页面内预览。
- 封面只使用该文章版本标题、企业简称、地区和主营业务；不包含联系方式、内部 ID
  或来源标记。图片按文章版本和样式缓存。
- 错误 400：`ErrorResponse`，代码 40001，样式参数无效。
- 错误 404：`ErrorResponse`，代码 40401，`message="文章封面不存在"`。

## 9. 渠道接口

### 9.1 GET `/channels`

- 请求：查询参数 `ownership?: ChannelData["ownership"]`、`cost?: ChannelData["cost"]`、`content_type?: string`、`active?: boolean`；无请求体。
- 成功 200：`Success<{ items: ChannelData[]; catalog_version: string }>`。
- 目录规则：`catalog_version` 使用日期版本；官方入口、核验日期、费用性质、访问方式和所有权必须来自版本化目录，不能由模型临时生成。
- 错误 400：`ErrorResponse`，代码 40001，`message="渠道筛选参数无效"`。

### 9.2 GET `/clients/{client_id}/channel-recommendations`

- 请求：查询参数 `active_only?: boolean`；无请求体。
- 成功 200：`Success<{ items: ChannelRecommendationData[]; generated_at: string | null }>`。
- 每条建议绑定 `generation_id`、`brief_id` 和可选 `content_document_id`，并返回本篇内容的渠道改编、账号定位、授权、费用、风险和目标生态说明。
- 渠道与内容简报均保存生成时快照；目录升级或简报后续修改不会改写历史建议。重新生成只将旧建议标为非当前，`active_only=false` 可读取历史。
- 错误 404：`ErrorResponse`，代码 40401，`message="客户不存在"`。

### 9.3 POST `/clients/{client_id}/channel-recommendations/generate`

- 请求头：`Idempotency-Key`；请求体 `{ brief_ids: string[]; include_ownership: ["operator_publishable", "client_required", "partner_cooperation"] }`。
- 成功 202：`Success<JobAccepted>`。
- 推荐规则：按每篇内容简报分别计算，综合客户行业、地区、最新诊断缺口、内容类型、建议渠道、账号所有权、公开访问性、费用和目录优先级；匹配分不是搜索量或平台流量。
- 默认每篇选择最多 4 个运营方可发布渠道、2 个客户配合渠道和 1 个合作渠道；请求可通过 `include_ownership` 缩小范围。
- 结果边界：此历史推荐接口只生成官方入口与内容适配建议；自动发布使用独立的渠道配置和发布任务。
- 幂等规则：同一客户、任务类型和 `Idempotency-Key` 的相同参数返回同一 202 任务；相同键用于不同参数返回 409。
- 错误 422：`ErrorResponse`，代码 42201，`message="客户暂无可用内容简报，请先生成内容策略"`。

### 9.4 GET `/publishing/channels`

- 请求：无请求体。
- 成功 200：`Success<PublishingChannelListData>`。固定返回头条号、百家号、网易号、搜狐号、企鹅号和一点号；每项包含 `max_accounts=5`、账号数量以及独立账号列表。一点号同一企业主体的官方认证数量仍以平台规则为准（当前为最多 2 个）。
- 错误 400：`ErrorResponse`，代码 40001。

### 9.5 POST `/publishing/channels/{channel_id}/accounts`

- 请求体：`{ display_name: string }`。`display_name` 是本系统内的账号备注，不是平台密码。
- 成功 201：`Success<PublishingAccountData>`。
- 错误 409：同一平台备注重复或已经达到五个账号上限。
- 错误 422：渠道未接入自动发布。

### 9.6 PATCH `/publishing/accounts/{account_id}`

- 请求体：`{ version: number; display_name?: string; enabled?: boolean }`。启用前必须检测到 `connection_status="connected"`。
- 成功 200：`Success<PublishingAccountData>`。
- 错误 404：账号不存在。
- 错误 409：版本冲突或备注重复。
- 错误 422：未连接时尝试启用。

### 9.7 POST `/publishing/accounts/{account_id}/login-window`

- 请求：无请求体。按平台和账号 ID 打开独立本机浏览器 profile，由运营人员登录；系统不保存平台账号密码。
- 成功 200：`Success<PublishingAccountData>`，`connection_status="awaiting_login"`。
- 错误 404：账号不存在。
- 错误 422：浏览器无法启动。

### 9.8 POST `/publishing/accounts/{account_id}/test`

- 请求：无请求体。关闭可见登录窗口后检测本机浏览器会话；不发布文章。
- 成功 200：`Success<PublishingAccountData>`。连接失败、安全验证和登录失效通过 `connection_status` 与 `last_error` 返回，并自动暂停该账号。
- 错误 404：账号不存在。
- 错误 422：浏览器会话无法启动或检测失败。

## 10. AI 可见性监测接口

### 10.1 GET `/monitoring/platforms`

- 请求：查询参数 `priority?: "P0" | "P1"`、`mode?: PlatformMode`、`active?: boolean`；无请求体。
- 成功 200：`Success<{ items: PlatformData[]; catalog_version: string }>`。
- 当前版本固定返回 DeepSeek、通义千问和豆包；三者均为官方模型 API 自动样本，不能表述为消费者端 App 回答。
- 错误 400：`ErrorResponse`，代码 40001，`message="平台筛选参数无效"`。

### 10.2 GET `/clients/{client_id}/question-sets`

- 请求：无请求体。
- 成功 200：`Success<{ items: QuestionSetData[] }>`。
- 错误 404：`ErrorResponse`，代码 40401，`message="客户不存在"`。

### 10.3 POST `/clients/{client_id}/question-sets`

- 请求体：`{ name: string; frozen?: boolean; questions: QuestionInput[] }`；每组 1—50 个问题，问题文本 2—500 字符。`id`、品牌问法标记、目标级别和优先级省略时由服务端补默认值。
- 成功 201：`Success<QuestionSetData>`。
- 错误 400：`ErrorResponse`，代码 40001，`message="问题集格式或问题分类无效"`。

### 10.4 PATCH `/question-sets/{question_set_id}`

- 请求体：`{ version: number; name?: string; frozen?: boolean; questions?: QuestionInput[] }`。
- 成功 200：`Success<QuestionSetData>`。
- 错误 409：`ErrorResponse`，代码 40901，`message="问题集已被更新，请刷新后重试"`。

### 10.5 POST `/clients/{client_id}/monitoring-batches`

- 请求头：`Idempotency-Key`；请求体 `{ question_set_id: string; platform_ids: string[]; api_sample_count?: number; manual_placeholders?: boolean }`；API 采样次数 1—5。
- 成功 202：`Success<JobAccepted>`。
- 错误 422：`ErrorResponse`，代码 42201，`message="问题集未冻结或未选择监测平台"`。

### 10.6 GET `/monitoring-batches/{batch_id}`

- 请求：路径参数 `batch_id: string`；无请求体。
- 成功 200：`Success<MonitoringBatchData>`。
- 错误 404：`ErrorResponse`，代码 40401，`message="监测批次不存在"`。

### 10.7 POST `/monitoring-batches/{batch_id}/manual-samples`

- 请求体：`{ items: ManualSampleInput[] }`。`raw_answer` 与 `failure_reason` 可省略或为 `null`，但成功样本必须提供非空回答文本，失败样本必须提供非空失败原因；只允许更新该批次中等待人工采样的占位样本，单次最多 50 条。
- 成功 201：`Success<{ items: MonitoringSampleData[] }>`。
- 错误 400：`ErrorResponse`，代码 40001，`message="人工样本字段不完整或平台采集方式不匹配"`。

### 10.8 PUT `/monitoring-samples/{sample_id}/evaluation`

- 请求体：

```ts
type EvaluationRequest = {
  version?: number | null;
  brand_found: boolean;
  correctly_associated: boolean;
  recommended: boolean;
  recommendation_supported?: boolean | null;
  facts_accurate?: boolean | null;
  source_visible?: boolean;
  mentioned_name?: string | null;
  reasons?: string[];
  incorrect_facts?: Record<string, unknown>[];
  visible_sources?: Record<string, unknown>[];
  note?: string | null;
};
```

首次人工评估 `version=null`，修正已有评估传当前版本。`facts_accurate=null`
表示尚未依据 P02 事实与证据完成人工核验，系统不得把“未发现冲突”自动写成准确。

- 成功 200：`Success<SampleEvaluationData>`，`evaluator="user"`。
- 错误 409：`ErrorResponse`，代码 40901，`message="评估已被更新，请刷新后重试"`。

### 10.9 GET `/clients/{client_id}/monitoring-metrics`

- 请求：查询参数 `from: string`、`to: string`、`platform_ids?: string[]`、`question_families?: QuestionFamily[]`；时间范围最多 366 天。已执行样本按实际 `asked_at` 归期，尚未执行且没有 `asked_at` 的占位样本按 `created_at` 归期，确保未执行数不会被时间筛选静默丢弃。
- 成功 200：`Success<MonitoringMetricsData>`。
- 指标响应必须包含 `mode_breakdown.api` 与 `mode_breakdown.manual_consumer`；同时存在两种采集方式时，顶层比率及 `metric_details` 的分子、分母、比率均返回 `null`，不能暴露混合口径。品牌核验问题不进入无品牌发现率和推荐候选率，重复出现率按同一冻结问题的多次成功采样分组。
- 错误 400：`ErrorResponse`，代码 40001，`message="监测时间范围或筛选参数无效"`。

### 10.10 POST `/monitoring-evaluations/{evaluation_id}/feedback`

- 请求体：`{ action_type: "add_fact_task" | "add_content_brief" | "update_channel_priority" | "increase_sample"; reason: string; target_page: "P02" | "P04" | "P06" | "P07" }`。
- 成功 201：`Success<{ id: string; action_type: string; target_page: "P02" | "P04" | "P06" | "P07"; converted_record_type: "optimization_action"; converted_record_id: string }>`。相同评估与动作类型重复提交返回原动作，不重复创建。
- 错误 422：`ErrorResponse`，代码 42202，`message="该评估没有足够依据生成反馈动作"`。

### 10.11 GET `/clients/{client_id}/monitoring-batches/latest`

- 请求：无请求体。
- 成功 200：`Success<MonitoringBatchData>`，返回当前客户最新创建的监测批次及完整样本。
- 错误 404：`ErrorResponse`，代码 40401，`message="客户暂无监测批次"`。

### 10.12 GET `/clients/{client_id}/optimization-actions`

- 请求：可选查询参数 `target_page?: "P02" | "P04" | "P06" | "P07"`。
- 成功 200：`Success<{ items: OptimizationActionData[] }>`；按创建时间倒序返回持久化改进任务。每项包含来源评估、标题、原因、目标级别、目标页面、状态与创建时间。
- 错误 404：`ErrorResponse`，代码 40401，`message="客户不存在"`。

## 11. 设置接口

### 11.1 GET `/settings`

- 请求：无请求体。
- 成功 200：`Success<SettingsData>`；密钥仅返回配置状态和掩码。
- 错误 401：`ErrorResponse`，代码 40101，`message="登录已失效，请重新登录"`。

### 11.2 PATCH `/settings/runtime`

- 请求体：`{ version: number; default_client_monthly_budget_cny_fen: number }`；金额范围为 0—1000000 分，0 表示只使用供应商日预算而不显示单客户提醒。
- 成功 200：`Success<RuntimeSettingsData>`。
- 错误 409：`ErrorResponse`，代码 40901，`message="运行设置已被更新，请刷新后重试"`。

### 11.3 PUT `/settings/providers/{provider}`

- 请求：路径参数 `provider: "deepseek" | "qwen"`；请求体：

```ts
type ProviderSettingRequest = {
  version: number;
  enabled: boolean;
  base_url: string;
  workspace_id?: string | null;
  writer_model?: string | null;
  reviewer_model?: string | null;
  fallback_model?: string | null;
  daily_budget_cny_fen: number;
  timeout_seconds: number;
  api_key?: string | null;
};
```

`api_key=null` 表示保留原密钥，非空表示覆盖；响应永不返回明文。

- 成功 200：`Success<ProviderSettingData>`。
- 错误 409：`ErrorResponse`，代码 40901，`message="模型设置已被更新，请刷新后重试"`。

### 11.4 POST `/settings/providers/{provider}/test`

- 请求体：`{ test_type: "connectivity" | "structured_output"; use_saved_secret: boolean; api_key: string | null }`。使用临时 Key 时 `use_saved_secret=false` 且 `api_key` 非空；临时 Key 不落库。
- 成功 200：`Success<{ provider: "deepseek" | "qwen"; status: "success"; model: string; latency_ms: number; structured_output_valid: boolean }>`。
- 错误 502：`ErrorResponse`，代码 50201，`message="模型连接或返回格式测试失败"`。

## 12. 后台任务接口

### 12.1 GET `/prompt-templates`

- 请求：可选查询参数 `category`；需会话认证。
- 成功 200：`Success<PromptTemplateListData>`。
- 错误 400：`ErrorResponse`，提示词分类参数无效。

### 12.2 PATCH `/prompt-templates/{template_id}`

- 请求头：`X-CSRF-Token`；请求体包含 `version`、`template_text`、`active`、可选 `contact_policy` 和 `change_note`。
- 成功 200：`Success<PromptTemplateData>`。
- 错误 404：模板不存在。
- 错误 409：模板版本冲突。
- 错误 422：只读模板、未知变量或渠道规则无效。

### 12.3 POST `/prompt-templates/{template_id}/restore`

- 请求头：`X-CSRF-Token`；请求体为 `{ version: number }`。
- 成功 200：`Success<PromptTemplateData>`。
- 错误 404：模板不存在。
- 错误 409：模板版本冲突。
- 错误 422：只读模板不能恢复。

### 12.4 GET `/prompt-templates/{template_id}/versions`

- 请求：需会话认证。
- 成功 200：`Success<ItemsData[PromptTemplateVersionData]>`。
- 错误 404：模板不存在。

### 13.1 GET `/jobs/{job_id}`

- 请求：路径参数 `job_id: string`；无请求体。
- 成功 200：`Success<JobData>`。
- 错误 404：`ErrorResponse`，代码 40401，`message="任务不存在"`。

### 13.2 POST `/jobs/{job_id}/retry`

- 请求头：新的 `Idempotency-Key`；请求体 `{ reason: string }`。
- 成功 202：`Success<JobAccepted>`，返回新任务 ID。
- 错误 409：`ErrorResponse`，代码 40902，`message="任务不可重试或已达到最大重试次数"`。

### 13.3 POST `/jobs/{job_id}/cancel`

- 请求体：`{ reason: string }`。
- 成功 200：`Success<JobData>`，`status="cancelled"`。
- 错误 409：`ErrorResponse`，代码 40902，`message="任务已开始执行或已经结束，不能取消"`。

## 13. 兼容、事件与变更规则

- V1 不提供外部 Webhook、自动发布回调和消费者 AI 平台登录接口。
- 破坏性字段变更只能发布 `/api/v2`；v1 允许新增可空字段或新增枚举前先升级前端兼容逻辑。
- OpenAPI 文档必须由后端 Schema 生成，并通过测试与本文件中的方法、路径、状态码和字段比对。
- Mock 仅在开发模式启用；`VITE_USE_MOCK=false` 时所有页面必须命中真实 API。
- 所有模型、目录和提示词变更保留版本；历史任务按原版本可追溯。
- 导出文件成功响应是本契约唯一不使用 JSON 成功包络的接口。
