from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, Request
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Owner(Base):
    __tablename__ = "owners"
    __table_args__ = (CheckConstraint("singleton_key = 1", name="ck_owners_singleton_key"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    singleton_key: Mapped[int] = mapped_column(Integer, unique=True, default=1)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(Text)
    session_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class OwnerSession(Base):
    __tablename__ = "owner_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("owners.id", ondelete="CASCADE"),
        index=True,
    )
    csrf_hash: Mapped[str] = mapped_column(String(64))
    session_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    standard_name: Mapped[str] = mapped_column(String(200), index=True)
    normalized_name: Mapped[str] = mapped_column(Text, unique=True)
    short_name: Mapped[str | None] = mapped_column(String(100))
    industry_code: Mapped[str] = mapped_column(String(100), index=True)
    industry_name: Mapped[str] = mapped_column(String(100))
    province: Mapped[str] = mapped_column(String(100))
    city: Mapped[str] = mapped_column(String(100))
    district: Mapped[str] = mapped_column(String(100))
    address: Mapped[str] = mapped_column(String(500))
    contact_phone: Mapped[str | None] = mapped_column(String(50))
    contact_wechat: Mapped[str | None] = mapped_column(String(100))
    business_hours: Mapped[str | None] = mapped_column(String(200))
    service_radius: Mapped[str | None] = mapped_column(String(200))
    cooperation_started_on: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    current_level: Mapped[str] = mapped_column(String(2), default="L0")
    fact_completeness: Mapped[int] = mapped_column(Integer, default=0)
    blocking_issue_count: Mapped[int] = mapped_column(Integer, default=0)
    next_action: Mapped[str] = mapped_column(String(200), default="完善企业资料")
    archived_reason: Mapped[str | None] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="CASCADE"),
        index=True,
    )
    file_name: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(150))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    category: Mapped[str] = mapped_column(String(30), index=True)
    authorization_status: Mapped[str] = mapped_column(String(30))
    extraction_status: Mapped[str] = mapped_column(
        String(30),
        default="not_started",
        index=True,
    )
    extraction_error: Mapped[str | None] = mapped_column(String(500))
    page_count: Mapped[int | None] = mapped_column(Integer)
    fragment_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    version: Mapped[int] = mapped_column(Integer, default=1)


class MaterialFragment(Base):
    __tablename__ = "material_fragments"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    material_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("materials.id", ondelete="CASCADE"),
        index=True,
    )
    page: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(20))
    sensitivity_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    position: Mapped[int] = mapped_column(Integer)


class Fact(Base):
    __tablename__ = "facts"
    __table_args__ = (UniqueConstraint("client_id", "key", name="uq_facts_client_key"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="CASCADE"),
        index=True,
    )
    category: Mapped[str] = mapped_column(String(30), index=True)
    key: Mapped[str] = mapped_column(String(150))
    label: Mapped[str] = mapped_column(String(200))
    value: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), index=True)
    confidence: Mapped[int] = mapped_column(Integer, default=100)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    confirmation_note: Mapped[str | None] = mapped_column(String(1000))
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="CASCADE"),
        index=True,
    )
    material_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("materials.id", ondelete="SET NULL"),
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(30))
    source_label: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(2000))
    quote: Mapped[str] = mapped_column(Text)
    observed_at: Mapped[date] = mapped_column(Date)
    authorization_status: Mapped[str] = mapped_column(String(30))


class FactEvidence(Base):
    __tablename__ = "fact_evidence"

    fact_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("facts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    evidence_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("evidence.id", ondelete="CASCADE"),
        primary_key=True,
    )


class FactConflict(Base):
    __tablename__ = "fact_conflicts"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="CASCADE"),
        index=True,
    )
    fact_key: Mapped[str] = mapped_column(String(150))
    label: Mapped[str] = mapped_column(String(200))
    candidates: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    resolved_value: Mapped[str | None] = mapped_column(Text)
    resolution_note: Mapped[str | None] = mapped_column(String(1000))
    version: Mapped[int] = mapped_column(Integer, default=1)


