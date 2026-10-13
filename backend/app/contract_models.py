from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas import ApiEnvelope

ResultLevel = Literal["L0", "L1", "L2", "L3", "L4"]
QuestionFamily = Literal[
    "discovery",
    "recommendation",
    "scenario",
    "comparison",
    "brand_verification",
]
MonitoringQuestionFamily = Literal[
    "category_discovery",
    "recommendation",
    "scenario",
    "comparison",
    "brand_verification",
]
ContentType = Literal[
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


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PageData[DataT](ContractModel):
    items: list[DataT]
    total: int
    page: int
    page_size: int
    has_next: bool


class UserData(ContractModel):
    id: str
    username: str
    display_name: str


class SessionData(ContractModel):
    user: UserData
    csrf_token: str
    expires_at: str


class LoggedOutData(ContractModel):
    logged_out: Literal[True]


class PasswordChangedData(ContractModel):
    changed: Literal[True]
    relogin_required: Literal[True]


class ClientSummary(ContractModel):
    id: str
    standard_name: str
    short_name: str | None
    industry_code: str
    industry_name: str
    province: str
    city: str
    district: str
    status: Literal["active", "paused", "archived"]
    current_level: ResultLevel
    fact_completeness: float
    blocking_issue_count: int
    next_action: str
    updated_at: str
    version: int


class ClientDetail(ClientSummary):
    address: str
    contact_phone: str | None
    contact_wechat: str | None
    business_hours: str | None
    service_radius: str | None
    cooperation_started_on: str
    notes: str | None
    created_at: str


class DashboardCounts(ContractModel):
    materials: int
    confirmed_facts: int
    unresolved_conflicts: int
    planned_contents: int
    draft_contents: int
    monitoring_samples_30d: int


class LevelProgress(ContractModel):
    current: ResultLevel
    next: ResultLevel | None
    missing_conditions: list[str]


class NextActionData(ContractModel):
    id: str
    title: str
    reason: str
    target_level: ResultLevel
    target_page: Literal["P02", "P03", "P04", "P05", "P06", "P07"]
    priority: Literal[1, 2, 3]


class JobData(ContractModel):
    id: str
    client_id: str | None
    type: Literal[
        "material_extract",
        "diagnostic",
        "strategy_generate",
        "document_operation",
        "content_publish",
        "channel_recommend",
        "monitoring_batch",
    ]
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    progress: int
    current_step: str
    attempt: int
    max_attempts: int
    result_resource_type: str | None
    result_resource_id: str | None
    error_code: int | None
    error_message: str | None
    retryable: bool
    created_at: str
    started_at: str | None
    finished_at: str | None


class JobAccepted(ContractModel):
    job_id: str
    status: Literal["queued"]
    progress: Literal[0]


class DashboardData(ContractModel):
    client: ClientSummary
    counts: DashboardCounts
    level_progress: LevelProgress
    next_actions: list[NextActionData]
    recent_jobs: list[JobData]


class MaterialData(ContractModel):
    id: str
    client_id: str
    file_name: str
    media_type: str
    size_bytes: int
    sha256: str
    category: Literal[
        "license",
        "service",
        "price",
        "team",
        "case",
        "channel",
        "other",
        "image",
    ]
    authorization_status: Literal["authorized", "restricted", "not_authorized", "not_required"]
    extraction_status: Literal["not_started", "queued", "running", "succeeded", "failed"]
    page_count: int | None
    fragment_count: int
    uploaded_at: str
    file_url: str | None
    version: int


class MaterialsCreatedData(ContractModel):
    items: list[MaterialData]


class MaterialFragmentData(ContractModel):
    id: str
    page: int | None
    text: str
    extraction_method: Literal["text", "ocr", "manual"]


class MaterialDetailData(ContractModel):
    material: MaterialData
    fragments: list[MaterialFragmentData]


class MaterialDeletedData(ContractModel):
    id: str
    deleted: Literal[True]


class EvidenceData(ContractModel):
    id: str
    material_id: str | None
    source_type: Literal["material", "manual", "public_url"]
    source_label: str
    source_url: str | None
    quote: str
    observed_at: str
    authorization_status: Literal["authorized", "restricted", "not_authorized", "not_required"]


class FactData(ContractModel):
    id: str
    client_id: str
    category: Literal[
        "identity",
        "location",
        "service",
        "audience",
        "price",
        "process",
        "capability",
        "case",
        "contact",
        "restriction",
    ]
    key: str
    label: str
    value: str
    status: Literal[
        "confirmed",
        "client_provided",
        "external_source",
        "inferred",
        "conflict",
        "private",
    ]
    confidence: float
    valid_from: str | None
    valid_until: str | None
    evidence: list[EvidenceData]
    version: int
    updated_at: str


class ConflictCandidateData(ContractModel):
    value: str
    source_label: str
    evidence_id: str | None


class ConflictData(ContractModel):
    id: str
    client_id: str
    fact_key: str
    label: str
    candidates: list[ConflictCandidateData]
    status: Literal["open", "resolved", "ignored"]
    resolved_value: str | None
    resolution_note: str | None
    version: int


class ItemsData[DataT](ContractModel):
    items: list[DataT]


class ServiceData(ContractModel):
    id: str
    name: str
    description: str
    target_audience: str
    price_statement: str | None
    limitations: list[str]
    active: bool


class CapabilityData(ContractModel):
    id: str
    type: str
    title: str
    description: str
    evidence_ids: list[str]
    authorization_status: Literal["authorized", "restricted", "not_authorized", "not_required"]


class ProhibitedClaimData(ContractModel):
    id: str
    phrase: str
    reason: str
    source: Literal["system", "user"]


class ExternalPresenceData(ContractModel):
    id: str
    platform: str
    account_name: str
    public_url: str
    ownership: Literal["operator", "client", "partner"]
    verified_on: str


class MissingQuestionData(ContractModel):
    id: str
    field_key: str
    question: str
    reason: str
    blocking: bool


class KnowledgeProfileData(ContractModel):
    client_id: str
    services: list[ServiceData]
    capabilities: list[CapabilityData]
    prohibited_claims: list[ProhibitedClaimData]
    external_presences: list[ExternalPresenceData]
    missing_questions: list[MissingQuestionData]
    version: int


class DiagnosticScores(ContractModel):
    entity_completeness: float | None
    evidence_coverage: float | None
    content_coverage: float | None
    source_coverage: float | None
    ai_visibility: float | None


class DiagnosticIssueData(ContractModel):
    id: str
    category: Literal["entity", "evidence", "content", "source", "visibility"]
    severity: Literal["info", "warning", "blocking"]
    title: str
    explanation: str
    evidence_ids: list[str]
    suggested_action: str
    target_page: Literal["P02", "P04", "P05", "P06", "P07"]
    status: Literal["open", "resolved", "ignored"]
    version: int


class PlatformVisibilityMetrics(ContractModel):
    mention_rate: float | None
    association_rate: float | None
    recommendation_rate: float | None
    accuracy_rate: float | None
    source_rate: float | None


class DiagnosticProbeQuestionData(ContractModel):
    id: str
    family: str
    label: str
    text: str
    answer_excerpt: str | None
    status: Literal["not_run", "succeeded", "failed"]


class PlatformVisibilityData(ContractModel):
    platform_id: str
    platform_name: str
    collection_mode: Literal["api"]
    status: Literal[
        "unconfigured",
        "untested",
        "failed",
        "not_found",
        "mentioned",
        "associated",
        "recommended",
    ]
    score: float | None
    grade: Literal["excellent", "good", "medium", "poor"] | None
    comment: str
    valid_sample_count: int
    measured_at: str | None
    metrics: PlatformVisibilityMetrics
    questions: list[DiagnosticProbeQuestionData] = []
    platform_note: str | None = None


class DiagnosticRunData(ContractModel):
    id: str
    client_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    current_level: ResultLevel
    scores: DiagnosticScores
    scope: list[Literal["entity", "evidence", "content", "source", "visibility"]] = []
    monitoring_window_days: int = 30
    overall_score: float | None
    overall_grade: Literal["excellent", "good", "medium", "poor"] | None
    evaluated_platform_count: int
    total_platform_count: int
    effective_sample_count: int
    platform_results: list[PlatformVisibilityData]
    issues: list[DiagnosticIssueData]
    fact_snapshot_id: str
    is_stale: bool
    changed_fact_count: int
    completed_at: str | None


class StrategyItemData(ContractModel):
    id: str
    kind: Literal["keyword", "question", "cluster"]
    text: str
    family: QuestionFamily | None
    keyword_type: (
        Literal[
            "core",
            "decision",
            "service",
            "geo_longtail",
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
    )
    provenance: Literal[
        "measured",
        "client_provided",
        "external_source",
        "system_inference",
        "ai_generated",
    ]
    target_level: ResultLevel
    priority: Literal[1, 2, 3]
    rationale: str
    main_keyword: str | None
    user_intent: str | None
    recommended_content_type: str | None
    locked: bool
    selected: bool
    active: bool
    generated_count: int
    version: int


class ContentBriefData(ContractModel):
    id: str
    client_id: str
    title: str
    content_type: ContentType
    target_question_ids: list[str]
    target_keywords: list[str]
    target_level: ResultLevel
    audience: str
    angle: str
    required_fact_ids: list[str]
    required_evidence_ids: list[str]
    expected_recommendation_reason: str
    prohibited_claims: list[str]
    retest_questions: list[str]
    suggested_channel_ids: list[str]
    priority: Literal[1, 2, 3]
    status: Literal["planned", "in_production", "completed", "archived"]
    keyword_strategy_id: str | None
    keyword_type: str | None
    prompt_template_code: str | None
    prompt_template_version: int | None
    target_channel_id: str | None
    contact_policy: str | None
    prompt_layers_snapshot: list[dict[str, object]]
    contact_allowed_urls: list[str]
    version: int


class StrategyBundleData(ContractModel):
    client_id: str
    diagnostic_run_id: str | None
    items: list[StrategyItemData]
    briefs: list[ContentBriefData]
    prompt_template_code: str | None
    prompt_template_version: int | None
    generated_at: str
    version: int


class KeywordProfileData(ContractModel):
    primary_keyword: str
    regions: list[str]
    secondary_keywords: list[str]
    keyword_types: list[
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
    ]
    recommended_count: int
    knowledge_fingerprint: str
    version: int
    updated_at: str | None
    inferred: bool


class KeywordCandidateData(ContractModel):
    id: str
    generation_id: str
    text: str
    normalized_text: str
    main_keyword: str
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
    user_intent: str
    region: str | None
    secondary_keyword: str | None
    recommended_content_type: str
    priority: Literal[1, 2, 3]
    selected: bool
    active: bool
    confirmed_item_id: str | None
    version: int


class KeywordGenerationData(ContractModel):
    id: str
    client_id: str
    job_id: str | None
    primary_keyword: str
    regions: list[str]
    secondary_keywords: list[str]
    keyword_types: list[str]
    target_count: int
    status: Literal[
        "queued",
        "running",
        "awaiting_confirmation",
        "confirmed",
        "failed",
    ]
    generated_count: int
    filtered_count: int
    confirmed_count: int
    error_message: str | None
    archived: bool
    created_at: str
    completed_at: str | None
    confirmed_at: str | None
    version: int
    candidates: list[KeywordCandidateData] | None = None


class ConfirmedKeywordData(ContractModel):
    id: str
    text: str
    keyword_type: str | None
    main_keyword: str | None
    selected: bool
    active: bool
    version: int


class KeywordWorkspaceData(ContractModel):
    profile: KeywordProfileData
    generations: list[KeywordGenerationData]
    confirmed_keywords: list[ConfirmedKeywordData]


class KeywordGenerationAcceptedData(ContractModel):
    job_id: str
    generation_id: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    progress: int


class QualityDimensionData(ContractModel):
    key: Literal[
        "fact_consistency",
        "question_relevance",
        "entity_clarity",
        "answer_extractability",
        "source_traceability",
        "natural_language",
        "channel_fit",
        "compliance",
    ]
    status: Literal["passed", "warning", "blocked"]
    score: float
    explanation: str


class QualityFindingData(ContractModel):
    id: str
    severity: Literal["info", "warning", "blocking"]
    category: str
    message: str
    paragraph_id: str | None
    fact_id: str | None
    suggested_fix: str


class QualityCheckData(ContractModel):
    id: str
    document_version_id: str
    overall_status: Literal["passed", "warning", "blocked"]
    dimensions: list[QualityDimensionData]
    findings: list[QualityFindingData]
    provider: Literal["deepseek", "qwen", "rules"]
    model: str | None
    created_at: str


class DocumentVersionData(ContractModel):
    id: str
    document_id: str
    version_number: int
    title: str
    body_markdown: str
    change_type: Literal[
        "generated",
        "manual_edit",
        "geo_optimized",
        "naturalized",
        "regenerated",
        "restored",
        "channel_variant",
    ]
    provider: Literal["deepseek", "qwen", "user", "rules"]
    model: str | None
    fact_snapshot_id: str
    prompt_version: str | None
    prompt_template_code: str | None
    prompt_template_version: int | None
    target_channel_id: str | None
    contact_policy: Literal["allow", "official_only", "omit", "manual_review"] | None
    prompt_layers_snapshot: list[dict[str, object]]
    contact_allowed_urls: list[str]
    contact_sanitization_report: dict[str, object]
    image_material_ids: list[str]
    input_tokens: int = 0
    output_tokens: int = 0
    fallback_reason: str | None = None
    created_at: str


class ChannelVariantData(ContractModel):
    id: str
    channel_id: str
    version_id: str
    adaptation_note: str


class PublicationData(ContractModel):
    id: str
    document_version_id: str
    channel_id: str | None
    publishing_account_id: str | None = None
    account_name: str | None = None
    status: Literal[
        "queued",
        "publishing",
        "pending_review",
        "published",
        "failed",
        "needs_login",
        "needs_verification",
        "rejected",
    ]
    public_url: str | None
    error_message: str | None
    submitted_at: str | None
    published_at: str | None


class DocumentData(ContractModel):
    id: str
    client_id: str
    brief_id: str
    generation_task_id: str | None
    generation_task_confirmed_at: str | None
    title: str
    status: Literal[
        "brief",
        "generating",
        "draft",
        "blocked",
        "failed",
        "checked",
        "optimized",
        "exported",
        "published",
        "archived",
    ]
    generation_status: Literal["pending", "generating", "generated", "failed"]
    publication_status: Literal[
        "unpublished",
        "queued",
        "publishing",
        "pending_review",
        "published",
        "failed",
        "needs_login",
        "needs_verification",
        "rejected",
    ]
    publication_error: str | None
    keyword: str | None
    keyword_type: str | None
    current_version: DocumentVersionData | None
    latest_check: QualityCheckData | None
    fact_snapshot: dict[str, object] | None = None
    channel_variants: list[ChannelVariantData]
    latest_publication: PublicationData | None
    publications: list[PublicationData] = []
    current_version_published: bool
    updated_at: str
    version: int


class ContentGenerationTaskData(ContractModel):
    id: str
    client_id: str
    platform_type: Literal["self_media"]
    keyword_snapshots: list[dict[str, object]]
    channel_ids: list[str]
    article_count_per_channel: int
    length: Literal["short", "medium", "long"]
    content_form_codes: list[str]
    total_count: int
    completed_count: int
    failed_count: int
    progress: int
    status: Literal["queued", "generating", "completed", "partial", "failed"]
    confirmed_at: str | None
    created_at: str
    version: int
    documents: list[DocumentData] = Field(default_factory=list)


class DocumentsCreatedData(ContractModel):
    task: ContentGenerationTaskData
    items: list[DocumentData]
    total: int


class ChannelData(ContractModel):
    id: str
    name: str
    official_url: str
    ownership: Literal["operator_publishable", "client_required", "partner_cooperation"]
    access: Literal["public_web", "mostly_in_app", "mixed"]
    cost: Literal["free", "optional_paid", "paid"]
    ecosystem_tags: list[str]
    supported_content_types: list[str]
    client_requirements: list[str]
    risks: list[str]
    verified_on: str
    priority: Literal["P0", "P1", "P2"]
    active: bool
    contact_policy: Literal["allow", "official_only", "omit", "manual_review"]
    contact_policy_label: str
    contact_policy_note: str


class ChannelCatalogData(ContractModel):
    items: list[ChannelData]
    catalog_version: str


class PublishingAccountData(ContractModel):
    id: str
    channel_id: Literal["toutiao", "baijia", "netease", "sohu", "penguin", "yidian"]
    display_name: str
    enabled: bool
    connection_status: Literal[
        "disconnected",
        "awaiting_login",
        "connected",
        "needs_login",
        "needs_verification",
        "error",
    ]
    account_name: str | None
    last_checked_at: str | None
    last_error: str | None
    session_health: Literal[
        "healthy",
        "check_due_soon",
        "check_due",
        "awaiting_login",
        "expired",
        "verification_required",
        "error",
        "not_checked",
    ]
    session_health_label: str
    session_health_message: str
    next_automatic_check_at: str | None
    automatic_check_interval_hours: Literal[24]
    version: int
    created_at: str
    updated_at: str


class PublishingChannelData(ContractModel):
    id: Literal["toutiao", "baijia", "netease", "sohu", "penguin", "yidian"]
    name: str
    description: str
    official_url: str
    login_url: str
    manage_url: str
    implementation_status: Literal["available"]
    can_configure: bool
    max_accounts: Literal[5]
    account_count: int
    connected_count: int
    enabled_count: int
    attention_count: int
    accounts: list[PublishingAccountData]


class PublishingChannelListData(ContractModel):
    items: list[PublishingChannelData]


class PublicationBatchJobData(JobAccepted):
    account_id: str
    account_name: str
    channel_id: Literal["toutiao", "baijia", "netease", "sohu", "penguin", "yidian"]


class PublicationBatchAccepted(ContractModel):
    items: list[PublicationBatchJobData]
    queued_count: int


class ChannelRecommendationData(ContractModel):
    id: str
    client_id: str
    generation_id: str | None
    brief_id: str | None
    brief_title: str
    brief_content_type: ContentType | None
    content_document_id: str | None
    channel: ChannelData
    priority: Literal[1, 2, 3]
    fit_score: float
    reasons: list[str]
    recommended_content_types: list[str]
    required_actions: list[str]
    required_adaptation: str
    account_positioning: str
    authorization_note: str
    cost_note: str
    risk_note: str
    target_ecosystems: list[str]
    catalog_version: str
    caveat: str
    generated_at: str


class RecommendationListData(ContractModel):
    items: list[ChannelRecommendationData]
    generated_at: str | None


class PlatformData(ContractModel):
    id: str
    name: str
    mode: Literal["api", "manual_consumer"]
    priority: Literal["P0", "P1"]
    provider: Literal["deepseek", "qwen", "doubao"] | None
    consumer_entry_url: str | None
    sample_count_default: int
    active: bool
    verified_on: str
    mode_label: str = ""
    note: str = ""


class PlatformCatalogData(ContractModel):
    items: list[PlatformData]
    catalog_version: str


class MonitoringQuestionData(ContractModel):
    id: str
    text: str
    family: MonitoringQuestionFamily
    is_brand_query: bool
    expected_facts: list[str] = []
    target_level: Literal["L1", "L2", "L3"]
    priority: int = 1


class QuestionSetData(ContractModel):
    id: str
    client_id: str
    name: str
    frozen: bool
    questions: list[MonitoringQuestionData]
    version: int
    created_at: str = ""
    updated_at: str


class SuggestedMonitoringActionData(ContractModel):
    action_type: Literal[
        "add_fact_task",
        "add_content_brief",
        "update_channel_priority",
        "increase_sample",
    ]
    title: str
    reason: str
    target_level: Literal["L1", "L2", "L3"]
    target_page: Literal["P02", "P04", "P06", "P07"]


class SampleEvaluationData(ContractModel):
    id: str
    sample_id: str
    brand_found: bool
    correctly_associated: bool
    recommended: bool
    recommendation_supported: bool | None
    facts_accurate: bool | None
    source_visible: bool
    mentioned_name: str | None
    reasons: list[str]
    incorrect_facts: list[dict[str, object]]
    visible_sources: list[dict[str, object]]
    note: str | None
    evaluator: Literal["system", "user"]
    version: int
    updated_at: str
    suggested_actions: list[SuggestedMonitoringActionData] = []


class MonitoringSampleData(ContractModel):
    id: str
    batch_id: str
    platform_id: str
    platform_name: str
    collection_mode: Literal["api", "manual_consumer"]
    question_id: str
    question_text: str
    question_family: MonitoringQuestionFamily
    is_brand_query: bool
    priority: int
    attempt: int
    status: Literal["succeeded", "failed", "not_executed"]
    raw_answer: str | None
    asked_at: str | None
    failure_reason: str | None
    evaluation: SampleEvaluationData | None


class MonitoringMetricDetail(ContractModel):
    numerator: int | None
    denominator: int | None
    rate: float | None


class MonitoringSummaryData(ContractModel):
    sample_count: int
    effective_sample_count: int
    failed_count: int
    not_executed_count: int
    brand_found_rate: float | None
    correct_association_rate: float | None
    recommendation_rate: float | None
    recommendation_supported_rate: float | None
    fact_accuracy_rate: float | None
    source_coverage_rate: float | None
    repeat_appearance_rate: float | None
    metric_details: dict[str, MonitoringMetricDetail]
    mode_breakdown: dict[str, dict[str, object]]


class MonitoringBatchData(ContractModel):
    id: str
    client_id: str
    question_set_id: str
    question_set_version: int
    status: Literal["queued", "running", "partial", "succeeded", "failed"]
    platform_ids: list[str]
    api_sample_count: int
    created_at: str
    completed_at: str | None
    samples: list[MonitoringSampleData]
    summary: MonitoringSummaryData


class MonitoringMetricsData(MonitoringSummaryData):
    time_range: dict[str, str]
    platform_ids: list[str]
    question_families: list[MonitoringQuestionFamily]


class OptimizationFeedbackData(ContractModel):
    id: str
    action_type: str
    target_page: Literal["P02", "P04", "P06", "P07"]
    converted_record_type: Literal["optimization_action"]
    converted_record_id: str


class OptimizationActionData(ContractModel):
    id: str
    client_id: str
    source: Literal["monitoring_feedback", "monitoring_evaluation"]
    source_id: str
    action_type: Literal[
        "add_fact_task",
        "add_content_brief",
        "update_channel_priority",
        "increase_sample",
    ]
    title: str
    reason: str
    target_level: Literal["L1", "L2", "L3"]
    target_page: Literal["P02", "P04", "P06", "P07"]
    status: Literal["open"]
    created_at: str


class ProviderSettingData(ContractModel):
    provider: Literal["deepseek", "doubao", "yuanbao", "qwen", "kimi"]
    enabled: bool
    base_url: str
    workspace_id: str | None
    writer_model: str | None
    reviewer_model: str | None
    fallback_model: str | None
    daily_budget_cny_fen: int
    timeout_seconds: int
    secret_configured: bool
    secret_mask: str | None
    last_tested_at: str | None
    last_test_status: Literal["success", "failed", "not_tested"]
    version: int


class RuntimeSettingsData(ContractModel):
    timezone: Literal["Asia/Shanghai"]
    max_upload_mb: Literal[30]
    max_upload_files: Literal[20]
    job_retry_limit: Literal[3]
    job_poll_seconds: Literal[2]
    default_client_monthly_budget_cny_fen: int
    version: int


class CatalogVersionsData(ContractModel):
    industry_template_version: str | None = None
    prompt_template_version: str | None = None
    channel_catalog_version: str | None = None
    platform_catalog_version: str | None = None
    provider_catalog_version: str | None = None
    model_policy_version: str | None = None


class SettingsData(ContractModel):
    providers: list[ProviderSettingData]
    runtime: RuntimeSettingsData
    catalogs: CatalogVersionsData


class ProviderTestData(ContractModel):
    provider: Literal["deepseek", "doubao", "yuanbao", "qwen", "kimi"]
    status: Literal["success"]
    model: str
    latency_ms: int
    structured_output_valid: bool
    budget_warning: bool = False


class PromptTemplateData(ContractModel):
    id: str
    code: str
    category: Literal[
        "guardrail",
        "base",
        "content_form",
        "keyword_strategy",
        "channel_adapter",
    ]
    name: str
    description: str
    template_text: str
    editable: bool
    active: bool
    variable_keys: list[str]
    required_fact_keys: list[str]
    contact_policy: (
        Literal[
            "allow",
            "official_only",
            "omit",
            "manual_review",
        ]
        | None
    )
    default_contact_policy: (
        Literal[
            "allow",
            "official_only",
            "omit",
            "manual_review",
        ]
        | None
    )
    channel_id: str | None
    source_url: str | None
    verified_at: str | None
    current_version: int
    version: int
    updated_at: str


class PromptGuardrailsData(ContractModel):
    editable: Literal[False]
    summary: str


class PromptTemplateListData(ContractModel):
    items: list[PromptTemplateData]
    available_variables: list[str]
    guardrails: PromptGuardrailsData


class PromptTemplateVersionData(ContractModel):
    id: str
    template_id: str
    version_number: int
    template_text: str
    contact_policy: (
        Literal[
            "allow",
            "official_only",
            "omit",
            "manual_review",
        ]
        | None
    )
    change_note: str
    created_at: str


SUCCESS_DATA_MODELS: dict[tuple[str, str], type[BaseModel] | object] = {
    ("post", "/api/v1/auth/login"): SessionData,
    ("get", "/api/v1/auth/session"): SessionData,
    ("delete", "/api/v1/auth/session"): LoggedOutData,
    ("put", "/api/v1/auth/password"): PasswordChangedData,
    ("get", "/api/v1/clients"): PageData[ClientSummary],
    ("post", "/api/v1/clients"): ClientDetail,
    ("get", "/api/v1/clients/{client_id}"): ClientDetail,
    ("patch", "/api/v1/clients/{client_id}"): ClientDetail,
    ("post", "/api/v1/clients/{client_id}/archive"): ClientDetail,
    ("post", "/api/v1/clients/{client_id}/restore"): ClientDetail,
    ("get", "/api/v1/clients/{client_id}/dashboard"): DashboardData,
    ("get", "/api/v1/clients/{client_id}/materials"): PageData[MaterialData],
    ("post", "/api/v1/clients/{client_id}/materials"): MaterialsCreatedData,
    ("get", "/api/v1/materials/{material_id}"): MaterialDetailData,
    ("delete", "/api/v1/materials/{material_id}"): MaterialDeletedData,
    ("post", "/api/v1/materials/{material_id}/extract"): JobAccepted,
    ("get", "/api/v1/clients/{client_id}/facts"): PageData[FactData],
    ("post", "/api/v1/clients/{client_id}/facts"): FactData,
    ("patch", "/api/v1/facts/{fact_id}"): FactData,
    ("post", "/api/v1/facts/{fact_id}/evidence"): FactData,
    ("post", "/api/v1/facts/{fact_id}/confirm"): FactData,
    ("get", "/api/v1/clients/{client_id}/conflicts"): ItemsData[ConflictData],
    ("post", "/api/v1/conflicts/{conflict_id}/resolve"): ConflictData,
    ("get", "/api/v1/clients/{client_id}/knowledge-profile"): KnowledgeProfileData,
    ("patch", "/api/v1/clients/{client_id}/knowledge-profile"): KnowledgeProfileData,
    ("post", "/api/v1/clients/{client_id}/diagnostics"): JobAccepted,
    ("get", "/api/v1/clients/{client_id}/diagnostics/latest"): DiagnosticRunData | None,
    ("patch", "/api/v1/diagnostic-issues/{issue_id}"): DiagnosticIssueData,
    ("post", "/api/v1/clients/{client_id}/strategy/generate"): JobAccepted,
    ("get", "/api/v1/clients/{client_id}/strategy"): StrategyBundleData | None,
    ("patch", "/api/v1/strategy-items/{item_id}"): StrategyItemData,
    ("get", "/api/v1/clients/{client_id}/keyword-workspace"): KeywordWorkspaceData,
    ("put", "/api/v1/clients/{client_id}/keyword-profile"): KeywordProfileData,
    (
        "post",
        "/api/v1/clients/{client_id}/keyword-generations",
    ): KeywordGenerationAcceptedData,
    ("get", "/api/v1/keyword-generations/{generation_id}"): KeywordGenerationData,
    ("patch", "/api/v1/keyword-candidates/{candidate_id}"): KeywordCandidateData,
    (
        "post",
        "/api/v1/keyword-generations/{generation_id}/confirm",
    ): KeywordGenerationData,
    ("delete", "/api/v1/keyword-generations/{generation_id}"): KeywordGenerationData,
    ("post", "/api/v1/clients/{client_id}/briefs"): ContentBriefData,
    ("get", "/api/v1/briefs/{brief_id}"): ContentBriefData,
    ("patch", "/api/v1/briefs/{brief_id}"): ContentBriefData,
    ("get", "/api/v1/clients/{client_id}/documents"): PageData[DocumentData],
    (
        "get",
        "/api/v1/clients/{client_id}/content-generation-tasks",
    ): PageData[ContentGenerationTaskData],
    (
        "get",
        "/api/v1/content-generation-tasks/{task_id}",
    ): ContentGenerationTaskData,
    (
        "post",
        "/api/v1/content-generation-tasks/{task_id}/confirm",
    ): ContentGenerationTaskData,
    ("post", "/api/v1/clients/{client_id}/documents/batch"): DocumentsCreatedData,
    ("post", "/api/v1/clients/{client_id}/documents"): DocumentData,
    ("get", "/api/v1/documents/{document_id}"): DocumentData,
    ("patch", "/api/v1/documents/{document_id}"): DocumentData,
    ("post", "/api/v1/documents/{document_id}/publish"): PublicationBatchAccepted,
    ("delete", "/api/v1/documents/{document_id}"): DocumentData,
    ("post", "/api/v1/documents/{document_id}/restore"): DocumentData,
    ("post", "/api/v1/documents/{document_id}/operations"): JobAccepted,
    ("get", "/api/v1/documents/{document_id}/versions"): PageData[DocumentVersionData],
    ("post", "/api/v1/documents/{document_id}/versions/{version_id}/restore"): DocumentData,
    ("get", "/api/v1/documents/{document_id}/quality-checks"): PageData[QualityCheckData],
    ("get", "/api/v1/channels"): ChannelCatalogData,
    ("get", "/api/v1/publishing/channels"): PublishingChannelListData,
    ("post", "/api/v1/publishing/channels/{channel_id}/accounts"): PublishingAccountData,
    ("patch", "/api/v1/publishing/accounts/{account_id}"): PublishingAccountData,
    ("post", "/api/v1/publishing/accounts/{account_id}/login-window"): PublishingAccountData,
    ("post", "/api/v1/publishing/accounts/{account_id}/test"): PublishingAccountData,
    ("get", "/api/v1/clients/{client_id}/channel-recommendations"): RecommendationListData,
    ("post", "/api/v1/clients/{client_id}/channel-recommendations/generate"): JobAccepted,
    ("get", "/api/v1/monitoring/platforms"): PlatformCatalogData,
    ("get", "/api/v1/clients/{client_id}/question-sets"): ItemsData[QuestionSetData],
    ("post", "/api/v1/clients/{client_id}/question-sets"): QuestionSetData,
    ("patch", "/api/v1/question-sets/{question_set_id}"): QuestionSetData,
    ("post", "/api/v1/clients/{client_id}/monitoring-batches"): JobAccepted,
    ("get", "/api/v1/monitoring-batches/{batch_id}"): MonitoringBatchData,
    ("get", "/api/v1/clients/{client_id}/monitoring-batches/latest"): MonitoringBatchData,
    ("post", "/api/v1/monitoring-batches/{batch_id}/manual-samples"): ItemsData[
        MonitoringSampleData
    ],
    ("put", "/api/v1/monitoring-samples/{sample_id}/evaluation"): SampleEvaluationData,
    ("get", "/api/v1/clients/{client_id}/monitoring-metrics"): MonitoringMetricsData,
    ("post", "/api/v1/monitoring-evaluations/{evaluation_id}/feedback"): OptimizationFeedbackData,
    ("get", "/api/v1/clients/{client_id}/optimization-actions"): ItemsData[OptimizationActionData],
    ("get", "/api/v1/settings"): SettingsData,
    ("patch", "/api/v1/settings/runtime"): RuntimeSettingsData,
    ("put", "/api/v1/settings/providers/{provider}"): ProviderSettingData,
    ("post", "/api/v1/settings/providers/{provider}/test"): ProviderTestData,
    ("get", "/api/v1/prompt-templates"): PromptTemplateListData,
    ("patch", "/api/v1/prompt-templates/{template_id}"): PromptTemplateData,
    ("post", "/api/v1/prompt-templates/{template_id}/restore"): PromptTemplateData,
    ("get", "/api/v1/prompt-templates/{template_id}/versions"): ItemsData[
        PromptTemplateVersionData
    ],
    ("get", "/api/v1/jobs/{job_id}"): JobData,
    ("post", "/api/v1/jobs/{job_id}/retry"): JobAccepted,
    ("post", "/api/v1/jobs/{job_id}/cancel"): JobData,
}

SUCCESS_RESPONSE_MODELS = {
    key: ApiEnvelope[data_model]  # type: ignore[valid-type]
    for key, data_model in SUCCESS_DATA_MODELS.items()
}
