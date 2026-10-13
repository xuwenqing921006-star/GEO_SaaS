export type ClientStatus = "active" | "paused" | "archived";
export type ResultLevel = "L0" | "L1" | "L2" | "L3" | "L4";
export type ContactPolicy =
  "allow" | "official_only" | "omit" | "manual_review";
export type ContentFormCode =
  | "local_recommendation"
  | "selection_guide"
  | "practical_guide"
  | "service_explainer"
  | "scenario_solution"
  | "faq"
  | "local_presence"
  | "entity_profile"
  | "price_guide"
  | "service_process"
  | "comparison"
  | "case_study";

export interface ApiSuccess<T> {
  code: 200 | 201 | 202;
  message: "success" | "created" | "accepted";
  data: T;
  request_id: string;
}

export interface ApiErrorBody {
  code: number;
  message: string;
  data: {
    field_errors: { field: string; message: string }[];
    retryable: boolean;
    provider: "deepseek" | "qwen" | null;
    job_id: string | null;
  };
  request_id: string;
}

export interface SessionData {
  user: { id: string; username: string; display_name: string };
  csrf_token: string;
  expires_at: string;
}

export interface ClientSummary {
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
}

export interface ClientDetail extends ClientSummary {
  address: string;
  contact_phone: string | null;
  contact_wechat: string | null;
  business_hours: string | null;
  service_radius: string | null;
  cooperation_started_on: string;
  notes: string | null;
  created_at: string;
}