class KnowledgeProfile(Base):
    __tablename__ = "knowledge_profiles"

    client_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="CASCADE"),
        primary_key=True,
    )
    services: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    capabilities: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    prohibited_claims: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    external_presences: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class DiagnosticRun(Base):
    __tablename__ = "diagnostic_runs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="CASCADE"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), index=True)
    current_level: Mapped[str] = mapped_column(String(2), default="L0")
    scores: Mapped[dict[str, int | None]] = mapped_column(JSON, default=dict)
    scope: Mapped[list[str]] = mapped_column(JSON, default=list)
    monitoring_window_days: Mapped[int] = mapped_column(Integer)
    fact_snapshot_id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    fact_snapshot: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    platform_results: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    monitoring_sample_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DiagnosticIssue(Base):
    __tablename__ = "diagnostic_issues"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    diagnostic_run_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("diagnostic_runs.id", ondelete="CASCADE"),
        index=True,
    )
    client_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="CASCADE"),
        index=True,
    )
    category: Mapped[str] = mapped_column(String(20), index=True)
    severity: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    explanation: Mapped[str] = mapped_column(Text)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    suggested_action: Mapped[str] = mapped_column(Text)
    target_page: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    note: Mapped[str | None] = mapped_column(String(1000))
    version: Mapped[int] = mapped_column(Integer, default=1)


class StrategyBundle(Base):
    __tablename__ = "strategy_bundles"
    __table_args__ = (UniqueConstraint("client_id", name="uq_strategy_bundles_client_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="CASCADE"),
        index=True,
    )
    diagnostic_run_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("diagnostic_runs.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    prompt_template_code: Mapped[str | None] = mapped_column(String(80))
    prompt_template_version: Mapped[int | None] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    version: Mapped[int] = mapped_column(Integer, default=1)


class StrategyItem(Base):
    __tablename__ = "strategy_items"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    bundle_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("strategy_bundles.id", ondelete="CASCADE"),
        index=True,
    )
    client_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="CASCADE"),
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(20), index=True)
    text: Mapped[str] = mapped_column(Text)
    family: Mapped[str | None] = mapped_column(String(30), index=True)
    keyword_type: Mapped[str | None] = mapped_column(String(30), index=True)
    provenance: Mapped[str] = mapped_column(String(30))
    target_level: Mapped[str] = mapped_column(String(2))
    priority: Mapped[int] = mapped_column(Integer)
    rationale: Mapped[str] = mapped_column(Text)
    main_keyword: Mapped[str | None] = mapped_column(String(300))
    user_intent: Mapped[str | None] = mapped_column(String(300))
    recommended_content_type: Mapped[str | None] = mapped_column(String(80))
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    selected: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class KeywordProfile(Base):
    __tablename__ = "keyword_profiles"

    client_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="CASCADE"),
        primary_key=True,
    )
    primary_keyword: Mapped[str] = mapped_column(String(300))
    regions: Mapped[list[str]] = mapped_column(JSON, default=list)
    secondary_keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    keyword_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    recommended_count: Mapped[int] = mapped_column(Integer, default=12)
    knowledge_fingerprint: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class KeywordGeneration(Base):
    __tablename__ = "keyword_generations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="CASCADE"),
        index=True,
    )
    job_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("jobs.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    primary_keyword: Mapped[str] = mapped_column(String(300))
    regions: Mapped[list[str]] = mapped_column(JSON, default=list)
    secondary_keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    keyword_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    knowledge_fingerprint: Mapped[str] = mapped_column(String(64))
    target_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    generated_count: Mapped[int] = mapped_column(Integer, default=0)
    filtered_count: Mapped[int] = mapped_column(Integer, default=0)
    confirmed_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KeywordCandidate(Base):
    __tablename__ = "keyword_candidates"
    __table_args__ = (
        UniqueConstraint(
            "client_id",
            "normalized_text",
            name="uq_keyword_candidates_client_normalized_text",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    generation_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("keyword_generations.id", ondelete="CASCADE"),
        index=True,
    )
    client_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="CASCADE"),
        index=True,
    )
    text: Mapped[str] = mapped_column(Text)
    normalized_text: Mapped[str] = mapped_column(String(500))
    main_keyword: Mapped[str] = mapped_column(String(300))
    keyword_type: Mapped[str] = mapped_column(String(30), index=True)
    user_intent: Mapped[str] = mapped_column(String(300))
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    secondary_keyword: Mapped[str | None] = mapped_column(String(300), nullable=True)
    recommended_content_type: Mapped[str] = mapped_column(String(80))
    priority: Mapped[int] = mapped_column(Integer, default=2)
    selected: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    confirmed_item_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("strategy_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ContentBrief(Base):
    __tablename__ = "content_briefs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    bundle_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("strategy_bundles.id", ondelete="CASCADE"),
        index=True,
    )
    client_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(30))
    target_question_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    target_keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    target_level: Mapped[str] = mapped_column(String(2))
    audience: Mapped[str] = mapped_column(Text)
    angle: Mapped[str] = mapped_column(Text)
    required_fact_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    required_evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    expected_recommendation_reason: Mapped[str] = mapped_column(Text)
    prohibited_claims: Mapped[list[str]] = mapped_column(JSON, default=list)
    retest_questions: Mapped[list[str]] = mapped_column(JSON, default=list)
    suggested_channel_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    priority: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="planned", index=True)
    keyword_strategy_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    keyword_type: Mapped[str | None] = mapped_column(String(30))
    prompt_template_code: Mapped[str | None] = mapped_column(String(80))
    prompt_template_version: Mapped[int | None] = mapped_column(Integer)
    target_channel_id: Mapped[str | None] = mapped_column(String(80))
    contact_policy: Mapped[str | None] = mapped_column(String(30))
    prompt_layers_snapshot: Mapped[list[dict[str, object]] | None] = mapped_column(JSON)
    contact_allowed_urls: Mapped[list[str] | None] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)


