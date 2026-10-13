import asyncio
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, Header, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.auth import Authenticated, CsrfAuthenticated
from app.config import Settings
from app.database import (
    Client,
    ContentDocument,
    ContentVersion,
    DatabaseSession,
    Evidence,
    Fact,
    FactConflict,
    FactEvidence,
    Job,
    KnowledgeProfile,
    Material,
    MaterialFragment,
    utc_now,
)
from app.knowledge_context import lock_content_fact_set
from app.responses import error_response, success_response
from app.storage import (
    MAX_FILE_SIZE,
    FileValidationError,
    inspect_upload,
    material_path,
    remove_material_file,
    resolve_storage_key,
    write_material_bytes,
)

MaterialCategory = Literal[
    "license",
    "service",
    "price",
    "team",
    "case",
    "channel",
    "other",
    "image",
]
AuthorizationStatus = Literal[
    "authorized",
    "restricted",
    "not_authorized",
    "not_required",
]
ExtractionStatus = Literal["not_started", "queued", "running", "succeeded", "failed"]
FactCategory = Literal[
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
FactStatus = Literal[
    "confirmed",
    "client_provided",
    "external_source",
    "inferred",
    "conflict",
    "private",
]
PUBLIC_AUTHORIZATIONS = {"authorized", "not_required"}
MAX_UPLOAD_FILES = 20


class FactCreateInput(BaseModel):
    category: FactCategory
    key: str = Field(min_length=1, max_length=150, pattern=r"^[a-z0-9_.-]+$")
    label: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=20_000)
    status: Literal["confirmed", "client_provided", "private"]
    valid_from: date | None
    valid_until: date | None
    evidence_ids: list[UUID] = Field(max_length=100)

    @model_validator(mode="after")
    def validate_dates(self) -> "FactCreateInput":
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until must not be before valid_from")
        return self


class FactUpdateInput(BaseModel):
    version: int = Field(ge=1)
    label: str | None = Field(default=None, min_length=1, max_length=200)
    value: str | None = Field(default=None, min_length=1, max_length=20_000)
    status: FactStatus | None = None
    valid_from: date | None = None
    valid_until: date | None = None

    @field_validator("label", "value", "status", mode="before")
    @classmethod
    def reject_null_required_fields(cls, value: object) -> object:
        if value is None:
            raise ValueError("editable fact fields cannot be null")
        return value

    @model_validator(mode="after")
    def require_change(self) -> "FactUpdateInput":
        if not self.model_fields_set.difference({"version"}):
            raise ValueError("at least one editable field is required")
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until must not be before valid_from")
        return self


class EvidenceInput(BaseModel):
    source_type: Literal["material", "manual", "public_url"]
    material_id: UUID | None
    source_label: str = Field(min_length=1, max_length=200)
    source_url: HttpUrl | None
    quote: str = Field(min_length=1, max_length=20_000)
    observed_at: date
    authorization_status: AuthorizationStatus

    @model_validator(mode="after")
    def validate_source(self) -> "EvidenceInput":
        if self.source_type == "material" and self.material_id is None:
            raise ValueError("material evidence requires material_id")
        if self.source_type != "material" and self.material_id is not None:
            raise ValueError("material_id is only valid for material evidence")
        if self.source_type == "public_url":
            if self.source_url is None or urlparse(str(self.source_url)).scheme != "https":
                raise ValueError("public_url evidence requires an HTTPS URL")
        elif self.source_url is not None:
            raise ValueError("source_url is only valid for public_url evidence")
        return self


class ConfirmFactInput(BaseModel):
    version: int = Field(ge=1)
    evidence_ids: list[UUID] = Field(min_length=1, max_length=100)
    confirmation_note: str = Field(min_length=2, max_length=1000)


class ExtractInput(BaseModel):
    force: bool = False
    languages: list[Literal["zh-CN"]] = Field(min_length=1, max_length=1)


class ConflictResolveInput(BaseModel):
    version: int = Field(ge=1)
    action: Literal["select", "manual", "ignore"]
    selected_evidence_id: UUID | None
    manual_value: str | None = Field(default=None, max_length=20_000)
    resolution_note: str = Field(min_length=2, max_length=1000)

    @model_validator(mode="after")
    def validate_action(self) -> "ConflictResolveInput":
        if self.action == "select" and self.selected_evidence_id is None:
            raise ValueError("select requires selected_evidence_id")
        if self.action == "manual" and not self.manual_value:
            raise ValueError("manual requires manual_value")
        return self


class ServiceProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=20_000)
    target_audience: str = Field(min_length=1, max_length=2000)
    price_statement: str | None = Field(default=None, max_length=2000)
    limitations: list[str] = Field(max_length=100)
    active: bool

    @field_validator("limitations")
    @classmethod
    def validate_limitations(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 500 for value in values):
            raise ValueError("limitations must contain 1-500 character strings")
        return values


class CapabilityProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    type: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=20_000)
    evidence_ids: list[UUID] = Field(max_length=100)
    authorization_status: AuthorizationStatus


class ProhibitedClaimInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    phrase: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=2000)
    source: Literal["system", "user"]


class ExternalPresenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    platform: str = Field(min_length=1, max_length=100)
    account_name: str = Field(min_length=1, max_length=200)
    public_url: HttpUrl
    ownership: Literal["operator", "client", "partner"]
    verified_on: date

    @field_validator("public_url")
    @classmethod
    def require_https(cls, value: HttpUrl) -> HttpUrl:
        if urlparse(str(value)).scheme != "https":
            raise ValueError("external presence URL must use HTTPS")
        return value


class KnowledgeProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    services: list[ServiceProfileInput] = Field(max_length=200)
    capabilities: list[CapabilityProfileInput] = Field(max_length=200)
    prohibited_claims: list[ProhibitedClaimInput] = Field(max_length=200)
    external_presences: list[ExternalPresenceInput] = Field(max_length=200)

    @model_validator(mode="after")
    def require_unique_ids(self) -> "KnowledgeProfileInput":
        for items in (
            self.services,
            self.capabilities,
            self.prohibited_claims,
            self.external_presences,
        ):
            identifiers = [item.id for item in items]
            if len(identifiers) != len(set(identifiers)):
                raise ValueError("knowledge profile item ids must be unique")
        return self


def _material_data(material: Material) -> dict[str, object]:
    return {
        "id": str(material.id),
        "client_id": str(material.client_id),
        "file_name": material.file_name,
        "media_type": material.media_type,
        "size_bytes": material.size_bytes,
        "sha256": material.sha256,
        "category": material.category,
        "authorization_status": material.authorization_status,
        "extraction_status": material.extraction_status,
        "page_count": material.page_count,
        "fragment_count": material.fragment_count,
        "uploaded_at": material.uploaded_at.isoformat(),
        "file_url": (
            f"/api/v1/materials/{material.id}/file"
            if material.category == "image" and material.media_type in {"image/jpeg", "image/png"}
            else None
        ),
        "version": material.version,
    }


def _evidence_data(evidence: Evidence) -> dict[str, object]:
    return {
        "id": str(evidence.id),
        "material_id": str(evidence.material_id) if evidence.material_id else None,
        "source_type": evidence.source_type,
        "source_label": evidence.source_label,
        "source_url": evidence.source_url,
        "quote": evidence.quote,
        "observed_at": evidence.observed_at.isoformat(),
        "authorization_status": evidence.authorization_status,
    }


async def _fact_data(database: DatabaseSession, fact: Fact) -> dict[str, object]:
    evidence_rows = await database.scalars(
        select(Evidence)
        .join(FactEvidence, FactEvidence.evidence_id == Evidence.id)
        .where(
            FactEvidence.fact_id == fact.id,
            Evidence.client_id == fact.client_id,
        )
        .order_by(Evidence.observed_at.desc(), Evidence.id),
    )
    return {
        "id": str(fact.id),
        "client_id": str(fact.client_id),
        "category": fact.category,
        "key": fact.key,
        "label": fact.label,
        "value": fact.value,
        "status": fact.status,
        "confidence": fact.confidence,
        "valid_from": fact.valid_from.isoformat() if fact.valid_from else None,
        "valid_until": fact.valid_until.isoformat() if fact.valid_until else None,
        "evidence": [_evidence_data(item) for item in evidence_rows.all()],
        "version": fact.version,
        "updated_at": fact.updated_at.isoformat(),
    }


def _conflict_data(conflict: FactConflict) -> dict[str, object]:
    return {
        "id": str(conflict.id),
        "client_id": str(conflict.client_id),
        "fact_key": conflict.fact_key,
        "label": conflict.label,
        "candidates": conflict.candidates,
        "status": conflict.status,
        "resolved_value": conflict.resolved_value,
        "resolution_note": conflict.resolution_note,
        "version": conflict.version,
    }


async def _client_or_none(database: DatabaseSession, client_id: UUID) -> Client | None:
    return await database.get(Client, client_id)


async def _usable_evidence(
    database: DatabaseSession,
    client_id: UUID,
    evidence_ids: list[UUID],
) -> list[Evidence]:
    if not evidence_ids:
        return []
    rows = await database.scalars(
        select(Evidence).where(
            Evidence.client_id == client_id,
            Evidence.id.in_(evidence_ids),
        ),
    )
    return list(rows.all())


async def _knowledge_profile_evidence_error(
    database: DatabaseSession,
    client_id: UUID,
    capabilities: list[CapabilityProfileInput],
) -> tuple[int, str] | None:
    evidence_ids = {
        evidence_id for capability in capabilities for evidence_id in capability.evidence_ids
    }
    evidence_rows = (
        await database.scalars(
            select(Evidence).where(
                Evidence.client_id == client_id,
                Evidence.id.in_(evidence_ids),
            ),
        )
        if evidence_ids
        else None
    )
    evidence_by_id = (
        {evidence.id: evidence for evidence in evidence_rows.all()}
        if evidence_rows is not None
        else {}
    )
    if len(evidence_by_id) != len(evidence_ids):
        return 404, "知识库证据不存在"
    authorization_rank = {
        "not_authorized": 0,
        "restricted": 1,
        "authorized": 2,
        "not_required": 2,
    }
    for capability in capabilities:
        if capability.authorization_status in PUBLIC_AUTHORIZATIONS and not capability.evidence_ids:
            return 400, "公开能力必须关联可公开证据"
        if any(
            authorization_rank[capability.authorization_status]
            > authorization_rank[evidence_by_id[evidence_id].authorization_status]
            for evidence_id in capability.evidence_ids
        ):
            return 400, "能力授权不能超过关联证据授权范围"
    return None


