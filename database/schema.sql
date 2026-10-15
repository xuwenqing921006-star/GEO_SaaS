-- GEO SaaS PostgreSQL 18 schema snapshot, generated from a NEW isolated database.
-- Source: all Alembic migrations through revision 0029 (2026-10-15).
-- Contains no original runtime data, credentials or role passwords.
-- Import into an EMPTY database as its migration owner, using psql --single-transaction -v ON_ERROR_STOP=1.
DO $$ BEGIN IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public') THEN RAISE EXCEPTION 'Schema snapshot requires an empty public schema; use migrations for an existing database'; END IF; END $$;
--
-- PostgreSQL database dump
--


-- Dumped from database version 18.4
-- Dumped by pg_dump version 18.4

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: channel_recommendations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.channel_recommendations (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    channel_id character varying(100) NOT NULL,
    catalog_version character varying(30) NOT NULL,
    priority integer NOT NULL,
    fit_score integer NOT NULL,
    reasons json NOT NULL,
    recommended_content_types json NOT NULL,
    required_actions json NOT NULL,
    caveat text NOT NULL,
    source_brief_ids json NOT NULL,
    active boolean NOT NULL,
    generated_at timestamp with time zone NOT NULL,
    generation_id uuid,
    brief_id uuid,
    content_document_id uuid,
    channel_snapshot json DEFAULT '{}'::json NOT NULL,
    brief_snapshot json DEFAULT '{}'::json NOT NULL,
    required_adaptation text DEFAULT ''::text NOT NULL,
    account_positioning text DEFAULT ''::text NOT NULL,
    authorization_note text DEFAULT ''::text NOT NULL,
    cost_note text DEFAULT ''::text NOT NULL,
    risk_note text DEFAULT ''::text NOT NULL,
    target_ecosystems json DEFAULT '[]'::json NOT NULL
);


--
-- Name: clients; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.clients (
    id uuid NOT NULL,
    standard_name character varying(200) NOT NULL,
    short_name character varying(100),
    industry_code character varying(100) NOT NULL,
    industry_name character varying(100) NOT NULL,
    province character varying(100) NOT NULL,
    city character varying(100) NOT NULL,
    district character varying(100) NOT NULL,
    address character varying(500) NOT NULL,
    contact_phone character varying(50),
    contact_wechat character varying(100),
    business_hours character varying(200),
    service_radius character varying(200),
    cooperation_started_on date NOT NULL,
    notes text,
    status character varying(20) NOT NULL,
    current_level character varying(2) NOT NULL,
    fact_completeness integer NOT NULL,
    blocking_issue_count integer NOT NULL,
    next_action character varying(200) NOT NULL,
    archived_reason character varying(200),
    version integer NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    normalized_name text NOT NULL
);


--
-- Name: content_briefs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_briefs (
    id uuid NOT NULL,
    bundle_id uuid NOT NULL,
    client_id uuid NOT NULL,
    title character varying(300) NOT NULL,
    content_type character varying(30) NOT NULL,
    target_question_ids json NOT NULL,
    target_keywords json NOT NULL,
    target_level character varying(2) NOT NULL,
    audience text NOT NULL,
    angle text NOT NULL,
    required_fact_ids json NOT NULL,
    required_evidence_ids json NOT NULL,
    expected_recommendation_reason text NOT NULL,
    prohibited_claims json NOT NULL,
    retest_questions json NOT NULL,
    suggested_channel_ids json NOT NULL,
    priority integer NOT NULL,
    status character varying(30) NOT NULL,
    version integer NOT NULL,
    keyword_strategy_id uuid,
    keyword_type character varying(30),
    prompt_template_code character varying(80),
    prompt_template_version integer,
    target_channel_id character varying(80),
    contact_policy character varying(30),
    prompt_layers_snapshot json,
    contact_allowed_urls json
);


--
-- Name: content_channel_variants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_channel_variants (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    channel_id character varying(100) NOT NULL,
    version_id uuid NOT NULL,
    adaptation_note text NOT NULL
);


--
-- Name: content_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_documents (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    brief_id uuid NOT NULL,
    title character varying(300) NOT NULL,
    status character varying(30) NOT NULL,
    current_version_id uuid,
    version integer NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    generation_task_id uuid
);


--
-- Name: content_exports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_exports (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    content_version_id uuid NOT NULL,
    format character varying(20) NOT NULL,
    include_sources boolean NOT NULL,
    storage_key character varying(500),
    status character varying(20) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    completed_at timestamp with time zone
);


--
-- Name: content_generation_tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_generation_tasks (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    platform_type character varying(30) DEFAULT 'self_media'::character varying NOT NULL,
    keyword_snapshots json NOT NULL,
    channel_ids json NOT NULL,
    article_count_per_channel integer NOT NULL,
    length character varying(20) NOT NULL,
    content_form_codes json NOT NULL,
    total_count integer NOT NULL,
    archived boolean DEFAULT false NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    confirmed_at timestamp with time zone
);


--
-- Name: content_publications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_publications (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    version_id uuid NOT NULL,
    channel_id character varying(80),
    published_at timestamp with time zone,
    status character varying(30) DEFAULT 'published'::character varying NOT NULL,
    platform_post_id character varying(200),
    public_url character varying(1000),
    error_message character varying(500),
    submitted_at timestamp with time zone,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    publishing_account_id uuid
);


--
-- Name: content_quality_checks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_quality_checks (
    id uuid NOT NULL,
    document_version_id uuid NOT NULL,
    overall_status character varying(20) NOT NULL,
    dimensions json NOT NULL,
    findings json NOT NULL,
    provider character varying(20) NOT NULL,
    model character varying(100),
    created_at timestamp with time zone NOT NULL
);


--
-- Name: content_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_versions (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    version_number integer NOT NULL,
    title character varying(300) NOT NULL,
    body_markdown text NOT NULL,
    outline_markdown text,
    change_type character varying(30) NOT NULL,
    provider character varying(20) NOT NULL,
    model character varying(100),
    fact_snapshot_id uuid NOT NULL,
    prompt_version character varying(50),
    input_hash character varying(64),
    output_hash character varying(64),
    input_tokens integer NOT NULL,
    output_tokens integer NOT NULL,
    fallback_reason character varying(200),
    created_at timestamp with time zone NOT NULL,
    prompt_template_code character varying(80),
    prompt_template_version integer,
    target_channel_id character varying(80),
    contact_policy character varying(30),
    prompt_layers_snapshot json,
    contact_allowed_urls json,
    contact_sanitization_report json,
    image_material_ids json DEFAULT '[]'::json NOT NULL,
    title_candidates json
);


--
-- Name: diagnostic_issues; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.diagnostic_issues (
    id uuid NOT NULL,
    diagnostic_run_id uuid NOT NULL,
    client_id uuid NOT NULL,
    category character varying(20) NOT NULL,
    severity character varying(20) NOT NULL,
    title character varying(200) NOT NULL,
    explanation text NOT NULL,
    evidence_ids json NOT NULL,
    suggested_action text NOT NULL,
    target_page character varying(3) NOT NULL,
    status character varying(20) NOT NULL,
    note character varying(1000),
    version integer NOT NULL
);