class FactSnapshot(Base):
    __tablename__ = "fact_snapshots"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="CASCADE"),
        index=True,
    )
    brief_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("content_briefs.id", ondelete="RESTRICT"),
        index=True,
    )
    brief_version: Mapped[int] = mapped_column(Integer)
    facts: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    evidence: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    brief_context: Mapped[dict[str, object]] = mapped_column(JSON)
    prohibited_claims: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ContentGenerationTask(Base):
    __tablename__ = "content_generation_tasks"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="CASCADE"),
        index=True,
    )
    platform_type: Mapped[str] = mapped_column(String(30), default="self_media")
    keyword_snapshots: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    channel_ids: Mapped[list[str]] = mapped_column(JSON)
    article_count_per_channel: Mapped[int] = mapped_column(Integer)
    length: Mapped[str] = mapped_column(String(20))
    content_form_codes: Mapped[list[str]] = mapped_column(JSON)
    total_count: Mapped[int] = mapped_column(Integer)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ContentDocument(Base):
    __tablename__ = "content_documents"
    __table_args__ = (UniqueConstraint("client_id", "brief_id", name="uq_content_documents_brief"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="CASCADE"),
        index=True,
    )
    brief_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("content_briefs.id", ondelete="RESTRICT"),
        index=True,
    )
    generation_task_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("content_generation_tasks.id", ondelete="SET NULL"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(30), default="brief", index=True)
    current_version_id: Mapped[UUID | None] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class ContentVersion(Base):
    __tablename__ = "content_versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_content_versions_document_number",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("content_documents.id", ondelete="CASCADE"),
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    title_candidates: Mapped[list[dict[str, str]] | None] = mapped_column(JSON)
    body_markdown: Mapped[str] = mapped_column(Text)
    outline_markdown: Mapped[str | None] = mapped_column(Text)
    change_type: Mapped[str] = mapped_column(String(30))
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str | None] = mapped_column(String(100))
    fact_snapshot_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("fact_snapshots.id", ondelete="RESTRICT"),
        index=True,
    )
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    prompt_template_code: Mapped[str | None] = mapped_column(String(80))
    prompt_template_version: Mapped[int | None] = mapped_column(Integer)
    target_channel_id: Mapped[str | None] = mapped_column(String(80))
    contact_policy: Mapped[str | None] = mapped_column(String(30))
    prompt_layers_snapshot: Mapped[list[dict[str, object]] | None] = mapped_column(JSON)
    contact_allowed_urls: Mapped[list[str] | None] = mapped_column(JSON)
    contact_sanitization_report: Mapped[dict[str, object] | None] = mapped_column(JSON)
    image_material_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    input_hash: Mapped[str | None] = mapped_column(String(64))
    output_hash: Mapped[str | None] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    fallback_reason: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ContentPublication(Base):
    __tablename__ = "content_publications"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "version_id",
            "publishing_account_id",
            name="uq_content_publications_document_version_account",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("content_documents.id", ondelete="CASCADE"),
        index=True,
    )
    version_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("content_versions.id", ondelete="RESTRICT"),
        index=True,
    )
    publishing_account_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("publishing_accounts.id", ondelete="RESTRICT"),
        index=True,
    )
    channel_id: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    platform_post_id: Mapped[str | None] = mapped_column(String(200))
    public_url: Mapped[str | None] = mapped_column(String(1000))
    error_message: Mapped[str | None] = mapped_column(String(500))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class PublishingChannelConfig(Base):
    __tablename__ = "publishing_channel_configs"

    channel_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    connection_status: Mapped[str] = mapped_column(
        String(30),
        default="disconnected",
        index=True,
    )
    account_name: Mapped[str | None] = mapped_column(String(200))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class PublishingAccount(Base):
    """One isolated browser session for one account on one publishing platform."""

    __tablename__ = "publishing_accounts"
    __table_args__ = (
        UniqueConstraint(
            "channel_id",
            "display_name",
            name="uq_publishing_accounts_channel_display_name",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    channel_id: Mapped[str] = mapped_column(String(80), index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    connection_status: Mapped[str] = mapped_column(
        String(30),
        default="disconnected",
        index=True,
    )
    account_name: Mapped[str | None] = mapped_column(String(200))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class ContentQualityCheck(Base):
    __tablename__ = "content_quality_checks"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_version_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("content_versions.id", ondelete="CASCADE"),
        index=True,
    )
    overall_status: Mapped[str] = mapped_column(String(20), index=True)
    dimensions: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    findings: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ContentChannelVariant(Base):
    __tablename__ = "content_channel_variants"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "channel_id",
            name="uq_content_channel_variants_document_channel",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("content_documents.id", ondelete="CASCADE"),
        index=True,
    )
    channel_id: Mapped[str] = mapped_column(String(100))
    version_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("content_versions.id", ondelete="CASCADE"),
        index=True,
    )
    adaptation_note: Mapped[str] = mapped_column(Text)