def _missing_questions(client: Client, confirmed_keys: set[str]) -> list[dict[str, object]]:
    definitions = (
        (
            "service.primary",
            "主要提供哪些服务或产品?",
            "明确核心服务后才能生成准确的本地需求内容。",
            True,
        ),
        (
            "audience.primary",
            "主要服务哪些客户或使用场景?",
            "适用客群和场景决定推荐问题及内容角度。",
            True,
        ),
        (
            "location.service_area",
            "实际服务范围和不能覆盖的区域是什么?",
            "本地服务必须避免把行政区或服务半径写错。",
            True,
        ),
        (
            "contact.public",
            "哪些联系方式允许公开?",
            "只有获准公开的联系方式才能进入文章。",
            False,
        ),
    )
    return [
        {
            "id": f"{client.id}-{field_key}",
            "field_key": field_key,
            "question": question,
            "reason": reason,
            "blocking": blocking,
        }
        for field_key, question, reason, blocking in definitions
        if field_key not in confirmed_keys
    ]


async def _profile_data(
    database: DatabaseSession,
    client: Client,
    profile: KnowledgeProfile | None,
) -> dict[str, object]:
    managed_keys = set(
        (
            await database.scalars(
                select(Fact.key).where(
                    Fact.client_id == client.id,
                    Fact.status.in_(
                        (
                            "confirmed",
                            "client_provided",
                            "external_source",
                            "inferred",
                        ),
                    ),
                ),
            )
        ).all(),
    )
    return {
        "client_id": str(client.id),
        "services": profile.services if profile else [],
        "capabilities": profile.capabilities if profile else [],
        "prohibited_claims": profile.prohibited_claims if profile else [],
        "external_presences": profile.external_presences if profile else [],
        "missing_questions": _missing_questions(client, managed_keys),
        "version": profile.version if profile else 1,
    }


async def _read_upload(upload: UploadFile) -> bytes:
    content = await upload.read(MAX_FILE_SIZE + 1)
    await upload.close()
    return content