export interface ClientsPage {
  items: ClientSummary[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

export interface DashboardData {
  client: ClientSummary;
  counts: Record<
    | "materials"
    | "confirmed_facts"
    | "unresolved_conflicts"
    | "planned_contents"
    | "draft_contents"
    | "monitoring_samples_30d",
    number
  >;
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
  recent_jobs: unknown[];
}

export interface ClientFilters {
  q: string;
  status: ClientStatus | "";
  sort: "-updated_at" | "standard_name";
  page: number;
  page_size: number;
}

export interface CreateClientInput {
  standard_name: string;
  short_name: string | null;
  industry_code: string;
  province: string;
  city: string;
  district: string;
  address: string;
  contact_phone: string | null;
  contact_wechat: string | null;
  business_hours: string | null;
  service_radius: string | null;
  cooperation_started_on: string;
  notes: string | null;
}

export type AuthorizationStatus =
  "authorized" | "restricted" | "not_authorized" | "not_required";
export type FactStatus =
  | "confirmed"
  | "client_provided"
  | "external_source"
  | "inferred"
  | "conflict"
  | "private";

export interface MaterialData {
  id: string;
  client_id: string;
  file_name: string;
  media_type: string;
  size_bytes: number;
  sha256: string;
  category:
    | "license"
    | "service"
    | "price"
    | "team"
    | "case"
    | "channel"
    | "other"
    | "image";
  authorization_status: AuthorizationStatus;
  extraction_status:
    "not_started" | "queued" | "running" | "succeeded" | "failed";
  page_count: number | null;
  fragment_count: number;
  uploaded_at: string;
  file_url: string | null;
  version: number;
}

export interface EvidenceData {
  id: string;
  material_id: string | null;
  source_type: "material" | "manual" | "public_url";
  source_label: string;
  source_url: string | null;
  quote: string;
  observed_at: string;
  authorization_status: AuthorizationStatus;
}

export interface FactData {
  id: string;
  client_id: string;
  category:
    | "identity"
    | "location"
    | "service"
    | "audience"
    | "price"
    | "process"
    | "capability"
    | "case"
    | "contact"
    | "restriction";
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
}

export interface ConflictData {
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
}

export interface KnowledgeProfileData {
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
}

export interface DiagnosticRunData {
  id: string;
  client_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  current_level: ResultLevel;
  scores: Record<
    | "entity_completeness"
    | "evidence_coverage"
    | "content_coverage"
    | "source_coverage"
    | "ai_visibility",
    number | null
  >;
  scope: ("entity" | "evidence" | "content" | "source" | "visibility")[];
  monitoring_window_days: number;
  overall_score?: number | null;
  overall_grade?: "excellent" | "good" | "medium" | "poor" | null;
  evaluated_platform_count?: number;
  total_platform_count?: number;
  effective_sample_count?: number;
  platform_results?: {
    platform_id: string;
    platform_name: string;
    collection_mode: "api";
    status:
      | "unconfigured"
      | "untested"
      | "failed"
      | "not_found"
      | "brand_only"
      | "mentioned"
      | "associated"
      | "recommended";
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
      source_rate: number | null;
    };
    platform_note?: string;
    source_capability?: "available" | "no_sources" | "not_supported";
    source_count?: number;
    sources?: {
      index: number;
      title: string;
      url: string;
      site_name: string | null;
      snippet?: string | null;
      domain: string;
      channel_id: string;
      channel_name: string;
      question_ids: string[];
      question_labels: string[];
    }[];
    competitors?: {
      name: string;
      mention_count: number;
      recommendation_count: number;
      appeared_before_client_count: number;
      question_ids: string[];
      source_urls: string[];
      reasons: string[];
      answer_excerpts?: string[];
      source_evidence?: {
        title: string;
        url: string;
        site_name: string | null;
        snippet: string | null;
      }[];
    }[];
    channel_signals?: DiagnosticChannelSignal[];
    questions?: {
      id: string;
      family: string;
      label: string;
      text: string;
      answer_excerpt: string | null;
      status: "not_run" | "succeeded" | "failed";
      sources?: {
        index: number;
        title: string;
        url: string;
        site_name: string | null;
        snippet?: string | null;
      }[];
    }[];
  }[];
  competitive_insights?: {
    evidence_platform_count: number;
    source_count: number;
    competitors: {
      name: string;
      platform_count: number;
      platform_names: string[];
      mention_count: number;
      recommendation_count: number;
      appeared_before_client_count: number;
      source_count: number;
      source_urls: string[];
      reasons: string[];
      answer_excerpts: string[];
      source_evidence: {
        title: string;
        url: string;
        site_name: string | null;
        snippet: string | null;
      }[];
      strength_signals: {
        code: string;
        label: string;
        evidence: string;
      }[];
      recommended_actions: string[];
    }[];
    channel_signals: (DiagnosticChannelSignal & {
      platform_count: number;
      platform_names: string[];
    })[];
    advice: {
      type: "competitor_gap" | "channel_signal";
      title: string;
      reason: string;
      action: string;
      confidence: "high" | "medium" | "low";
      evidence_urls: string[];
    }[];
    methodology_note: string;
  };
  issues: {
    id: string;
    category: "entity" | "evidence" | "content" | "source" | "visibility";
    severity: "info" | "warning" | "blocking";
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
}

export type QuestionFamily =
  | "discovery"
  | "recommendation"
  | "scenario"
  | "comparison"
  | "brand_verification";
export interface StrategyItemData {
  id: string;
  kind: "keyword" | "question" | "cluster";
  text: string;
  family: QuestionFamily | null;
  keyword_type:
    | "core"
    | "decision"
    | "service"
    | "geo_longtail"
    | "local_service"
    | "brand"
    | "recommendation"
    | "scenario"
    | "service_detail"
    | "comparison"
    | "transaction"
    | "trust"
    | null;
  provenance:
    | "measured"
    | "client_provided"
    | "external_source"
    | "system_inference"
    | "ai_generated"
    | "system_migration_t027";
  target_level: ResultLevel;
  priority: 1 | 2 | 3;
  rationale: string;
  main_keyword?: string | null;
  user_intent?: string | null;
  recommended_content_type?: ContentFormCode | null;
  locked: boolean;
  selected?: boolean;
  active: boolean;
  generated_count?: number;
  version: number;
}
export interface ContentBriefData {
  id: string;
  client_id: string;
  title: string;
  content_type:
    | "local_recommendation"
    | "entity_profile"
    | "service_explainer"
    | "selection_guide"
    | "practical_guide"
    | "scenario_solution"
    | "faq"
    | "price_guide"
    | "service_process"
    | "comparison"
    | "case_study"
    | "local_presence"
    | "capability_proof"
    | "case"
    | "local_scenario";
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
  keyword_strategy_id?: string | null;
  keyword_type?: string | null;
  prompt_template_code?: string | null;
  prompt_template_version?: number | null;
  target_channel_id?: string | null;
  contact_policy?: ContactPolicy | null;
  prompt_layers_snapshot?: PromptLayerSnapshot[];
  contact_allowed_urls?: string[];
  version: number;
}
export type ContentStatus =
  | "brief"
  | "generating"
  | "draft"
  | "blocked"
  | "failed"
  | "checked"
  | "optimized"
  | "exported"
  | "published"
  | "archived";
export interface QualityCheckData {
  id: string;
  document_version_id: string;
  overall_status: "passed" | "warning" | "blocked";
  dimensions: {
    key:
      | "fact_consistency"
      | "question_relevance"
      | "entity_clarity"
      | "answer_extractability"
      | "source_traceability"
      | "natural_language"
      | "channel_fit"
      | "compliance";
    status: "passed" | "warning" | "blocked";
    score: number;
    explanation: string;
  }[];
  findings: {
    id: string;
    severity: "info" | "warning" | "blocking";
    category: string;
    message: string;
    paragraph_id: string | null;
    fact_id: string | null;
    suggested_fix: string;
  }[];
  provider: "deepseek" | "qwen" | "rules";
  model: string | null;
  created_at: string;
}
export interface DocumentVersionData {
  id: string;
  document_id: string;
  version_number: number;
  title: string;
  title_candidates?: {
    title: string;
    title_type:
      | "professional"
      | "scenario"
      | "local_decision"
      | "qa"
      | "brand_verification"
      | "custom";
  }[];
  body_markdown: string;
  change_type:
    | "generated"
    | "manual_edit"
    | "geo_optimized"
    | "naturalized"
    | "regenerated"
    | "restored"
    | "channel_variant";
  provider: "deepseek" | "qwen" | "user" | "rules";
  model: string | null;
  fact_snapshot_id: string;
  prompt_version: string | null;
  prompt_template_code: string | null;
  prompt_template_version: number | null;
  target_channel_id: string | null;
  contact_policy: ContactPolicy | null;
  prompt_layers_snapshot?: PromptLayerSnapshot[];
  contact_allowed_urls?: string[];
  contact_sanitization_report?: {
    policy?: ContactPolicy;
    changed?: boolean;
    removed_phone_or_wechat?: number;
    removed_qr_or_guidance?: number;
    removed_urls?: number;
    title_changed?: boolean;
    allowed_urls?: string[];
  };
  image_material_ids: string[];
  input_tokens: number;
  output_tokens: number;
  fallback_reason: string | null;
  created_at: string;
}
export interface ContentDocumentData {
  id: string;
  client_id: string;
  brief_id: string;
  generation_task_id: string | null;
  generation_task_confirmed_at: string | null;
  title: string;
  status: ContentStatus;
  generation_status: "pending" | "generating" | "generated" | "failed";
  publication_status:
    | "unpublished"
    | "queued"
    | "publishing"
    | "pending_review"
    | "published"
    | "failed"
    | "needs_login"
    | "needs_verification"
    | "rejected";
  publication_error: string | null;
  keyword?: string | null;
  keyword_type?: string | null;
  current_version: DocumentVersionData | null;
  latest_check: QualityCheckData | null;
  fact_snapshot: {
    id: string;
    brief_version: number;
    facts: {
      id: string;
      key: string;
      label: string;
      value: string;
      category: string;
      version?: number;
    }[];
    evidence: {
      id: string;
      fact_id: string;
      source_type: string;
      source_label: string;
      source_url: string | null;
      quote: string | null;
      observed_at: string;
    }[];
    brief_context: {
      title: string;
      content_type: string;
      target_keywords: string[];
      retest_questions: string[];
      target_level: ResultLevel;
      audience: string;
      angle: string;
      suggested_channel_ids: string[];
      expected_recommendation_reason: string;
      prompt_template_code?: string | null;
      prompt_template_version?: number | null;
      target_channel_id?: string | null;
      contact_policy?: ContactPolicy | null;
      prompt_layers_snapshot?: PromptLayerSnapshot[];
      contact_allowed_urls?: string[];
    };
    created_at: string;
  } | null;
  channel_variants: {
    id: string;
    channel_id: string;
    version_id: string;
    adaptation_note: string;
  }[];
  latest_publication: {
    id: string;
    document_version_id: string;
    channel_id: string | null;
    publishing_account_id?: string | null;
    account_name?: string | null;
    status:
      | "queued"
      | "publishing"
      | "pending_review"
      | "published"
      | "failed"
      | "needs_login"
      | "needs_verification"
      | "rejected";
    public_url: string | null;
    error_message: string | null;
    submitted_at: string | null;
    published_at: string | null;
  } | null;
  publications?: Array<NonNullable<ContentDocumentData["latest_publication"]>>;
  current_version_published: boolean;
  updated_at: string;
  version: number;
}
export interface ContentGenerationTaskData {
  id: string;
  client_id: string;
  platform_type: "self_media";
  keyword_snapshots: {
    id: string;
    text: string;
    keyword_type: string | null;
    main_keyword: string | null;
  }[];
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
  documents?: ContentDocumentData[];
}
export interface StrategyBundleData {
  client_id: string;
  diagnostic_run_id: string | null;
  items: StrategyItemData[];
  briefs: ContentBriefData[];
  prompt_template_code?: string | null;
  prompt_template_version?: number | null;
  generated_at: string;
  version: number;
}

export type KeywordType =
  | "local_service"
  | "brand"
  | "recommendation"
  | "scenario"
  | "service_detail"
  | "comparison"
  | "transaction"
  | "trust";

export interface KeywordProfileData {
  primary_keyword: string;
  regions: string[];
  secondary_keywords: string[];
  keyword_types: KeywordType[];
  recommended_count: number;
  knowledge_fingerprint: string;
  version: number;
  updated_at: string | null;
  inferred: boolean;
}

export interface KeywordCandidateData {
  id: string;
  generation_id: string;
  text: string;
  normalized_text: string;
  main_keyword: string;
  keyword_type: KeywordType;
  user_intent: string;
  region: string | null;
  secondary_keyword: string | null;
  recommended_content_type: string;
  priority: 1 | 2 | 3;
  selected: boolean;
  active: boolean;
  confirmed_item_id: string | null;
  version: number;
}

export interface KeywordGenerationData {
  id: string;
  client_id: string;
  job_id: string | null;
  primary_keyword: string;
  regions: string[];
  secondary_keywords: string[];
  keyword_types: KeywordType[];
  target_count: number;
  status:
    "queued" | "running" | "awaiting_confirmation" | "confirmed" | "failed";
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
}

export interface ConfirmedKeywordData {
  id: string;
  text: string;
  keyword_type: KeywordType | null;
  main_keyword: string | null;
  selected: boolean;
  active: boolean;
  version: number;
}

export interface KeywordWorkspaceData {
  profile: KeywordProfileData;
  generations: KeywordGenerationData[];
  confirmed_keywords: ConfirmedKeywordData[];
}

export interface KeywordGenerationAcceptedData {
  job_id: string;
  generation_id: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  progress: number;
}

export interface JobData {
  id: string;
  client_id: string;
  type:
    | "material_extract"
    | "diagnostic"
    | "strategy_generate"
    | "document_operation"
    | "content_publish"
    | "channel_recommend"
    | "monitoring_batch";
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  progress: number;
  current_step: string;
  attempt: number;
  max_attempts: number;
  error_message: string | null;
  retryable: boolean;
  result_resource_type?: "material" | "document" | "export" | null;
  result_resource_id?: string | null;
}

export interface PublishingChannelData {
  id: "toutiao" | "baijia" | "netease" | "sohu" | "penguin" | "yidian";
  name: string;
  description: string;
  official_url: string;
  login_url: string;
  manage_url: string;
  implementation_status: "available";
  generation_spec: {
    channel_id: PublishingChannelData["id"];
    channel_name: string;
    title_min_characters: number;
    title_max_characters: number;
    generation_title_max_characters: number;
    minimum_body_characters: number;
    summary_max_characters: number | null;
    daily_publication_limit: number | null;
    content_requirements: string[];
    image_requirements: {
      cover_width: number;
      cover_height: number;
      maximum_bytes: number;
      allowed_formats: string[];
      target_body_images: number;
      minimum_body_images: number;
      maximum_body_images: number;
      requirement: string;
      cover_source: "upload" | "body";
    };
    verified_at: string;
    source_urls: string[];
  } | null;
  can_configure: boolean;
  max_accounts: 5;
  account_count: number;
  connected_count: number;
  enabled_count: number;
  attention_count: number;
  accounts: PublishingAccountData[];
}

export interface PublishingAccountData {
  id: string;
  channel_id: PublishingChannelData["id"];
  display_name: string;
  enabled: boolean;
  connection_status:
    | "disconnected"
    | "awaiting_login"
    | "connected"
    | "needs_login"
    | "needs_verification"
    | "error";
  account_name: string | null;
  last_checked_at: string | null;
  last_error: string | null;
  session_health:
    | "healthy"
    | "check_due_soon"
    | "check_due"
    | "awaiting_login"
    | "expired"
    | "verification_required"
    | "error"
    | "not_checked";
  session_health_label: string;
  session_health_message: string;
  next_automatic_check_at: string | null;
  automatic_check_interval_hours: 24;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface ChannelData {
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
  contact_policy: ContactPolicy;
  contact_policy_label: string;
  contact_policy_note: string;
}

export interface ChannelRecommendationData {
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
}

export interface PlatformData {
  id: string;
  name: string;
  mode: "api" | "manual_consumer";
  priority: "P0" | "P1";
  provider: ProviderName | null;
  consumer_entry_url: string;
  sample_count_default: number;
  active: boolean;
  verified_on: string;
  mode_label: string;
  note: string;
}

export type MonitoringQuestionFamily =
  | "category_discovery"
  | "recommendation"
  | "scenario"
  | "comparison"
  | "brand_verification";

export interface MonitoringQuestionData {
  id: string;
  text: string;
  family: MonitoringQuestionFamily;
  is_brand_query: boolean;
  target_level: "L1" | "L2" | "L3";
  priority: number;
}

export interface MonitoringQuestionSetData {
  id: string;
  client_id: string;
  name: string;
  frozen: boolean;
  questions: MonitoringQuestionData[];
  version: number;
  created_at: string;
  updated_at: string;
}

export interface MonitoringEvaluationData {
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
  suggested_actions?: {
    action_type:
      | "add_fact_task"
      | "add_content_brief"
      | "update_channel_priority"
      | "increase_sample";
    title: string;
    reason: string;
    target_level: ResultLevel;
    target_page: "P02" | "P04" | "P06" | "P07";
  }[];
}

export interface MonitoringSampleData {
  id: string;
  batch_id: string;
  platform_id: string;
  platform_name: string;
  collection_mode: "api" | "manual_consumer";
  question_id: string;
  question_text: string;
  question_family: MonitoringQuestionFamily;
  is_brand_query: boolean;
  priority: number;
  attempt: number;
  status: "succeeded" | "failed" | "not_executed";
  raw_answer: string | null;
  asked_at: string | null;
  failure_reason: string | null;
  evaluation: MonitoringEvaluationData | null;
}

export interface MonitoringBatchData {
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
}

export interface MonitoringMetricDetail {
  numerator: number | null;
  denominator: number | null;
  rate: number | null;
}
export interface MonitoringSummaryData {
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
  mode_breakdown: Partial<
    Record<
      "api" | "manual_consumer",
      Omit<MonitoringSummaryData, "mode_breakdown">
    >
  >;
}
export type MonitoringMetricsData = MonitoringBatchData["summary"] & {
  time_range: { from: string; to: string };
  platform_ids: string[];
  question_families: MonitoringQuestionFamily[];
};

export interface OptimizationActionData {
  id: string;
  client_id: string;
  source: "monitoring_feedback" | "monitoring_evaluation";
  source_id: string;
  action_type:
    | "add_fact_task"
    | "add_content_brief"
    | "update_channel_priority"
    | "increase_sample";
  title: string;
  reason: string;
  target_level: "L1" | "L2" | "L3";
  target_page: "P02" | "P04" | "P06" | "P07";
  status: "open";
  created_at: string;
}

export interface DiagnosticChannelSignal {
  channel_id: string;
  channel_name: string;
  signal_score: number;
  confidence: "high" | "medium" | "low";
  source_count: number;
  question_count: number;
  competitor_reference_count: number;
  evidence: {
    title: string;
    url: string;
    platform_name?: string;
  }[];
}

export type ProviderName =
  "qwen" | "deepseek" | "doubao" | "wenxin" | "yuanbao" | "kimi";
export interface ProviderSettingData {
  provider: ProviderName;
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
}

export interface RuntimeSettingData {
  timezone: "Asia/Shanghai";
  max_upload_mb: 30;
  max_upload_files: 20;
  job_retry_limit: 3;
  job_poll_seconds: 2;
  default_client_monthly_budget_cny_fen: number;
  version: number;
}

export interface SettingsData {
  providers: ProviderSettingData[];
  runtime: RuntimeSettingData;
  catalogs: {
    provider_catalog_version: string;
    model_policy_version: string;
  };
}

export interface ProviderTestData {
  provider: ProviderName;
  status: "success";
  model: string;
  latency_ms: number;
  structured_output_valid: boolean;
  budget_warning: boolean;
}

export type PromptCategory =
  | "guardrail"
  | "base"
  | "content_form"
  | "keyword_strategy"
  | "channel_adapter";

export interface PromptLayerSnapshot {
  template_id?: string;
  code: string;
  name?: string;
  category?: PromptCategory;
  version_number: number;
  contact_policy?: ContactPolicy | null;
  channel_id?: string | null;
  source_url?: string | null;
  verified_at?: string | null;
  applied_as?: string;
}

export interface PromptTemplateData {
  id: string;
  code: string;
  category: PromptCategory;
  name: string;
  description: string;
  template_text: string;
  editable: boolean;
  active: boolean;
  variable_keys: string[];
  required_fact_keys: string[];
  contact_policy: ContactPolicy | null;
  default_contact_policy?: ContactPolicy | null;
  channel_id: string | null;
  source_url: string | null;
  verified_at: string | null;
  current_version: number;
  version: number;
  updated_at: string;
}

export interface PromptTemplateVersionData {
  id: string;
  template_id: string;
  version_number: number;
  template_text: string;
  contact_policy: ContactPolicy | null;
  change_note: string;
  created_at: string;
}

export interface PromptTemplateListData {
  items: PromptTemplateData[];
  available_variables: string[];
  guardrails: {
    editable: false;
    summary: string;
  };
}