class ChannelRecommendation(Base):
    __tablename__ = "channel_recommendations"
    __table_args__ = (
        UniqueConstraint(
            "client_id",
            "generation_id",
            "brief_id",
            "channel_id",
            name="uq_channel_recommendations_generation_brief_channel",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="CASCADE"),
        index=True,
    )
    generation_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    brief_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("content_briefs.id", ondelete="SET NULL"),
        index=True,
    )
    content_document_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("content_documents.id", ondelete="SET NULL"),
        index=True,
    )
    channel_id: Mapped[str] = mapped_column(String(100), index=True)
    catalog_version: Mapped[str] = mapped_column(String(30))
    channel_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    brief_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    priority: Mapped[int] = mapped_column(Integer)
    fit_score: Mapped[int] = mapped_column(Integer)
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    recommended_content_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    required_actions: Mapped[list[str]] = mapped_column(JSON, default=list)
    required_adaptation: Mapped[str] = mapped_column(Text, default="")
    account_positioning: Mapped[str] = mapped_column(Text, default="")
    authorization_note: Mapped[str] = mapped_column(Text, default="")
    cost_note: Mapped[str] = mapped_column(Text, default="")
    risk_note: Mapped[str] = mapped_column(Text, default="")
    target_ecosystems: Mapped[list[str]] = mapped_column(JSON, default=list)
    caveat: Mapped[str] = mapped_column(Text)
    source_brief_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ContentExport(Base):
    __tablename__ = "content_exports"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("content_documents.id", ondelete="CASCADE"),
        index=True,
    )
    content_version_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("content_versions.id", ondelete="RESTRICT"),
        index=True,
    )
    format: Mapped[str] = mapped_column(String(20))
    include_sources: Mapped[bool] = mapped_column(Boolean, default=True)
    storage_key: Mapped[str | None] = mapped_column(String(500), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MonitoringQuestionSet(Base):
    __tablename__ = "monitoring_question_sets"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200))
    frozen: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    questions: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class MonitoringBatch(Base):
    __tablename__ = "monitoring_batches"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="CASCADE"),
        index=True,
    )
    question_set_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("monitoring_question_sets.id", ondelete="RESTRICT"),
        index=True,
    )
    question_set_version: Mapped[int] = mapped_column(Integer)
    question_snapshot: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    platform_ids: Mapped[list[str]] = mapped_column(JSON)
    api_sample_count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MonitoringSample(Base):
    __tablename__ = "monitoring_samples"
    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "platform_id",
            "question_id",
            "attempt",
            name="uq_monitoring_samples_batch_platform_question_attempt",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("monitoring_batches.id", ondelete="CASCADE"),
        index=True,
    )
    client_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="CASCADE"),
        index=True,
    )
    platform_id: Mapped[str] = mapped_column(String(50), index=True)
    platform_name: Mapped[str] = mapped_column(String(100))
    collection_mode: Mapped[str] = mapped_column(String(30), index=True)
    question_id: Mapped[str] = mapped_column(String(100), index=True)
    question_text: Mapped[str] = mapped_column(Text)
    question_family: Mapped[str] = mapped_column(String(50), index=True)
    is_brand_query: Mapped[bool] = mapped_column(Boolean, default=False)
    question_priority: Mapped[int] = mapped_column(Integer, default=1)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(30), default="not_executed", index=True)
    raw_answer: Mapped[str | None] = mapped_column(Text)
    asked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    failure_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class MonitoringEvaluation(Base):
    __tablename__ = "monitoring_evaluations"
    __table_args__ = (UniqueConstraint("sample_id", name="uq_monitoring_evaluations_sample_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    sample_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("monitoring_samples.id", ondelete="CASCADE"),
        index=True,
    )
    client_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="CASCADE"),
        index=True,
    )
    brand_found: Mapped[bool] = mapped_column(Boolean)
    correctly_associated: Mapped[bool] = mapped_column(Boolean)
    recommended: Mapped[bool] = mapped_column(Boolean)
    recommendation_supported: Mapped[bool | None] = mapped_column(Boolean)
    facts_accurate: Mapped[bool | None] = mapped_column(Boolean)
    source_visible: Mapped[bool] = mapped_column(Boolean, default=False)
    mentioned_name: Mapped[str | None] = mapped_column(String(200))
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    incorrect_facts: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    visible_sources: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    note: Mapped[str | None] = mapped_column(String(1000))
    evaluator: Mapped[str] = mapped_column(String(20), default="system")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class MonitoringFeedback(Base):
    __tablename__ = "monitoring_feedback"
    __table_args__ = (
        UniqueConstraint(
            "evaluation_id",
            "action_type",
            name="uq_monitoring_feedback_evaluation_action",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="CASCADE"),
        index=True,
    )
    evaluation_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("monitoring_evaluations.id", ondelete="CASCADE"),
        index=True,
    )
    action_type: Mapped[str] = mapped_column(String(40), index=True)
    reason: Mapped[str] = mapped_column(Text)
    target_level: Mapped[str] = mapped_column(String(2))
    target_page: Mapped[str] = mapped_column(String(3))
    converted_record_type: Mapped[str] = mapped_column(String(40))
    converted_record_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("optimization_actions.id", ondelete="RESTRICT"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OptimizationAction(Base):
    __tablename__ = "optimization_actions"
    __table_args__ = (
        UniqueConstraint(
            "source_type",
            "source_id",
            "action_type",
            name="uq_optimization_actions_source_action",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="CASCADE"),
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(40), index=True)
    source_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    action_type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(300))
    reason: Mapped[str] = mapped_column(Text)
    target_level: Mapped[str] = mapped_column(String(2))
    target_page: Mapped[str] = mapped_column(String(3), index=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"
    __table_args__ = (UniqueConstraint("code", name="uq_prompt_templates_code"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(30), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500))
    template_text: Mapped[str] = mapped_column(Text)
    default_text: Mapped[str] = mapped_column(Text)
    editable: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    variable_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    required_fact_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    contact_policy: Mapped[str | None] = mapped_column(String(30), index=True)
    default_contact_policy: Mapped[str | None] = mapped_column(String(30))
    channel_id: Mapped[str | None] = mapped_column(String(80), index=True)
    source_url: Mapped[str | None] = mapped_column(String(2000))
    verified_at: Mapped[date | None] = mapped_column(Date)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class PromptTemplateVersion(Base):
    __tablename__ = "prompt_template_versions"
    __table_args__ = (
        UniqueConstraint(
            "template_id",
            "version_number",
            name="uq_prompt_template_versions_number",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    template_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("prompt_templates.id", ondelete="CASCADE"),
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer)
    template_text: Mapped[str] = mapped_column(Text)
    contact_policy: Mapped[str | None] = mapped_column(String(30))
    change_note: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProviderSetting(Base):
    __tablename__ = "provider_settings"
    __table_args__ = (
        CheckConstraint(
            "provider IN ('qwen', 'deepseek', 'doubao', 'wenxin', 'yuanbao', 'kimi')",
            name="ck_provider_settings_provider",
        ),
    )

    provider: Mapped[str] = mapped_column(String(20), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    base_url: Mapped[str] = mapped_column(String(500))
    workspace_id: Mapped[str | None] = mapped_column(String(200))
    writer_model: Mapped[str | None] = mapped_column(String(100))
    reviewer_model: Mapped[str | None] = mapped_column(String(100))
    fallback_model: Mapped[str | None] = mapped_column(String(100))
    daily_budget_cny_fen: Mapped[int] = mapped_column(Integer, default=0)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    encrypted_api_key: Mapped[bytes | None] = mapped_column(LargeBinary)
    secret_suffix: Mapped[str | None] = mapped_column(String(4))
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_status: Mapped[str] = mapped_column(String(20), default="not_tested")
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class RuntimeSetting(Base):
    __tablename__ = "runtime_settings"
    __table_args__ = (
        CheckConstraint("singleton_key = 1", name="ck_runtime_settings_singleton_key"),
    )

    singleton_key: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    default_client_monthly_budget_cny_fen: Mapped[int] = mapped_column(
        Integer,
        default=30_000,
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class ModelUsage(Base):
    __tablename__ = "model_usage"
    __table_args__ = (Index("ix_model_usage_provider_day", "provider", "usage_date"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    client_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="SET NULL"),
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(100))
    purpose: Mapped[str] = mapped_column(String(50))
    fact_snapshot_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    pricing_version: Mapped[str | None] = mapped_column(String(50))
    usage_date: Mapped[date] = mapped_column(Date)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_cny_fen: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20))
    fallback_reason: Mapped[str | None] = mapped_column(String(100))
    input_hash: Mapped[str | None] = mapped_column(String(64))
    output_hash: Mapped[str | None] = mapped_column(String(64))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint(
            "client_id",
            "job_type",
            "idempotency_key",
            name="uq_jobs_client_type_idempotency",
        ),
        Index(
            "uq_jobs_active_material_extract",
            "material_id",
            unique=True,
            postgresql_where=text(
                "material_id IS NOT NULL AND job_type = 'material_extract' "
                "AND status IN ('queued', 'running')",
            ),
            sqlite_where=text(
                "material_id IS NOT NULL AND job_type = 'material_extract' "
                "AND status IN ('queued', 'running')",
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="CASCADE"),
        index=True,
    )
    material_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("materials.id", ondelete="CASCADE"),
        index=True,
    )
    job_type: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


async def get_database_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session


DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