def build_knowledge_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["knowledge"])

    @router.get("/clients/{client_id}/materials")
    async def list_materials(
        request: Request,
        client_id: UUID,
        database: DatabaseSession,
        authentication: Authenticated,
        category: MaterialCategory | None = None,
        extraction_status: ExtractionStatus | None = None,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> Response:
        client = await _client_or_none(database, client_id)
        if client is None:
            return error_response(request, status_code=404, code=40401, message="客户不存在")
        filters = [Material.client_id == client_id]
        if category:
            filters.append(Material.category == category)
        if extraction_status:
            filters.append(Material.extraction_status == extraction_status)
        total = int(
            await database.scalar(select(func.count(Material.id)).where(*filters)) or 0,
        )
        rows = await database.scalars(
            select(Material)
            .where(*filters)
            .order_by(Material.uploaded_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size),
        )
        return success_response(
            request,
            {
                "items": [_material_data(item) for item in rows.all()],
                "total": total,
                "page": page,
                "page_size": page_size,
                "has_next": page * page_size < total,
            },
        )

    @router.post("/clients/{client_id}/materials")
    async def upload_materials(
        request: Request,
        client_id: UUID,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
        files: Annotated[list[UploadFile], File()],
        category: Annotated[MaterialCategory, Form()],
        authorization_status: Annotated[AuthorizationStatus, Form()],
    ) -> Response:
        client = await _client_or_none(database, client_id)
        if client is None:
            return error_response(request, status_code=404, code=40401, message="客户不存在")
        if client.status != "active":
            return error_response(
                request,
                status_code=409,
                code=40902,
                message="客户已暂停或归档，不能新增资料",
            )
        if not files or len(files) > MAX_UPLOAD_FILES:
            return error_response(
                request,
                status_code=413,
                code=41301,
                message="文件数量或体积超过限制",
            )
        created: list[Material] = []
        written_materials: list[tuple[UUID, Path]] = []
        try:
            for upload in files:
                content = await _read_upload(upload)
                if len(content) > MAX_FILE_SIZE:
                    await database.rollback()
                    for _, path in written_materials:
                        await asyncio.to_thread(remove_material_file, path)
                    return error_response(
                        request,
                        status_code=413,
                        code=41301,
                        message="文件数量或体积超过限制",
                    )
                try:
                    inspected = await asyncio.to_thread(
                        inspect_upload,
                        upload.filename or "",
                        upload.content_type,
                        content,
                    )
                except FileValidationError:
                    await database.rollback()
                    for _, path in written_materials:
                        await asyncio.to_thread(remove_material_file, path)
                    return error_response(
                        request,
                        status_code=415,
                        code=41501,
                        message="文件类型或实际内容不允许上传",
                    )
                if category == "image" and inspected.media_type not in {
                    "image/jpeg",
                    "image/png",
                }:
                    await database.rollback()
                    for _, path in written_materials:
                        await asyncio.to_thread(remove_material_file, path)
                    return error_response(
                        request,
                        status_code=415,
                        code=41501,
                        message="企业图片库只允许上传 PNG 或 JPG 图片",
                    )
                material_id = uuid4()
                path = material_path(
                    settings.storage_root,
                    str(client_id),
                    str(material_id),
                    inspected.extension,
                )
                await asyncio.to_thread(write_material_bytes, path, content)
                written_materials.append((material_id, path))
                material = Material(
                    id=material_id,
                    client_id=client_id,
                    file_name=inspected.safe_name,
                    media_type=inspected.media_type,
                    size_bytes=len(content),
                    sha256=sha256(content).hexdigest(),
                    storage_key=str(path.relative_to(settings.storage_root.resolve())),
                    category=category,
                    authorization_status=authorization_status,
                )
                database.add(material)
                created.append(material)
            locked_client = await database.scalar(
                select(Client).where(Client.id == client_id).with_for_update(),
            )
            if locked_client is None or locked_client.status != "active":
                await database.rollback()
                for _, path in written_materials:
                    await asyncio.to_thread(remove_material_file, path)
                return error_response(
                    request,
                    status_code=409,
                    code=40902,
                    message="客户已暂停或归档，不能新增资料",
                )
            await database.commit()
        except Exception:
            await database.rollback()
            persisted_ids: set[UUID] | None = None
            try:
                verification_factory = async_sessionmaker(
                    bind=database.bind,
                    expire_on_commit=False,
                )
                async with verification_factory() as verification:
                    persisted_ids = set(
                        (
                            await verification.scalars(
                                select(Material.id).where(
                                    Material.id.in_(
                                        [item_id for item_id, _ in written_materials],
                                    ),
                                ),
                            )
                        ).all(),
                    )
            except Exception:
                persisted_ids = None
            if persisted_ids is not None:
                for item_id, path in written_materials:
                    if item_id not in persisted_ids:
                        await asyncio.to_thread(remove_material_file, path)
            raise
        for material in created:
            await database.refresh(material)
        return success_response(
            request,
            {"items": [_material_data(item) for item in created]},
            status_code=201,
        )

    @router.get("/materials/{material_id}")
    async def get_material(
        request: Request,
        material_id: UUID,
        database: DatabaseSession,
        authentication: Authenticated,
    ) -> Response:
        material = await database.get(Material, material_id)
        if material is None:
            return error_response(request, status_code=404, code=40401, message="资料不存在")
        fragments = await database.scalars(
            select(MaterialFragment)
            .where(MaterialFragment.material_id == material.id)
            .order_by(MaterialFragment.position),
        )
        return success_response(
            request,
            {
                "material": _material_data(material),
                "fragments": [
                    {
                        "id": str(fragment.id),
                        "page": fragment.page,
                        "text": fragment.text,
                        "extraction_method": fragment.extraction_method,
                    }
                    for fragment in fragments.all()
                ],
            },
        )

    @router.get("/materials/{material_id}/file")
    async def get_material_file(
        request: Request,
        material_id: UUID,
        database: DatabaseSession,
        authentication: Authenticated,
    ) -> Response:
        material = await database.get(Material, material_id)
        if (
            material is None
            or material.category != "image"
            or material.media_type not in {"image/jpeg", "image/png"}
        ):
            return error_response(request, status_code=404, code=40401, message="图片不存在")
        try:
            path = resolve_storage_key(settings.storage_root, material.storage_key)
        except FileValidationError:
            return error_response(request, status_code=404, code=40401, message="图片不存在")
        if not path.is_file():
            return error_response(request, status_code=404, code=40401, message="图片不存在")
        return FileResponse(
            path,
            media_type=material.media_type,
            headers={"Cache-Control": "private, max-age=3600"},
        )

    @router.delete("/materials/{material_id}")
    async def delete_image_material(
        request: Request,
        material_id: UUID,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        material = await database.get(Material, material_id)
        if material is None or material.category != "image":
            return error_response(request, status_code=404, code=40401, message="图片不存在")
        try:
            stored_path = resolve_storage_key(settings.storage_root, material.storage_key)
        except FileValidationError:
            stored_path = None

        versions = list(
            (
                await database.scalars(
                    select(ContentVersion)
                    .join(
                        ContentDocument,
                        ContentDocument.id == ContentVersion.document_id,
                    )
                    .where(ContentDocument.client_id == material.client_id),
                )
            ).all(),
        )
        material_id_text = str(material.id)
        for version in versions:
            current_ids = list(version.image_material_ids or [])
            if material_id_text in current_ids:
                version.image_material_ids = [
                    item for item in current_ids if item != material_id_text
                ]
        await database.delete(material)
        await database.commit()
        if stored_path is not None:
            await asyncio.to_thread(remove_material_file, stored_path)
        return success_response(
            request,
            {"id": material_id_text, "deleted": True},
        )

    @router.post("/materials/{material_id}/extract")
    async def enqueue_material_extraction(
        request: Request,
        material_id: UUID,
        body: ExtractInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
        idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    ) -> Response:
        material = await database.get(Material, material_id)
        if material is None:
            return error_response(request, status_code=404, code=40401, message="资料不存在")
        if material.category == "image":
            return error_response(
                request,
                status_code=409,
                code=40902,
                message="企业图片不参与文字提取",
            )
        client = await database.scalar(
            select(Client).where(Client.id == material.client_id).with_for_update(),
        )
        if client is None or client.status != "active":
            return error_response(
                request,
                status_code=409,
                code=40902,
                message="客户已暂停或归档，不能创建解析任务",
            )
        idempotency_key_value = str(idempotency_key)
        requested_payload: dict[str, object] = {
            "force": body.force,
            "languages": body.languages,
        }
        material_client_id = material.client_id
        requested_material_id = material.id
        existing = await database.scalar(
            select(Job).where(
                Job.client_id == material_client_id,
                Job.job_type == "material_extract",
                Job.idempotency_key == idempotency_key_value,
            ),
        )
        if existing is not None:
            if (
                existing.material_id != requested_material_id
                or existing.payload != requested_payload
            ):
                return error_response(
                    request,
                    status_code=409,
                    code=40903,
                    message="幂等键已用于不同的解析请求",
                )
            return success_response(
                request,
                {
                    "job_id": str(existing.id),
                    "status": existing.status,
                    "progress": existing.progress,
                    "resource_type": "material",
                    "resource_id": str(requested_material_id),
                },
                status_code=202,
            )
        running = await database.scalar(
            select(Job).where(
                Job.material_id == requested_material_id,
                Job.job_type == "material_extract",
                Job.status.in_(("queued", "running")),
            ),
        )
        if running is not None and running.idempotency_key != idempotency_key_value:
            return error_response(
                request,
                status_code=409,
                code=40902,
                message="该资料正在解析",
            )
        job = Job(
            client_id=material_client_id,
            material_id=requested_material_id,
            job_type="material_extract",
            idempotency_key=idempotency_key_value,
            payload=requested_payload,
        )
        database.add(job)
        material.extraction_status = "queued"
        material.extraction_error = None
        material.version += 1
        try:
            await database.commit()
        except IntegrityError:
            await database.rollback()
            raced = await database.scalar(
                select(Job).where(
                    Job.client_id == material_client_id,
                    Job.job_type == "material_extract",
                    Job.idempotency_key == idempotency_key_value,
                ),
            )
            if (
                raced is None
                or raced.material_id != requested_material_id
                or raced.payload != requested_payload
            ):
                active = await database.scalar(
                    select(Job).where(
                        Job.material_id == requested_material_id,
                        Job.job_type == "material_extract",
                        Job.status.in_(("queued", "running")),
                    ),
                )
                if active is not None:
                    return error_response(
                        request,
                        status_code=409,
                        code=40902,
                        message="该资料正在解析",
                    )
                return error_response(
                    request,
                    status_code=409,
                    code=40903,
                    message="幂等键已用于不同的解析请求",
                )
            job = raced
        else:
            await database.refresh(job)
        return success_response(
            request,
            {
                "job_id": str(job.id),
                "status": job.status,
                "progress": job.progress,
                "resource_type": "material",
                "resource_id": str(requested_material_id),
            },
            status_code=202,
        )

    @router.get("/clients/{client_id}/facts")
    async def list_facts(
        request: Request,
        client_id: UUID,
        database: DatabaseSession,
        authentication: Authenticated,
        category: FactCategory | None = None,
        status: FactStatus | None = None,
        q: Annotated[str | None, Query(max_length=200)] = None,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> Response:
        if await _client_or_none(database, client_id) is None:
            return error_response(request, status_code=404, code=40401, message="客户不存在")
        filters = [Fact.client_id == client_id]
        if category:
            filters.append(Fact.category == category)
        if status:
            filters.append(Fact.status == status)
        if q:
            pattern = f"%{q.strip()}%"
            filters.append(or_(Fact.label.ilike(pattern), Fact.value.ilike(pattern)))
        total = int(await database.scalar(select(func.count(Fact.id)).where(*filters)) or 0)
        rows = (
            await database.scalars(
                select(Fact)
                .where(*filters)
                .order_by(Fact.updated_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size),
            )
        ).all()
        return success_response(
            request,
            {
                "items": [await _fact_data(database, item) for item in rows],
                "total": total,
                "page": page,
                "page_size": page_size,
                "has_next": page * page_size < total,
            },
        )

    @router.post("/clients/{client_id}/facts")
    async def create_fact(
        request: Request,
        client_id: UUID,
        body: FactCreateInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        if await _client_or_none(database, client_id) is None:
            return error_response(request, status_code=404, code=40401, message="客户不存在")
        await lock_content_fact_set(database, client_id)
        evidence = await _usable_evidence(database, client_id, body.evidence_ids)
        if len(evidence) != len(set(body.evidence_ids)):
            return error_response(request, status_code=404, code=40401, message="证据不存在")
        if body.status == "confirmed" and (
            not evidence
            or any(item.authorization_status not in PUBLIC_AUTHORIZATIONS for item in evidence)
        ):
            return error_response(
                request,
                status_code=422,
                code=42202,
                message="确认事实缺少可用证据",
            )
        fact = Fact(
            client_id=client_id,
            category=body.category,
            key=body.key,
            label=body.label,
            value=body.value,
            status=body.status,
            confidence=100 if body.status == "confirmed" else 80,
            valid_from=body.valid_from,
            valid_until=body.valid_until,
        )
        database.add(fact)
        try:
            await database.flush()
            database.add_all(
                FactEvidence(fact_id=fact.id, evidence_id=item.id) for item in evidence
            )
            await database.commit()
        except IntegrityError:
            await database.rollback()
            return error_response(
                request,
                status_code=409,
                code=40901,
                message="该事实已存在，请编辑现有事实",
            )
        await database.refresh(fact)
        return success_response(
            request,
            await _fact_data(database, fact),
            status_code=201,
        )

    @router.patch("/facts/{fact_id}")
    async def update_fact(
        request: Request,
        fact_id: UUID,
        body: FactUpdateInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        client_id = await database.scalar(
            select(Fact.client_id).where(Fact.id == fact_id),
        )
        if client_id is None:
            return error_response(request, status_code=404, code=40401, message="事实不存在")
        await lock_content_fact_set(database, client_id)
        current = await database.scalar(
            select(Fact).where(Fact.id == fact_id).with_for_update(),
        )
        if current is None:
            return error_response(request, status_code=404, code=40401, message="事实不存在")
        if current.version != body.version:
            return error_response(
                request,
                status_code=409,
                code=40901,
                message="该事实已被更新，请刷新后重试",
            )
        if body.status == "confirmed":
            return error_response(
                request,
                status_code=422,
                code=42202,
                message="请通过事实确认操作核验证据",
            )
        values = body.model_dump(exclude={"version"}, exclude_unset=True)
        effective_from = values.get("valid_from", current.valid_from)
        effective_until = values.get("valid_until", current.valid_until)
        if effective_from and effective_until and effective_until < effective_from:
            return error_response(
                request,
                status_code=400,
                code=40001,
                message="事实有效期校验失败",
            )
        verification_fields = {"label", "value", "valid_from", "valid_until"}
        if current.status == "confirmed" and verification_fields.intersection(
            body.model_fields_set
        ):
            values["status"] = body.status or "client_provided"
            values["confidence"] = 80
            values["confirmation_note"] = None
        elif "status" in body.model_fields_set:
            values["confidence"] = 80
            values["confirmation_note"] = None
        result = await database.execute(
            update(Fact)
            .where(Fact.id == fact_id, Fact.version == body.version)
            .values(**values, version=Fact.version + 1, updated_at=utc_now())
            .returning(Fact),
        )
        fact = result.scalar_one_or_none()
        if fact is None:
            current = await database.get(Fact, fact_id)
            if current is None:
                return error_response(request, status_code=404, code=40401, message="事实不存在")
            return error_response(
                request,
                status_code=409,
                code=40901,
                message="该事实已被更新，请刷新后重试",
            )
        await database.commit()
        return success_response(request, await _fact_data(database, fact))

    @router.post("/facts/{fact_id}/evidence")
    async def add_fact_evidence(
        request: Request,
        fact_id: UUID,
        body: EvidenceInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        client_id = await database.scalar(
            select(Fact.client_id).where(Fact.id == fact_id),
        )
        if client_id is None:
            return error_response(request, status_code=404, code=40401, message="事实不存在")
        await lock_content_fact_set(database, client_id)
        fact = await database.scalar(
            select(Fact).where(Fact.id == fact_id).with_for_update(),
        )
        if fact is None:
            return error_response(request, status_code=404, code=40401, message="事实不存在")
        if body.material_id is not None:
            material = await database.scalar(
                select(Material).where(
                    Material.id == body.material_id,
                    Material.client_id == fact.client_id,
                ),
            )
            if material is None:
                return error_response(request, status_code=404, code=40401, message="资料不存在")
            authorization_rank = {
                "not_authorized": 0,
                "restricted": 1,
                "authorized": 2,
                "not_required": 2,
            }
            if (
                authorization_rank[body.authorization_status]
                > authorization_rank[material.authorization_status]
            ):
                return error_response(
                    request,
                    status_code=400,
                    code=40001,
                    message="证据授权不能超过原资料授权范围",
                )
        evidence = Evidence(
            client_id=fact.client_id,
            material_id=body.material_id,
            source_type=body.source_type,
            source_label=body.source_label,
            source_url=str(body.source_url) if body.source_url else None,
            quote=body.quote,
            observed_at=body.observed_at,
            authorization_status=body.authorization_status,
        )
        database.add(evidence)
        await database.flush()
        database.add(FactEvidence(fact_id=fact.id, evidence_id=evidence.id))
        fact.version += 1
        await database.commit()
        await database.refresh(fact)
        return success_response(
            request,
            await _fact_data(database, fact),
            status_code=201,
        )

    @router.post("/facts/{fact_id}/confirm")
    async def confirm_fact(
        request: Request,
        fact_id: UUID,
        body: ConfirmFactInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        client_id = await database.scalar(
            select(Fact.client_id).where(Fact.id == fact_id),
        )
        if client_id is None:
            return error_response(request, status_code=404, code=40401, message="事实不存在")
        await lock_content_fact_set(database, client_id)
        fact = await database.scalar(
            select(Fact).where(Fact.id == fact_id).with_for_update(),
        )
        if fact is None:
            return error_response(request, status_code=404, code=40401, message="事实不存在")
        if fact.version != body.version:
            return error_response(
                request,
                status_code=409,
                code=40901,
                message="该事实已被更新，请刷新后重试",
            )
        selected_evidence = await database.scalars(
            select(Evidence)
            .join(FactEvidence, FactEvidence.evidence_id == Evidence.id)
            .where(
                FactEvidence.fact_id == fact.id,
                Evidence.client_id == fact.client_id,
                Evidence.id.in_(body.evidence_ids),
                Evidence.authorization_status.in_(PUBLIC_AUTHORIZATIONS),
            ),
        )
        usable = selected_evidence.all()
        linked_evidence = await database.scalars(
            select(Evidence)
            .join(FactEvidence, FactEvidence.evidence_id == Evidence.id)
            .where(
                FactEvidence.fact_id == fact.id,
                Evidence.client_id == fact.client_id,
            ),
        )
        has_non_public_evidence = any(
            item.authorization_status not in PUBLIC_AUTHORIZATIONS for item in linked_evidence.all()
        )
        open_conflict = await database.scalar(
            select(FactConflict.id).where(
                FactConflict.client_id == fact.client_id,
                FactConflict.fact_key == fact.key,
                FactConflict.status == "open",
            ),
        )
        if (
            len(usable) != len(set(body.evidence_ids))
            or has_non_public_evidence
            or open_conflict is not None
        ):
            return error_response(
                request,
                status_code=422,
                code=42202,
                message="该事实存在冲突或证据不可公开",
            )
        result = await database.execute(
            update(Fact)
            .where(Fact.id == fact.id, Fact.version == body.version)
            .values(
                status="confirmed",
                confidence=100,
                confirmation_note=body.confirmation_note,
                version=Fact.version + 1,
                updated_at=utc_now(),
            )
            .returning(Fact),
        )
        confirmed = result.scalar_one_or_none()
        if confirmed is None:
            return error_response(
                request,
                status_code=409,
                code=40901,
                message="该事实已被更新，请刷新后重试",
            )
        await database.commit()
        return success_response(request, await _fact_data(database, confirmed))

    @router.get("/clients/{client_id}/conflicts")
    async def list_conflicts(
        request: Request,
        client_id: UUID,
        database: DatabaseSession,
        authentication: Authenticated,
        status: Literal["open", "resolved", "ignored"] | None = None,
    ) -> Response:
        if await _client_or_none(database, client_id) is None:
            return error_response(request, status_code=404, code=40401, message="客户不存在")
        filters = [FactConflict.client_id == client_id]
        if status:
            filters.append(FactConflict.status == status)
        rows = await database.scalars(
            select(FactConflict).where(*filters).order_by(FactConflict.id),
        )
        return success_response(
            request,
            {"items": [_conflict_data(item) for item in rows.all()]},
        )

    @router.post("/conflicts/{conflict_id}/resolve")
    async def resolve_conflict(
        request: Request,
        conflict_id: UUID,
        body: ConflictResolveInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        conflict = await database.get(FactConflict, conflict_id)
        if conflict is None:
            return error_response(request, status_code=404, code=40401, message="冲突不存在")
        await lock_content_fact_set(database, conflict.client_id)
        resolved_value: str | None
        selected_evidence: Evidence | None = None
        if body.action == "select":
            selected = next(
                (
                    item
                    for item in conflict.candidates
                    if item.get("evidence_id") == str(body.selected_evidence_id)
                ),
                None,
            )
            if selected is None:
                return error_response(
                    request,
                    status_code=400,
                    code=40001,
                    message="冲突处理字段不匹配",
                )
            selected_evidence = await database.scalar(
                select(Evidence).where(
                    Evidence.id == body.selected_evidence_id,
                    Evidence.client_id == conflict.client_id,
                ),
            )
            if selected_evidence is None:
                return error_response(
                    request,
                    status_code=400,
                    code=40001,
                    message="冲突处理字段不匹配",
                )
            resolved_value = str(selected.get("value", ""))
        else:
            resolved_value = body.manual_value if body.action == "manual" else None
        result = await database.execute(
            update(FactConflict)
            .where(
                FactConflict.id == conflict.id,
                FactConflict.version == body.version,
                FactConflict.status == "open",
            )
            .values(
                status="ignored" if body.action == "ignore" else "resolved",
                resolved_value=resolved_value,
                resolution_note=body.resolution_note,
                version=FactConflict.version + 1,
            )
            .returning(FactConflict),
        )
        resolved = result.scalar_one_or_none()
        if resolved is None:
            return error_response(
                request,
                status_code=409,
                code=40901,
                message="冲突状态已变化，请刷新后重试",
            )
        if body.action != "ignore" and resolved_value:
            target_status = (
                "private"
                if selected_evidence is not None
                and selected_evidence.authorization_status not in PUBLIC_AUTHORIZATIONS
                else "client_provided"
            )
            fact = await database.scalar(
                select(Fact)
                .where(
                    Fact.client_id == conflict.client_id,
                    Fact.key == conflict.fact_key,
                )
                .with_for_update(),
            )
            if fact is None:
                category_prefix = conflict.fact_key.split(".", maxsplit=1)[0]
                category = (
                    category_prefix
                    if category_prefix
                    in {
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
                    }
                    else "service"
                )
                fact = Fact(
                    client_id=conflict.client_id,
                    category=category,
                    key=conflict.fact_key,
                    label=conflict.label,
                    value=resolved_value,
                    status=target_status,
                    confidence=80,
                )
                database.add(fact)
                await database.flush()
            else:
                fact_result = await database.execute(
                    update(Fact)
                    .where(Fact.id == fact.id, Fact.version == fact.version)
                    .values(
                        value=resolved_value,
                        status=target_status,
                        confidence=80,
                        confirmation_note=None,
                        version=Fact.version + 1,
                        updated_at=utc_now(),
                    )
                    .returning(Fact.id),
                )
                if fact_result.scalar_one_or_none() is None:
                    await database.rollback()
                    return error_response(
                        request,
                        status_code=409,
                        code=40901,
                        message="相关事实已被更新，请刷新后重试",
                    )
            if selected_evidence is not None:
                linked = await database.get(
                    FactEvidence,
                    (fact.id, selected_evidence.id),
                )
                if linked is None:
                    database.add(
                        FactEvidence(
                            fact_id=fact.id,
                            evidence_id=selected_evidence.id,
                        ),
                    )
        elif body.action == "ignore":
            fact = await database.scalar(
                select(Fact)
                .where(
                    Fact.client_id == conflict.client_id,
                    Fact.key == conflict.fact_key,
                )
                .with_for_update(),
            )
            if fact is not None:
                fact_result = await database.execute(
                    update(Fact)
                    .where(Fact.id == fact.id, Fact.version == fact.version)
                    .values(
                        status="private",
                        confidence=80,
                        confirmation_note=None,
                        version=Fact.version + 1,
                        updated_at=utc_now(),
                    )
                    .returning(Fact.id),
                )
                if fact_result.scalar_one_or_none() is None:
                    await database.rollback()
                    return error_response(
                        request,
                        status_code=409,
                        code=40901,
                        message="相关事实已被更新，请刷新后重试",
                    )
        await database.commit()
        return success_response(request, _conflict_data(resolved))

    @router.get("/clients/{client_id}/knowledge-profile")
    async def get_knowledge_profile(
        request: Request,
        client_id: UUID,
        database: DatabaseSession,
        authentication: Authenticated,
    ) -> Response:
        client = await _client_or_none(database, client_id)
        if client is None:
            return error_response(
                request,
                status_code=404,
                code=40401,
                message="客户知识库不存在",
            )
        profile = await database.get(KnowledgeProfile, client_id)
        return success_response(request, await _profile_data(database, client, profile))

    @router.patch("/clients/{client_id}/knowledge-profile")
    async def update_knowledge_profile(
        request: Request,
        client_id: UUID,
        body: KnowledgeProfileInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        client = await _client_or_none(database, client_id)
        if client is None:
            return error_response(
                request,
                status_code=404,
                code=40401,
                message="客户知识库不存在",
            )
        await lock_content_fact_set(database, client_id)
        evidence_error = await _knowledge_profile_evidence_error(
            database,
            client_id,
            body.capabilities,
        )
        if evidence_error is not None:
            status_code, message = evidence_error
            return error_response(
                request,
                status_code=status_code,
                code=40401 if status_code == 404 else 40001,
                message=message,
            )
        profile = await database.get(KnowledgeProfile, client_id)
        serialized = body.model_dump(exclude={"version"}, mode="json")
        if profile is None:
            if body.version != 1:
                return error_response(
                    request,
                    status_code=409,
                    code=40901,
                    message="知识库已被更新，请刷新后重试",
                )
            profile = KnowledgeProfile(
                client_id=client_id,
                **serialized,
                version=2,
            )
            database.add(profile)
        else:
            result = await database.execute(
                update(KnowledgeProfile)
                .where(
                    KnowledgeProfile.client_id == client_id,
                    KnowledgeProfile.version == body.version,
                )
                .values(
                    **serialized,
                    version=KnowledgeProfile.version + 1,
                    updated_at=utc_now(),
                )
                .returning(KnowledgeProfile),
            )
            updated = result.scalar_one_or_none()
            if updated is None:
                return error_response(
                    request,
                    status_code=409,
                    code=40901,
                    message="知识库已被更新，请刷新后重试",
                )
            profile = updated
        try:
            await database.commit()
        except IntegrityError:
            await database.rollback()
            return error_response(
                request,
                status_code=409,
                code=40901,
                message="知识库已被更新，请刷新后重试",
            )
        return success_response(request, await _profile_data(database, client, profile))

    return router