--
-- Name: diagnostic_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.diagnostic_runs (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    status character varying(20) NOT NULL,
    current_level character varying(2) NOT NULL,
    scores json NOT NULL,
    fact_snapshot_id uuid NOT NULL,
    fact_snapshot json NOT NULL,
    completed_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    scope json NOT NULL,
    monitoring_window_days integer NOT NULL,
    platform_results json DEFAULT '[]'::json NOT NULL,
    monitoring_sample_count integer DEFAULT 0 NOT NULL
);


--
-- Name: evidence; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.evidence (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    material_id uuid,
    source_type character varying(30) NOT NULL,
    source_label character varying(200) NOT NULL,
    source_url character varying(2000),
    quote text NOT NULL,
    observed_at date NOT NULL,
    authorization_status character varying(30) NOT NULL
);


--
-- Name: fact_conflicts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.fact_conflicts (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    fact_key character varying(150) NOT NULL,
    label character varying(200) NOT NULL,
    candidates json NOT NULL,
    status character varying(20) NOT NULL,
    resolved_value text,
    resolution_note character varying(1000),
    version integer NOT NULL
);


--
-- Name: fact_evidence; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.fact_evidence (
    fact_id uuid NOT NULL,
    evidence_id uuid NOT NULL
);


--
-- Name: fact_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.fact_snapshots (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    brief_id uuid NOT NULL,
    brief_version integer NOT NULL,
    facts json NOT NULL,
    evidence json NOT NULL,
    brief_context json NOT NULL,
    prohibited_claims json NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: facts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.facts (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    category character varying(30) NOT NULL,
    key character varying(150) NOT NULL,
    label character varying(200) NOT NULL,
    value text NOT NULL,
    status character varying(30) NOT NULL,
    confidence integer NOT NULL,
    valid_from date,
    valid_until date,
    confirmation_note character varying(1000),
    version integer NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.jobs (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    material_id uuid,
    job_type character varying(50) NOT NULL,
    status character varying(30) NOT NULL,
    idempotency_key character varying(200) NOT NULL,
    payload json NOT NULL,
    progress integer NOT NULL,
    attempts integer NOT NULL,
    max_attempts integer NOT NULL,
    lease_until timestamp with time zone,
    error_message character varying(500),
    created_at timestamp with time zone NOT NULL,
    started_at timestamp with time zone,
    completed_at timestamp with time zone
);


--
-- Name: keyword_candidates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.keyword_candidates (
    id uuid NOT NULL,
    generation_id uuid NOT NULL,
    client_id uuid NOT NULL,
    text text NOT NULL,
    normalized_text character varying(500) NOT NULL,
    main_keyword character varying(300) NOT NULL,
    keyword_type character varying(30) NOT NULL,
    user_intent character varying(300) NOT NULL,
    region character varying(100),
    secondary_keyword character varying(300),
    recommended_content_type character varying(80) NOT NULL,
    priority integer DEFAULT 2 NOT NULL,
    selected boolean DEFAULT true NOT NULL,
    active boolean DEFAULT true NOT NULL,
    confirmed_item_id uuid,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: keyword_generations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.keyword_generations (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    job_id uuid,
    primary_keyword character varying(300) NOT NULL,
    regions json NOT NULL,
    secondary_keywords json NOT NULL,
    keyword_types json NOT NULL,
    knowledge_fingerprint character varying(64) NOT NULL,
    target_count integer NOT NULL,
    status character varying(30) DEFAULT 'queued'::character varying NOT NULL,
    generated_count integer DEFAULT 0 NOT NULL,
    filtered_count integer DEFAULT 0 NOT NULL,
    confirmed_count integer DEFAULT 0 NOT NULL,
    error_message character varying(500),
    archived boolean DEFAULT false NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    confirmed_at timestamp with time zone
);


--
-- Name: keyword_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.keyword_profiles (
    client_id uuid NOT NULL,
    primary_keyword character varying(300) NOT NULL,
    regions json NOT NULL,
    secondary_keywords json NOT NULL,
    keyword_types json NOT NULL,
    recommended_count integer NOT NULL,
    knowledge_fingerprint character varying(64) NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: knowledge_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.knowledge_profiles (
    client_id uuid NOT NULL,
    services json NOT NULL,
    capabilities json NOT NULL,
    prohibited_claims json NOT NULL,
    external_presences json NOT NULL,
    version integer NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: material_fragments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.material_fragments (
    id uuid NOT NULL,
    material_id uuid NOT NULL,
    page integer,
    text text NOT NULL,
    extraction_method character varying(20) NOT NULL,
    sensitivity_tags json NOT NULL,
    "position" integer NOT NULL
);


--
-- Name: materials; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.materials (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    file_name character varying(255) NOT NULL,
    media_type character varying(150) NOT NULL,
    size_bytes bigint NOT NULL,
    sha256 character varying(64) NOT NULL,
    storage_key character varying(500) NOT NULL,
    category character varying(30) NOT NULL,
    authorization_status character varying(30) NOT NULL,
    extraction_status character varying(30) NOT NULL,
    extraction_error character varying(500),
    page_count integer,
    fragment_count integer NOT NULL,
    uploaded_at timestamp with time zone NOT NULL,
    version integer NOT NULL
);


--
-- Name: model_usage; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.model_usage (
    id uuid NOT NULL,
    client_id uuid,
    provider character varying(20) NOT NULL,
    model character varying(100) NOT NULL,
    purpose character varying(50) NOT NULL,
    usage_date date NOT NULL,
    input_tokens integer NOT NULL,
    output_tokens integer NOT NULL,
    cost_cny_fen integer NOT NULL,
    status character varying(20) NOT NULL,
    fallback_reason character varying(100),
    input_hash character varying(64),
    output_hash character varying(64),
    latency_ms integer,
    created_at timestamp with time zone NOT NULL,
    fact_snapshot_id uuid,
    prompt_version character varying(50),
    pricing_version character varying(50)
);


--
-- Name: monitoring_batches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.monitoring_batches (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    question_set_id uuid NOT NULL,
    question_set_version integer NOT NULL,
    question_snapshot json NOT NULL,
    platform_ids json NOT NULL,
    api_sample_count integer DEFAULT 1 NOT NULL,
    status character varying(30) DEFAULT 'queued'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone
);


--
-- Name: monitoring_evaluations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.monitoring_evaluations (
    id uuid NOT NULL,
    sample_id uuid NOT NULL,
    client_id uuid NOT NULL,
    brand_found boolean NOT NULL,
    correctly_associated boolean NOT NULL,
    recommended boolean NOT NULL,
    recommendation_supported boolean,
    facts_accurate boolean,
    source_visible boolean DEFAULT false NOT NULL,
    mentioned_name character varying(200),
    reasons json DEFAULT '[]'::json NOT NULL,
    incorrect_facts json DEFAULT '[]'::json NOT NULL,
    visible_sources json DEFAULT '[]'::json NOT NULL,
    note character varying(1000),
    evaluator character varying(20) DEFAULT 'system'::character varying NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: monitoring_feedback; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.monitoring_feedback (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    evaluation_id uuid NOT NULL,
    action_type character varying(40) NOT NULL,
    reason text NOT NULL,
    target_level character varying(2) NOT NULL,
    target_page character varying(3) NOT NULL,
    status character varying(20) DEFAULT 'open'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    converted_record_type character varying(40) NOT NULL,
    converted_record_id uuid NOT NULL
);


--
-- Name: monitoring_question_sets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.monitoring_question_sets (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    name character varying(200) NOT NULL,
    frozen boolean DEFAULT false NOT NULL,
    questions json DEFAULT '[]'::json NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: monitoring_samples; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.monitoring_samples (
    id uuid NOT NULL,
    batch_id uuid NOT NULL,
    client_id uuid NOT NULL,
    platform_id character varying(50) NOT NULL,
    platform_name character varying(100) NOT NULL,
    collection_mode character varying(30) NOT NULL,
    question_id character varying(100) NOT NULL,
    question_text text NOT NULL,
    question_family character varying(50) NOT NULL,
    is_brand_query boolean DEFAULT false NOT NULL,
    attempt integer DEFAULT 1 NOT NULL,
    status character varying(30) DEFAULT 'not_executed'::character varying NOT NULL,
    raw_answer text,
    asked_at timestamp with time zone,
    failure_reason character varying(500),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    question_priority integer DEFAULT 1 NOT NULL
);


--
-- Name: optimization_actions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.optimization_actions (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    source_type character varying(40) NOT NULL,
    source_id uuid NOT NULL,
    action_type character varying(40) NOT NULL,
    title character varying(300) NOT NULL,
    reason text NOT NULL,
    target_level character varying(2) NOT NULL,
    target_page character varying(3) NOT NULL,
    status character varying(20) DEFAULT 'open'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: owner_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.owner_sessions (
    token_hash character varying(64) NOT NULL,
    owner_id uuid NOT NULL,
    csrf_hash character varying(64) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    last_seen_at timestamp with time zone NOT NULL,
    idle_expires_at timestamp with time zone NOT NULL,
    absolute_expires_at timestamp with time zone NOT NULL,
    session_version integer NOT NULL
);


--
-- Name: owners; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.owners (
    id uuid NOT NULL,
    username character varying(64) NOT NULL,
    display_name character varying(100) NOT NULL,
    password_hash text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    singleton_key integer NOT NULL,
    session_version integer NOT NULL,
    CONSTRAINT ck_owners_singleton_key CHECK ((singleton_key = 1))
);


--
-- Name: prompt_template_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.prompt_template_versions (
    id uuid NOT NULL,
    template_id uuid NOT NULL,
    version_number integer NOT NULL,
    template_text text NOT NULL,
    contact_policy character varying(30),
    change_note character varying(300) NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: prompt_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.prompt_templates (
    id uuid NOT NULL,
    code character varying(80) NOT NULL,
    category character varying(30) NOT NULL,
    name character varying(100) NOT NULL,
    description character varying(500) NOT NULL,
    template_text text NOT NULL,
    default_text text NOT NULL,
    editable boolean NOT NULL,
    active boolean NOT NULL,
    variable_keys json NOT NULL,
    required_fact_keys json NOT NULL,
    contact_policy character varying(30),
    channel_id character varying(80),
    source_url character varying(2000),
    verified_at date,
    current_version integer NOT NULL,
    version integer NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    default_contact_policy character varying(30)
);


--
-- Name: provider_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.provider_settings (
    provider character varying(20) NOT NULL,
    enabled boolean NOT NULL,
    base_url character varying(500) NOT NULL,
    workspace_id character varying(200),
    writer_model character varying(100),
    reviewer_model character varying(100),
    fallback_model character varying(100),
    daily_budget_cny_fen integer NOT NULL,
    timeout_seconds integer NOT NULL,
    encrypted_api_key bytea,
    secret_suffix character varying(4),
    last_tested_at timestamp with time zone,
    last_test_status character varying(20) NOT NULL,
    version integer NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_provider_settings_provider CHECK (((provider)::text = ANY ((ARRAY['qwen'::character varying, 'deepseek'::character varying, 'doubao'::character varying, 'wenxin'::character varying, 'yuanbao'::character varying, 'kimi'::character varying])::text[])))
);


--
-- Name: publishing_accounts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.publishing_accounts (
    id uuid NOT NULL,
    channel_id character varying(80) NOT NULL,
    display_name character varying(100) NOT NULL,
    enabled boolean DEFAULT false NOT NULL,
    connection_status character varying(30) DEFAULT 'disconnected'::character varying NOT NULL,
    account_name character varying(200),
    last_checked_at timestamp with time zone,
    last_error character varying(500),
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: publishing_channel_configs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.publishing_channel_configs (
    channel_id character varying(80) NOT NULL,
    enabled boolean DEFAULT false NOT NULL,
    connection_status character varying(30) DEFAULT 'disconnected'::character varying NOT NULL,
    account_name character varying(200),
    last_checked_at timestamp with time zone,
    last_error character varying(500),
    version integer DEFAULT 1 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: runtime_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.runtime_settings (
    singleton_key integer NOT NULL,
    default_client_monthly_budget_cny_fen integer NOT NULL,
    version integer NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_runtime_settings_singleton_key CHECK ((singleton_key = 1))
);


--
-- Name: runtime_settings_singleton_key_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.runtime_settings_singleton_key_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: runtime_settings_singleton_key_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.runtime_settings_singleton_key_seq OWNED BY public.runtime_settings.singleton_key;


--
-- Name: strategy_bundles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.strategy_bundles (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    diagnostic_run_id uuid,
    generated_at timestamp with time zone NOT NULL,
    version integer NOT NULL,
    prompt_template_code character varying(80),
    prompt_template_version integer
);


--
-- Name: strategy_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.strategy_items (
    id uuid NOT NULL,
    bundle_id uuid NOT NULL,
    client_id uuid NOT NULL,
    kind character varying(20) NOT NULL,
    text text NOT NULL,
    family character varying(30),
    keyword_type character varying(30),
    provenance character varying(30) NOT NULL,
    target_level character varying(2) NOT NULL,
    priority integer NOT NULL,
    rationale text NOT NULL,
    locked boolean NOT NULL,
    active boolean NOT NULL,
    version integer NOT NULL,
    main_keyword character varying(300),
    user_intent character varying(300),
    selected boolean DEFAULT false NOT NULL,
    recommended_content_type character varying(80)
);


--
-- Name: runtime_settings singleton_key; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.runtime_settings ALTER COLUMN singleton_key SET DEFAULT nextval('public.runtime_settings_singleton_key_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: channel_recommendations channel_recommendations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.channel_recommendations
    ADD CONSTRAINT channel_recommendations_pkey PRIMARY KEY (id);


--
-- Name: clients clients_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clients
    ADD CONSTRAINT clients_pkey PRIMARY KEY (id);


--
-- Name: content_briefs content_briefs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_briefs
    ADD CONSTRAINT content_briefs_pkey PRIMARY KEY (id);


--
-- Name: content_channel_variants content_channel_variants_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_channel_variants
    ADD CONSTRAINT content_channel_variants_pkey PRIMARY KEY (id);


--
-- Name: content_documents content_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_documents
    ADD CONSTRAINT content_documents_pkey PRIMARY KEY (id);


--
-- Name: content_exports content_exports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_exports
    ADD CONSTRAINT content_exports_pkey PRIMARY KEY (id);


--
-- Name: content_exports content_exports_storage_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_exports
    ADD CONSTRAINT content_exports_storage_key_key UNIQUE (storage_key);


--
-- Name: content_generation_tasks content_generation_tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_generation_tasks
    ADD CONSTRAINT content_generation_tasks_pkey PRIMARY KEY (id);


--
-- Name: content_publications content_publications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_publications
    ADD CONSTRAINT content_publications_pkey PRIMARY KEY (id);


--
-- Name: content_quality_checks content_quality_checks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_quality_checks
    ADD CONSTRAINT content_quality_checks_pkey PRIMARY KEY (id);


--
-- Name: content_versions content_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_versions
    ADD CONSTRAINT content_versions_pkey PRIMARY KEY (id);


--
-- Name: diagnostic_issues diagnostic_issues_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_issues
    ADD CONSTRAINT diagnostic_issues_pkey PRIMARY KEY (id);


--
-- Name: diagnostic_runs diagnostic_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_runs
    ADD CONSTRAINT diagnostic_runs_pkey PRIMARY KEY (id);


--
-- Name: evidence evidence_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evidence
    ADD CONSTRAINT evidence_pkey PRIMARY KEY (id);


--
-- Name: fact_conflicts fact_conflicts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fact_conflicts
    ADD CONSTRAINT fact_conflicts_pkey PRIMARY KEY (id);


--
-- Name: fact_evidence fact_evidence_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fact_evidence
    ADD CONSTRAINT fact_evidence_pkey PRIMARY KEY (fact_id, evidence_id);


--
-- Name: fact_snapshots fact_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fact_snapshots
    ADD CONSTRAINT fact_snapshots_pkey PRIMARY KEY (id);


--
-- Name: facts facts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.facts
    ADD CONSTRAINT facts_pkey PRIMARY KEY (id);


--
-- Name: jobs jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_pkey PRIMARY KEY (id);


--
-- Name: keyword_candidates keyword_candidates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.keyword_candidates
    ADD CONSTRAINT keyword_candidates_pkey PRIMARY KEY (id);


--
-- Name: keyword_generations keyword_generations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.keyword_generations
    ADD CONSTRAINT keyword_generations_pkey PRIMARY KEY (id);


--
-- Name: keyword_profiles keyword_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.keyword_profiles
    ADD CONSTRAINT keyword_profiles_pkey PRIMARY KEY (client_id);


--
-- Name: knowledge_profiles knowledge_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_profiles
    ADD CONSTRAINT knowledge_profiles_pkey PRIMARY KEY (client_id);


--
-- Name: material_fragments material_fragments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.material_fragments
    ADD CONSTRAINT material_fragments_pkey PRIMARY KEY (id);


--
-- Name: materials materials_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.materials
    ADD CONSTRAINT materials_pkey PRIMARY KEY (id);


--
-- Name: materials materials_storage_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.materials
    ADD CONSTRAINT materials_storage_key_key UNIQUE (storage_key);


--
-- Name: model_usage model_usage_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_usage
    ADD CONSTRAINT model_usage_pkey PRIMARY KEY (id);


--
-- Name: monitoring_batches monitoring_batches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monitoring_batches
    ADD CONSTRAINT monitoring_batches_pkey PRIMARY KEY (id);


--
-- Name: monitoring_evaluations monitoring_evaluations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monitoring_evaluations
    ADD CONSTRAINT monitoring_evaluations_pkey PRIMARY KEY (id);


--
-- Name: monitoring_feedback monitoring_feedback_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monitoring_feedback
    ADD CONSTRAINT monitoring_feedback_pkey PRIMARY KEY (id);


--
-- Name: monitoring_question_sets monitoring_question_sets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monitoring_question_sets
    ADD CONSTRAINT monitoring_question_sets_pkey PRIMARY KEY (id);


--
-- Name: monitoring_samples monitoring_samples_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monitoring_samples
    ADD CONSTRAINT monitoring_samples_pkey PRIMARY KEY (id);


--
-- Name: optimization_actions optimization_actions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.optimization_actions
    ADD CONSTRAINT optimization_actions_pkey PRIMARY KEY (id);


--
-- Name: owner_sessions owner_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.owner_sessions
    ADD CONSTRAINT owner_sessions_pkey PRIMARY KEY (token_hash);


--
-- Name: owners owners_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.owners
    ADD CONSTRAINT owners_pkey PRIMARY KEY (id);


--
-- Name: owners owners_username_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.owners
    ADD CONSTRAINT owners_username_key UNIQUE (username);


--
-- Name: prompt_template_versions prompt_template_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prompt_template_versions
    ADD CONSTRAINT prompt_template_versions_pkey PRIMARY KEY (id);


--
-- Name: prompt_templates prompt_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prompt_templates
    ADD CONSTRAINT prompt_templates_pkey PRIMARY KEY (id);


--
-- Name: provider_settings provider_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_settings
    ADD CONSTRAINT provider_settings_pkey PRIMARY KEY (provider);


--
-- Name: publishing_accounts publishing_accounts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.publishing_accounts
    ADD CONSTRAINT publishing_accounts_pkey PRIMARY KEY (id);


--
-- Name: publishing_channel_configs publishing_channel_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.publishing_channel_configs
    ADD CONSTRAINT publishing_channel_configs_pkey PRIMARY KEY (channel_id);


--
-- Name: runtime_settings runtime_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.runtime_settings
    ADD CONSTRAINT runtime_settings_pkey PRIMARY KEY (singleton_key);


--
-- Name: strategy_bundles strategy_bundles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_bundles
    ADD CONSTRAINT strategy_bundles_pkey PRIMARY KEY (id);


--
-- Name: strategy_items strategy_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_items
    ADD CONSTRAINT strategy_items_pkey PRIMARY KEY (id);


--
-- Name: channel_recommendations uq_channel_recommendations_generation_brief_channel; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.channel_recommendations
    ADD CONSTRAINT uq_channel_recommendations_generation_brief_channel UNIQUE (client_id, generation_id, brief_id, channel_id);


--
-- Name: clients uq_clients_normalized_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clients
    ADD CONSTRAINT uq_clients_normalized_name UNIQUE (normalized_name);


--
-- Name: content_channel_variants uq_content_channel_variants_document_channel; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_channel_variants
    ADD CONSTRAINT uq_content_channel_variants_document_channel UNIQUE (document_id, channel_id);


--
-- Name: content_documents uq_content_documents_brief; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_documents
    ADD CONSTRAINT uq_content_documents_brief UNIQUE (client_id, brief_id);


--
-- Name: content_publications uq_content_publications_document_version_account; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_publications
    ADD CONSTRAINT uq_content_publications_document_version_account UNIQUE (document_id, version_id, publishing_account_id);


--
-- Name: content_versions uq_content_versions_document_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_versions
    ADD CONSTRAINT uq_content_versions_document_number UNIQUE (document_id, version_number);


--
-- Name: facts uq_facts_client_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.facts
    ADD CONSTRAINT uq_facts_client_key UNIQUE (client_id, key);


--
-- Name: jobs uq_jobs_client_type_idempotency; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT uq_jobs_client_type_idempotency UNIQUE (client_id, job_type, idempotency_key);


--
-- Name: keyword_candidates uq_keyword_candidates_client_normalized_text; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.keyword_candidates
    ADD CONSTRAINT uq_keyword_candidates_client_normalized_text UNIQUE (client_id, normalized_text);


--
-- Name: monitoring_evaluations uq_monitoring_evaluations_sample_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monitoring_evaluations
    ADD CONSTRAINT uq_monitoring_evaluations_sample_id UNIQUE (sample_id);


--
-- Name: monitoring_feedback uq_monitoring_feedback_evaluation_action; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monitoring_feedback
    ADD CONSTRAINT uq_monitoring_feedback_evaluation_action UNIQUE (evaluation_id, action_type);


--
-- Name: monitoring_samples uq_monitoring_samples_batch_platform_question_attempt; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monitoring_samples
    ADD CONSTRAINT uq_monitoring_samples_batch_platform_question_attempt UNIQUE (batch_id, platform_id, question_id, attempt);


--
-- Name: optimization_actions uq_optimization_actions_source_action; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.optimization_actions
    ADD CONSTRAINT uq_optimization_actions_source_action UNIQUE (source_type, source_id, action_type);


--
-- Name: owners uq_owners_singleton_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.owners
    ADD CONSTRAINT uq_owners_singleton_key UNIQUE (singleton_key);


--
-- Name: prompt_template_versions uq_prompt_template_versions_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prompt_template_versions
    ADD CONSTRAINT uq_prompt_template_versions_number UNIQUE (template_id, version_number);


--
-- Name: prompt_templates uq_prompt_templates_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prompt_templates
    ADD CONSTRAINT uq_prompt_templates_code UNIQUE (code);


--
-- Name: publishing_accounts uq_publishing_accounts_channel_display_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.publishing_accounts
    ADD CONSTRAINT uq_publishing_accounts_channel_display_name UNIQUE (channel_id, display_name);


--
-- Name: strategy_bundles uq_strategy_bundles_client_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_bundles
    ADD CONSTRAINT uq_strategy_bundles_client_id UNIQUE (client_id);


--
-- Name: ix_channel_recommendations_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_channel_recommendations_active ON public.channel_recommendations USING btree (active);


--
-- Name: ix_channel_recommendations_brief_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_channel_recommendations_brief_id ON public.channel_recommendations USING btree (brief_id);


--
-- Name: ix_channel_recommendations_channel_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_channel_recommendations_channel_id ON public.channel_recommendations USING btree (channel_id);


--
-- Name: ix_channel_recommendations_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_channel_recommendations_client_id ON public.channel_recommendations USING btree (client_id);


--
-- Name: ix_channel_recommendations_content_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_channel_recommendations_content_document_id ON public.channel_recommendations USING btree (content_document_id);


--
-- Name: ix_channel_recommendations_generation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_channel_recommendations_generation_id ON public.channel_recommendations USING btree (generation_id);


--
-- Name: ix_clients_industry_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clients_industry_code ON public.clients USING btree (industry_code);


--
-- Name: ix_clients_standard_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clients_standard_name ON public.clients USING btree (standard_name);


--
-- Name: ix_clients_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clients_status ON public.clients USING btree (status);


--
-- Name: ix_content_briefs_bundle_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_briefs_bundle_id ON public.content_briefs USING btree (bundle_id);


--
-- Name: ix_content_briefs_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_briefs_client_id ON public.content_briefs USING btree (client_id);


--
-- Name: ix_content_briefs_keyword_strategy_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_briefs_keyword_strategy_id ON public.content_briefs USING btree (keyword_strategy_id);


--
-- Name: ix_content_briefs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_briefs_status ON public.content_briefs USING btree (status);


--
-- Name: ix_content_channel_variants_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_channel_variants_document_id ON public.content_channel_variants USING btree (document_id);


--
-- Name: ix_content_channel_variants_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_channel_variants_version_id ON public.content_channel_variants USING btree (version_id);


--
-- Name: ix_content_documents_brief_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_documents_brief_id ON public.content_documents USING btree (brief_id);


--
-- Name: ix_content_documents_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_documents_client_id ON public.content_documents USING btree (client_id);


--
-- Name: ix_content_documents_generation_task_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_documents_generation_task_id ON public.content_documents USING btree (generation_task_id);


--
-- Name: ix_content_documents_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_documents_status ON public.content_documents USING btree (status);


--
-- Name: ix_content_exports_content_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_exports_content_version_id ON public.content_exports USING btree (content_version_id);


--
-- Name: ix_content_exports_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_exports_document_id ON public.content_exports USING btree (document_id);


--
-- Name: ix_content_exports_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_exports_status ON public.content_exports USING btree (status);


--
-- Name: ix_content_generation_tasks_archived; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_generation_tasks_archived ON public.content_generation_tasks USING btree (archived);


--
-- Name: ix_content_generation_tasks_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_generation_tasks_client_id ON public.content_generation_tasks USING btree (client_id);


--
-- Name: ix_content_publications_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_publications_document_id ON public.content_publications USING btree (document_id);


--
-- Name: ix_content_publications_published_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_publications_published_at ON public.content_publications USING btree (published_at);


--
-- Name: ix_content_publications_publishing_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_publications_publishing_account_id ON public.content_publications USING btree (publishing_account_id);


--
-- Name: ix_content_publications_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_publications_status ON public.content_publications USING btree (status);


--
-- Name: ix_content_publications_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_publications_version_id ON public.content_publications USING btree (version_id);


--
-- Name: ix_content_quality_checks_document_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_quality_checks_document_version_id ON public.content_quality_checks USING btree (document_version_id);


--
-- Name: ix_content_quality_checks_overall_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_quality_checks_overall_status ON public.content_quality_checks USING btree (overall_status);


--
-- Name: ix_content_versions_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_versions_document_id ON public.content_versions USING btree (document_id);


--
-- Name: ix_content_versions_fact_snapshot_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_versions_fact_snapshot_id ON public.content_versions USING btree (fact_snapshot_id);


--
-- Name: ix_diagnostic_issues_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_issues_category ON public.diagnostic_issues USING btree (category);


--
-- Name: ix_diagnostic_issues_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_issues_client_id ON public.diagnostic_issues USING btree (client_id);


--
-- Name: ix_diagnostic_issues_diagnostic_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_issues_diagnostic_run_id ON public.diagnostic_issues USING btree (diagnostic_run_id);


--
-- Name: ix_diagnostic_issues_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_issues_status ON public.diagnostic_issues USING btree (status);


--
-- Name: ix_diagnostic_runs_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_runs_client_id ON public.diagnostic_runs USING btree (client_id);


--
-- Name: ix_diagnostic_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_runs_status ON public.diagnostic_runs USING btree (status);


--
-- Name: ix_evidence_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_evidence_client_id ON public.evidence USING btree (client_id);


--
-- Name: ix_evidence_material_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_evidence_material_id ON public.evidence USING btree (material_id);


--
-- Name: ix_fact_conflicts_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fact_conflicts_client_id ON public.fact_conflicts USING btree (client_id);


--
-- Name: ix_fact_conflicts_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fact_conflicts_status ON public.fact_conflicts USING btree (status);


--
-- Name: ix_fact_snapshots_brief_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fact_snapshots_brief_id ON public.fact_snapshots USING btree (brief_id);


--
-- Name: ix_fact_snapshots_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fact_snapshots_client_id ON public.fact_snapshots USING btree (client_id);


--
-- Name: ix_facts_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_facts_category ON public.facts USING btree (category);


--
-- Name: ix_facts_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_facts_client_id ON public.facts USING btree (client_id);


--
-- Name: ix_facts_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_facts_status ON public.facts USING btree (status);


--
-- Name: ix_jobs_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jobs_client_id ON public.jobs USING btree (client_id);


--
-- Name: ix_jobs_job_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jobs_job_type ON public.jobs USING btree (job_type);


--
-- Name: ix_jobs_material_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jobs_material_id ON public.jobs USING btree (material_id);


--
-- Name: ix_jobs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jobs_status ON public.jobs USING btree (status);


--
-- Name: ix_keyword_candidates_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_keyword_candidates_active ON public.keyword_candidates USING btree (active);


--
-- Name: ix_keyword_candidates_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_keyword_candidates_client_id ON public.keyword_candidates USING btree (client_id);


--
-- Name: ix_keyword_candidates_generation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_keyword_candidates_generation_id ON public.keyword_candidates USING btree (generation_id);


--
-- Name: ix_keyword_candidates_keyword_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_keyword_candidates_keyword_type ON public.keyword_candidates USING btree (keyword_type);


--
-- Name: ix_keyword_candidates_selected; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_keyword_candidates_selected ON public.keyword_candidates USING btree (selected);


--
-- Name: ix_keyword_generations_archived; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_keyword_generations_archived ON public.keyword_generations USING btree (archived);


--
-- Name: ix_keyword_generations_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_keyword_generations_client_id ON public.keyword_generations USING btree (client_id);


--
-- Name: ix_keyword_generations_job_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_keyword_generations_job_id ON public.keyword_generations USING btree (job_id);


--
-- Name: ix_keyword_generations_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_keyword_generations_status ON public.keyword_generations USING btree (status);


--
-- Name: ix_material_fragments_material_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_material_fragments_material_id ON public.material_fragments USING btree (material_id);


--
-- Name: ix_materials_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_materials_category ON public.materials USING btree (category);


--
-- Name: ix_materials_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_materials_client_id ON public.materials USING btree (client_id);


--
-- Name: ix_materials_extraction_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_materials_extraction_status ON public.materials USING btree (extraction_status);


--
-- Name: ix_model_usage_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_model_usage_client_id ON public.model_usage USING btree (client_id);


--
-- Name: ix_model_usage_fact_snapshot_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_model_usage_fact_snapshot_id ON public.model_usage USING btree (fact_snapshot_id);


--
-- Name: ix_model_usage_provider_day; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_model_usage_provider_day ON public.model_usage USING btree (provider, usage_date);


--
-- Name: ix_monitoring_batches_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_monitoring_batches_client_id ON public.monitoring_batches USING btree (client_id);


--
-- Name: ix_monitoring_batches_question_set_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_monitoring_batches_question_set_id ON public.monitoring_batches USING btree (question_set_id);


--
-- Name: ix_monitoring_batches_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_monitoring_batches_status ON public.monitoring_batches USING btree (status);


--
-- Name: ix_monitoring_evaluations_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_monitoring_evaluations_client_id ON public.monitoring_evaluations USING btree (client_id);


--
-- Name: ix_monitoring_evaluations_sample_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_monitoring_evaluations_sample_id ON public.monitoring_evaluations USING btree (sample_id);


--
-- Name: ix_monitoring_feedback_action_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_monitoring_feedback_action_type ON public.monitoring_feedback USING btree (action_type);


--
-- Name: ix_monitoring_feedback_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_monitoring_feedback_client_id ON public.monitoring_feedback USING btree (client_id);


--
-- Name: ix_monitoring_feedback_converted_record_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_monitoring_feedback_converted_record_id ON public.monitoring_feedback USING btree (converted_record_id);


--
-- Name: ix_monitoring_feedback_evaluation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_monitoring_feedback_evaluation_id ON public.monitoring_feedback USING btree (evaluation_id);


--
-- Name: ix_monitoring_feedback_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_monitoring_feedback_status ON public.monitoring_feedback USING btree (status);


--
-- Name: ix_monitoring_question_sets_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_monitoring_question_sets_client_id ON public.monitoring_question_sets USING btree (client_id);


--
-- Name: ix_monitoring_question_sets_frozen; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_monitoring_question_sets_frozen ON public.monitoring_question_sets USING btree (frozen);


--
-- Name: ix_monitoring_samples_asked_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_monitoring_samples_asked_at ON public.monitoring_samples USING btree (asked_at);


--
-- Name: ix_monitoring_samples_batch_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_monitoring_samples_batch_id ON public.monitoring_samples USING btree (batch_id);


--
-- Name: ix_monitoring_samples_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_monitoring_samples_client_id ON public.monitoring_samples USING btree (client_id);


--
-- Name: ix_monitoring_samples_collection_mode; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_monitoring_samples_collection_mode ON public.monitoring_samples USING btree (collection_mode);


--
-- Name: ix_monitoring_samples_platform_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_monitoring_samples_platform_id ON public.monitoring_samples USING btree (platform_id);


--
-- Name: ix_monitoring_samples_question_family; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_monitoring_samples_question_family ON public.monitoring_samples USING btree (question_family);


--
-- Name: ix_monitoring_samples_question_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_monitoring_samples_question_id ON public.monitoring_samples USING btree (question_id);


--
-- Name: ix_monitoring_samples_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_monitoring_samples_status ON public.monitoring_samples USING btree (status);


--
-- Name: ix_optimization_actions_action_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_optimization_actions_action_type ON public.optimization_actions USING btree (action_type);


--
-- Name: ix_optimization_actions_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_optimization_actions_client_id ON public.optimization_actions USING btree (client_id);


--
-- Name: ix_optimization_actions_source_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_optimization_actions_source_id ON public.optimization_actions USING btree (source_id);


--
-- Name: ix_optimization_actions_source_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_optimization_actions_source_type ON public.optimization_actions USING btree (source_type);


--
-- Name: ix_optimization_actions_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_optimization_actions_status ON public.optimization_actions USING btree (status);


--
-- Name: ix_optimization_actions_target_page; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_optimization_actions_target_page ON public.optimization_actions USING btree (target_page);


--
-- Name: ix_owner_sessions_owner_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_owner_sessions_owner_id ON public.owner_sessions USING btree (owner_id);


--
-- Name: ix_prompt_template_versions_template_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_prompt_template_versions_template_id ON public.prompt_template_versions USING btree (template_id);


--
-- Name: ix_prompt_templates_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_prompt_templates_active ON public.prompt_templates USING btree (active);


--
-- Name: ix_prompt_templates_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_prompt_templates_category ON public.prompt_templates USING btree (category);


--
-- Name: ix_prompt_templates_channel_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_prompt_templates_channel_id ON public.prompt_templates USING btree (channel_id);


--
-- Name: ix_prompt_templates_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_prompt_templates_code ON public.prompt_templates USING btree (code);


--
-- Name: ix_prompt_templates_contact_policy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_prompt_templates_contact_policy ON public.prompt_templates USING btree (contact_policy);


--
-- Name: ix_publishing_accounts_channel_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_publishing_accounts_channel_id ON public.publishing_accounts USING btree (channel_id);


--
-- Name: ix_publishing_accounts_connection_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_publishing_accounts_connection_status ON public.publishing_accounts USING btree (connection_status);


--
-- Name: ix_publishing_channel_configs_connection_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_publishing_channel_configs_connection_status ON public.publishing_channel_configs USING btree (connection_status);


--
-- Name: ix_strategy_bundles_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_bundles_client_id ON public.strategy_bundles USING btree (client_id);


--
-- Name: ix_strategy_bundles_diagnostic_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_bundles_diagnostic_run_id ON public.strategy_bundles USING btree (diagnostic_run_id);


--
-- Name: ix_strategy_items_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_items_active ON public.strategy_items USING btree (active);


--
-- Name: ix_strategy_items_bundle_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_items_bundle_id ON public.strategy_items USING btree (bundle_id);


--
-- Name: ix_strategy_items_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_items_client_id ON public.strategy_items USING btree (client_id);


--
-- Name: ix_strategy_items_family; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_items_family ON public.strategy_items USING btree (family);


--
-- Name: ix_strategy_items_keyword_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_items_keyword_type ON public.strategy_items USING btree (keyword_type);


--
-- Name: ix_strategy_items_kind; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_items_kind ON public.strategy_items USING btree (kind);


--
-- Name: ix_strategy_items_selected; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_items_selected ON public.strategy_items USING btree (selected);


--
-- Name: uq_jobs_active_material_extract; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_jobs_active_material_extract ON public.jobs USING btree (material_id) WHERE ((material_id IS NOT NULL) AND ((job_type)::text = 'material_extract'::text) AND ((status)::text = ANY ((ARRAY['queued'::character varying, 'running'::character varying])::text[])));


--
-- Name: channel_recommendations channel_recommendations_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.channel_recommendations
    ADD CONSTRAINT channel_recommendations_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: content_briefs content_briefs_bundle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_briefs
    ADD CONSTRAINT content_briefs_bundle_id_fkey FOREIGN KEY (bundle_id) REFERENCES public.strategy_bundles(id) ON DELETE CASCADE;


--
-- Name: content_briefs content_briefs_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_briefs
    ADD CONSTRAINT content_briefs_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: content_channel_variants content_channel_variants_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_channel_variants
    ADD CONSTRAINT content_channel_variants_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.content_documents(id) ON DELETE CASCADE;


--
-- Name: content_channel_variants content_channel_variants_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_channel_variants
    ADD CONSTRAINT content_channel_variants_version_id_fkey FOREIGN KEY (version_id) REFERENCES public.content_versions(id) ON DELETE CASCADE;


--
-- Name: content_documents content_documents_brief_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_documents
    ADD CONSTRAINT content_documents_brief_id_fkey FOREIGN KEY (brief_id) REFERENCES public.content_briefs(id) ON DELETE RESTRICT;


--
-- Name: content_documents content_documents_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_documents
    ADD CONSTRAINT content_documents_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: content_exports content_exports_content_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_exports
    ADD CONSTRAINT content_exports_content_version_id_fkey FOREIGN KEY (content_version_id) REFERENCES public.content_versions(id) ON DELETE RESTRICT;


--
-- Name: content_exports content_exports_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_exports
    ADD CONSTRAINT content_exports_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.content_documents(id) ON DELETE CASCADE;


--
-- Name: content_generation_tasks content_generation_tasks_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_generation_tasks
    ADD CONSTRAINT content_generation_tasks_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: content_publications content_publications_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_publications
    ADD CONSTRAINT content_publications_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.content_documents(id) ON DELETE CASCADE;


--
-- Name: content_publications content_publications_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_publications
    ADD CONSTRAINT content_publications_version_id_fkey FOREIGN KEY (version_id) REFERENCES public.content_versions(id) ON DELETE RESTRICT;


--
-- Name: content_quality_checks content_quality_checks_document_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_quality_checks
    ADD CONSTRAINT content_quality_checks_document_version_id_fkey FOREIGN KEY (document_version_id) REFERENCES public.content_versions(id) ON DELETE CASCADE;


--
-- Name: content_versions content_versions_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_versions
    ADD CONSTRAINT content_versions_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.content_documents(id) ON DELETE CASCADE;


--
-- Name: content_versions content_versions_fact_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_versions
    ADD CONSTRAINT content_versions_fact_snapshot_id_fkey FOREIGN KEY (fact_snapshot_id) REFERENCES public.fact_snapshots(id) ON DELETE RESTRICT;


--
-- Name: diagnostic_issues diagnostic_issues_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_issues
    ADD CONSTRAINT diagnostic_issues_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: diagnostic_issues diagnostic_issues_diagnostic_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_issues
    ADD CONSTRAINT diagnostic_issues_diagnostic_run_id_fkey FOREIGN KEY (diagnostic_run_id) REFERENCES public.diagnostic_runs(id) ON DELETE CASCADE;


--
-- Name: diagnostic_runs diagnostic_runs_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_runs
    ADD CONSTRAINT diagnostic_runs_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: evidence evidence_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evidence
    ADD CONSTRAINT evidence_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: evidence evidence_material_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evidence
    ADD CONSTRAINT evidence_material_id_fkey FOREIGN KEY (material_id) REFERENCES public.materials(id) ON DELETE SET NULL;


--
-- Name: fact_conflicts fact_conflicts_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fact_conflicts
    ADD CONSTRAINT fact_conflicts_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: fact_evidence fact_evidence_evidence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fact_evidence
    ADD CONSTRAINT fact_evidence_evidence_id_fkey FOREIGN KEY (evidence_id) REFERENCES public.evidence(id) ON DELETE CASCADE;


--
-- Name: fact_evidence fact_evidence_fact_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fact_evidence
    ADD CONSTRAINT fact_evidence_fact_id_fkey FOREIGN KEY (fact_id) REFERENCES public.facts(id) ON DELETE CASCADE;


--
-- Name: fact_snapshots fact_snapshots_brief_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fact_snapshots
    ADD CONSTRAINT fact_snapshots_brief_id_fkey FOREIGN KEY (brief_id) REFERENCES public.content_briefs(id) ON DELETE RESTRICT;


--
-- Name: fact_snapshots fact_snapshots_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fact_snapshots
    ADD CONSTRAINT fact_snapshots_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: facts facts_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.facts
    ADD CONSTRAINT facts_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: channel_recommendations fk_channel_recommendations_brief_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.channel_recommendations
    ADD CONSTRAINT fk_channel_recommendations_brief_id FOREIGN KEY (brief_id) REFERENCES public.content_briefs(id) ON DELETE SET NULL;


--
-- Name: channel_recommendations fk_channel_recommendations_content_document_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.channel_recommendations
    ADD CONSTRAINT fk_channel_recommendations_content_document_id FOREIGN KEY (content_document_id) REFERENCES public.content_documents(id) ON DELETE SET NULL;


--
-- Name: content_documents fk_content_documents_generation_task_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_documents
    ADD CONSTRAINT fk_content_documents_generation_task_id FOREIGN KEY (generation_task_id) REFERENCES public.content_generation_tasks(id) ON DELETE SET NULL;


--
-- Name: content_publications fk_content_publications_publishing_account_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_publications
    ADD CONSTRAINT fk_content_publications_publishing_account_id FOREIGN KEY (publishing_account_id) REFERENCES public.publishing_accounts(id) ON DELETE RESTRICT;


--
-- Name: monitoring_feedback fk_monitoring_feedback_converted_record; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monitoring_feedback
    ADD CONSTRAINT fk_monitoring_feedback_converted_record FOREIGN KEY (converted_record_id) REFERENCES public.optimization_actions(id) ON DELETE RESTRICT;


--
-- Name: jobs jobs_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: jobs jobs_material_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_material_id_fkey FOREIGN KEY (material_id) REFERENCES public.materials(id) ON DELETE CASCADE;


--
-- Name: keyword_candidates keyword_candidates_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.keyword_candidates
    ADD CONSTRAINT keyword_candidates_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: keyword_candidates keyword_candidates_confirmed_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.keyword_candidates
    ADD CONSTRAINT keyword_candidates_confirmed_item_id_fkey FOREIGN KEY (confirmed_item_id) REFERENCES public.strategy_items(id) ON DELETE SET NULL;


--
-- Name: keyword_candidates keyword_candidates_generation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.keyword_candidates
    ADD CONSTRAINT keyword_candidates_generation_id_fkey FOREIGN KEY (generation_id) REFERENCES public.keyword_generations(id) ON DELETE CASCADE;


--
-- Name: keyword_generations keyword_generations_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.keyword_generations
    ADD CONSTRAINT keyword_generations_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: keyword_generations keyword_generations_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.keyword_generations
    ADD CONSTRAINT keyword_generations_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE SET NULL;


--
-- Name: keyword_profiles keyword_profiles_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.keyword_profiles
    ADD CONSTRAINT keyword_profiles_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: knowledge_profiles knowledge_profiles_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_profiles
    ADD CONSTRAINT knowledge_profiles_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: material_fragments material_fragments_material_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.material_fragments
    ADD CONSTRAINT material_fragments_material_id_fkey FOREIGN KEY (material_id) REFERENCES public.materials(id) ON DELETE CASCADE;


--
-- Name: materials materials_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.materials
    ADD CONSTRAINT materials_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: model_usage model_usage_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_usage
    ADD CONSTRAINT model_usage_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE SET NULL;


--
-- Name: monitoring_batches monitoring_batches_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monitoring_batches
    ADD CONSTRAINT monitoring_batches_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: monitoring_batches monitoring_batches_question_set_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monitoring_batches
    ADD CONSTRAINT monitoring_batches_question_set_id_fkey FOREIGN KEY (question_set_id) REFERENCES public.monitoring_question_sets(id) ON DELETE RESTRICT;


--
-- Name: monitoring_evaluations monitoring_evaluations_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monitoring_evaluations
    ADD CONSTRAINT monitoring_evaluations_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: monitoring_evaluations monitoring_evaluations_sample_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monitoring_evaluations
    ADD CONSTRAINT monitoring_evaluations_sample_id_fkey FOREIGN KEY (sample_id) REFERENCES public.monitoring_samples(id) ON DELETE CASCADE;


--
-- Name: monitoring_feedback monitoring_feedback_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monitoring_feedback
    ADD CONSTRAINT monitoring_feedback_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: monitoring_feedback monitoring_feedback_evaluation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monitoring_feedback
    ADD CONSTRAINT monitoring_feedback_evaluation_id_fkey FOREIGN KEY (evaluation_id) REFERENCES public.monitoring_evaluations(id) ON DELETE CASCADE;


--
-- Name: monitoring_question_sets monitoring_question_sets_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monitoring_question_sets
    ADD CONSTRAINT monitoring_question_sets_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: monitoring_samples monitoring_samples_batch_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monitoring_samples
    ADD CONSTRAINT monitoring_samples_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES public.monitoring_batches(id) ON DELETE CASCADE;


--
-- Name: monitoring_samples monitoring_samples_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monitoring_samples
    ADD CONSTRAINT monitoring_samples_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: optimization_actions optimization_actions_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.optimization_actions
    ADD CONSTRAINT optimization_actions_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: owner_sessions owner_sessions_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.owner_sessions
    ADD CONSTRAINT owner_sessions_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.owners(id) ON DELETE CASCADE;


--
-- Name: prompt_template_versions prompt_template_versions_template_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prompt_template_versions
    ADD CONSTRAINT prompt_template_versions_template_id_fkey FOREIGN KEY (template_id) REFERENCES public.prompt_templates(id) ON DELETE CASCADE;


--
-- Name: strategy_bundles strategy_bundles_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_bundles
    ADD CONSTRAINT strategy_bundles_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: strategy_bundles strategy_bundles_diagnostic_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_bundles
    ADD CONSTRAINT strategy_bundles_diagnostic_run_id_fkey FOREIGN KEY (diagnostic_run_id) REFERENCES public.diagnostic_runs(id) ON DELETE CASCADE;


--
-- Name: strategy_items strategy_items_bundle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_items
    ADD CONSTRAINT strategy_items_bundle_id_fkey FOREIGN KEY (bundle_id) REFERENCES public.strategy_bundles(id) ON DELETE CASCADE;


--
-- Name: strategy_items strategy_items_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_items
    ADD CONSTRAINT strategy_items_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--



INSERT INTO public.alembic_version (version_num) VALUES ('0029');
