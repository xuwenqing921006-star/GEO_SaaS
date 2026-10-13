from datetime import date
from typing import Annotated, Literal
from unicodedata import normalize
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import asc, desc, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.auth import Authenticated, CsrfAuthenticated
from app.database import (
    Client,
    DatabaseSession,
    Fact,
    FactConflict,
    Job,
    Material,
    utc_now,
)
from app.responses import error_response, success_response

ClientStatus = Literal["active", "paused", "archived"]
INDUSTRY_NAMES = {
    "art_education": "少儿美术",
    "housekeeping": "家政服务",
    "repair": "维修服务",
}


def normalize_client_name(value: str) -> str:
    return " ".join(normalize("NFKC", value).casefold().split())


COMPLETENESS_FACT_STATUSES = (
    "confirmed",
    "client_provided",
    "external_source",
    "inferred",
)


def calculate_fact_completeness(client: Client, fact_keys: set[str]) -> int:
    """Calculate the customer-facing profile percentage from eight basic groups."""

    checks = (
        (10, bool(client.standard_name.strip())),
        (
            10,
            bool(client.industry_code.strip()) or "identity.industry" in fact_keys,
        ),
        (
            15,
            bool(client.province.strip() and client.city.strip() and client.district.strip())
            or bool(
                fact_keys
                & {
                    "location.administrative_area",
                    "location.service_area",
                    "location.address",
                },
            ),
        ),
        (
            20,
            bool(
                fact_keys
                & {
                    "service.primary",
                    "service.details",
                    "service.promotion_focus",
                },
            ),
        ),
        (15, "identity.introduction" in fact_keys),
        (10, "audience.primary" in fact_keys),
        (
            10,
            any(key.startswith("capability.") for key in fact_keys),
        ),
        (
            10,
            bool(client.contact_phone or client.contact_wechat)
            or bool(
                fact_keys
                & {
                    "contact.public",
                    "contact.phone",
                    "contact.wechat",
                },
            ),
        ),
    )
    return sum(weight for weight, present in checks if present)


async def _fact_keys_by_client(
    database: DatabaseSession,
    client_ids: list[UUID],
) -> dict[UUID, set[str]]:
    if not client_ids:
        return {}
    today = date.today()
    rows = (
        await database.execute(
            select(Fact.client_id, Fact.key).where(
                Fact.client_id.in_(client_ids),
                Fact.status.in_(COMPLETENESS_FACT_STATUSES),
                (Fact.valid_from.is_(None) | (Fact.valid_from <= today)),
                (Fact.valid_until.is_(None) | (Fact.valid_until >= today)),
                Fact.value != "",
            ),
        )
    ).all()
    keys_by_client: dict[UUID, set[str]] = {client_id: set() for client_id in client_ids}
    for client_id, key in rows:
        keys_by_client.setdefault(client_id, set()).add(key)
    return keys_by_client


class ClientCreateInput(BaseModel):
    standard_name: str = Field(min_length=1, max_length=200)
    short_name: str | None = Field(default=None, max_length=100)
    industry_code: str = Field(min_length=1, max_length=100)
    province: str = Field(min_length=1, max_length=100)
    city: str = Field(min_length=1, max_length=100)
    district: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=1, max_length=500)
    contact_phone: str | None = Field(default=None, max_length=50)
    contact_wechat: str | None = Field(default=None, max_length=100)
    business_hours: str | None = Field(default=None, max_length=200)
    service_radius: str | None = Field(default=None, max_length=200)
    cooperation_started_on: date
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("standard_name")
    @classmethod
    def validate_standard_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("standard name cannot be blank")
        return cleaned


class ClientUpdateInput(BaseModel):
    version: int = Field(ge=1)
    standard_name: str | None = Field(default=None, min_length=1, max_length=200)
    short_name: str | None = Field(default=None, max_length=100)
    industry_code: str | None = Field(default=None, min_length=1, max_length=100)
    province: str | None = Field(default=None, min_length=1, max_length=100)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    district: str | None = Field(default=None, min_length=1, max_length=100)
    address: str | None = Field(default=None, min_length=1, max_length=500)
    contact_phone: str | None = Field(default=None, max_length=50)
    contact_wechat: str | None = Field(default=None, max_length=100)
    business_hours: str | None = Field(default=None, max_length=200)
    service_radius: str | None = Field(default=None, max_length=200)
    cooperation_started_on: date | None = None
    notes: str | None = Field(default=None, max_length=5000)
    status: Literal["active", "paused"] | None = None

    @field_validator("standard_name")
    @classmethod
    def validate_standard_name(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("standard name cannot be null")
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("standard name cannot be blank")
        return cleaned

    @field_validator(
        "industry_code",
        "province",
        "city",
        "district",
        "address",
        "cooperation_started_on",
        "status",
        mode="before",
    )
    @classmethod
    def reject_null_required_fields(cls, value: object) -> object:
        if value is None:
            raise ValueError("required client fields cannot be null")
        return value

    @model_validator(mode="after")
    def require_change(self) -> "ClientUpdateInput":
        if not self.model_fields_set.difference({"version"}):
            raise ValueError("at least one editable field is required")
        return self


class ArchiveInput(BaseModel):
    version: int = Field(ge=1)
    reason: str = Field(min_length=2, max_length=200)


class VersionInput(BaseModel):
    version: int = Field(ge=1)


def _summary(
    client: Client,
    *,
    fact_keys: set[str] | None = None,
) -> dict[str, object]:
    return {
        "id": str(client.id),
        "standard_name": client.standard_name,
        "short_name": client.short_name,
        "industry_code": client.industry_code,
        "industry_name": client.industry_name,
        "province": client.province,
        "city": client.city,
        "district": client.district,
        "status": client.status,
        "current_level": client.current_level,
        "fact_completeness": calculate_fact_completeness(
            client,
            fact_keys or set(),
        ),
        "blocking_issue_count": client.blocking_issue_count,
        "next_action": client.next_action,
        "updated_at": client.updated_at.isoformat(),
        "version": client.version,
    }


def _detail(
    client: Client,
    *,
    fact_keys: set[str] | None = None,
) -> dict[str, object]:
    return {
        **_summary(client, fact_keys=fact_keys),
        "address": client.address,
        "contact_phone": client.contact_phone,
        "contact_wechat": client.contact_wechat,
        "business_hours": client.business_hours,
        "service_radius": client.service_radius,
        "cooperation_started_on": client.cooperation_started_on.isoformat(),
        "notes": client.notes,
        "created_at": client.created_at.isoformat(),
    }


async def _find_client(database: DatabaseSession, client_id: UUID) -> Client | None:
    return await database.get(Client, client_id)


async def _client_fact_keys(
    database: DatabaseSession,
    client_id: UUID,
) -> set[str]:
    return (await _fact_keys_by_client(database, [client_id])).get(client_id, set())


async def _atomic_client_update(
    database: DatabaseSession,
    client_id: UUID,
    version: int,
    values: dict[str, object],
    *,
    allowed_statuses: tuple[str, ...] | None = None,
) -> Client | None:
    statement = update(Client).where(Client.id == client_id, Client.version == version)
    if allowed_statuses is not None:
        statement = statement.where(Client.status.in_(allowed_statuses))
    result = await database.execute(
        statement.values(**values, version=Client.version + 1, updated_at=utc_now()).returning(
            Client
        ),
    )
    client = result.scalar_one_or_none()
    if client is not None:
        await database.commit()
    return client


def _is_client_name_conflict(error: IntegrityError) -> bool:
    original = error.orig
    sqlstate = getattr(original, "sqlstate", None)
    if sqlstate is None:
        sqlstate = getattr(getattr(original, "__cause__", None), "sqlstate", None)
    return sqlstate == "23505" or "clients.normalized_name" in str(original)


def build_clients_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/clients", tags=["clients"])

    @router.get("")
    async def list_clients(
        request: Request,
        database: DatabaseSession,
        authentication: Authenticated,
        q: Annotated[str | None, Query(max_length=200)] = None,
        status: ClientStatus | None = None,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
        sort: Literal["-updated_at", "standard_name"] = "-updated_at",
    ) -> Response:
        filters = []
        if q:
            pattern = f"%{q.strip()}%"
            filters.append(
                or_(
                    Client.standard_name.ilike(pattern),
                    Client.short_name.ilike(pattern),
                ),
            )
        if status:
            filters.append(Client.status == status)
        else:
            filters.append(Client.status != "archived")
        total = await database.scalar(select(func.count(Client.id)).where(*filters))
        ordering = desc(Client.updated_at) if sort == "-updated_at" else asc(Client.standard_name)
        rows = await database.scalars(
            select(Client)
            .where(*filters)
            .order_by(ordering)
            .offset((page - 1) * page_size)
            .limit(page_size),
        )
        clients = list(rows.all())
        fact_keys = await _fact_keys_by_client(
            database,
            [item.id for item in clients],
        )
        items = [_summary(item, fact_keys=fact_keys.get(item.id, set())) for item in clients]
        count = int(total or 0)
        return success_response(
            request,
            {
                "items": items,
                "total": count,
                "page": page,
                "page_size": page_size,
                "has_next": page * page_size < count,
            },
        )

    @router.post("")
    async def create_client(
        request: Request,
        body: ClientCreateInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        values = body.model_dump()
        client = Client(
            **values,
            normalized_name=normalize_client_name(body.standard_name),
            industry_name=INDUSTRY_NAMES.get(body.industry_code, body.industry_code),
        )
        database.add(client)
        try:
            await database.commit()
        except IntegrityError as error:
            await database.rollback()
            if not _is_client_name_conflict(error):
                raise
            return error_response(
                request,
                status_code=409,
                code=40903,
                message="客户标准名称已存在",
            )
        await database.refresh(client)
        return success_response(
            request,
            _detail(client, fact_keys=await _client_fact_keys(database, client.id)),
            status_code=201,
        )

    @router.get("/{client_id}")
    async def get_client(
        request: Request,
        client_id: UUID,
        database: DatabaseSession,
        authentication: Authenticated,
    ) -> Response:
        client = await _find_client(database, client_id)
        if client is None:
            return error_response(
                request,
                status_code=404,
                code=40401,
                message="客户不存在",
            )
        return success_response(
            request,
            _detail(client, fact_keys=await _client_fact_keys(database, client.id)),
        )

    @router.patch("/{client_id}")
    async def update_client(
        request: Request,
        client_id: UUID,
        body: ClientUpdateInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        values = body.model_dump(exclude={"version"}, exclude_unset=True)
        standard_name = values.get("standard_name")
        if isinstance(standard_name, str):
            values["normalized_name"] = normalize_client_name(standard_name)
        industry_code = values.get("industry_code")
        if isinstance(industry_code, str):
            values["industry_name"] = INDUSTRY_NAMES.get(industry_code, industry_code)
        try:
            client = await _atomic_client_update(
                database,
                client_id,
                body.version,
                values,
                allowed_statuses=("active", "paused"),
            )
        except IntegrityError as error:
            await database.rollback()
            if not _is_client_name_conflict(error):
                raise
            return error_response(
                request,
                status_code=409,
                code=40903,
                message="客户标准名称已存在",
            )
        if client is not None:
            return success_response(
                request,
                _detail(client, fact_keys=await _client_fact_keys(database, client.id)),
            )
        current = await _find_client(database, client_id)
        if current is None:
            return error_response(request, status_code=404, code=40401, message="客户不存在")
        if current.status == "archived" and current.version == body.version:
            return error_response(
                request,
                status_code=409,
                code=40902,
                message="已归档客户请先恢复",
            )
        return error_response(
            request,
            status_code=409,
            code=40901,
            message="客户资料已被更新，请刷新后重试",
        )

    @router.post("/{client_id}/archive")
    async def archive_client(
        request: Request,
        client_id: UUID,
        body: ArchiveInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        client = await database.scalar(
            select(Client).where(Client.id == client_id).with_for_update(),
        )
        if client is None:
            return error_response(request, status_code=404, code=40401, message="客户不存在")
        if client.version != body.version or client.status not in ("active", "paused"):
            return error_response(
                request,
                status_code=409,
                code=40901,
                message="客户状态已变化，请刷新后重试",
            )
        active_job = await database.scalar(
            select(Job.id).where(
                Job.client_id == client_id,
                Job.status.in_(("queued", "running")),
            ),
        )
        if active_job is not None:
            return error_response(
                request,
                status_code=409,
                code=40902,
                message="客户存在运行中任务，暂时不能归档",
            )
        client.status = "archived"
        client.archived_reason = body.reason
        client.version += 1
        client.updated_at = utc_now()
        await database.commit()
        return success_response(
            request,
            _detail(client, fact_keys=await _client_fact_keys(database, client.id)),
        )

    @router.post("/{client_id}/restore")
    async def restore_client(
        request: Request,
        client_id: UUID,
        body: VersionInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        client = await _atomic_client_update(
            database,
            client_id,
            body.version,
            {"status": "active", "archived_reason": None},
            allowed_statuses=("archived",),
        )
        if client is not None:
            return success_response(
                request,
                _detail(client, fact_keys=await _client_fact_keys(database, client.id)),
            )
        current = await _find_client(database, client_id)
        if current is None:
            return error_response(request, status_code=404, code=40401, message="客户不存在")
        return error_response(
            request,
            status_code=409,
            code=40901,
            message="客户状态已变化，请刷新后重试",
        )

    @router.get("/{client_id}/dashboard")
    async def get_dashboard(
        request: Request,
        client_id: UUID,
        database: DatabaseSession,
        authentication: Authenticated,
    ) -> Response:
        client = await _find_client(database, client_id)
        if client is None:
            return error_response(request, status_code=404, code=40401, message="客户不存在")
        next_level = {
            "L0": "L1",
            "L1": "L2",
            "L2": "L3",
            "L3": "L4",
            "L4": None,
        }.get(client.current_level)
        materials_count = int(
            await database.scalar(
                select(func.count(Material.id)).where(Material.client_id == client_id),
            )
            or 0
        )
        confirmed_facts_count = int(
            await database.scalar(
                select(func.count(Fact.id)).where(
                    Fact.client_id == client_id,
                    Fact.status == "confirmed",
                ),
            )
            or 0
        )
        unresolved_conflicts_count = int(
            await database.scalar(
                select(func.count(FactConflict.id)).where(
                    FactConflict.client_id == client_id,
                    FactConflict.status == "open",
                ),
            )
            or 0
        )
        recent_jobs = (
            await database.scalars(
                select(Job)
                .where(Job.client_id == client_id)
                .order_by(Job.created_at.desc())
                .limit(10),
            )
        ).all()
        return success_response(
            request,
            {
                "client": _summary(
                    client,
                    fact_keys=await _client_fact_keys(database, client.id),
                ),
                "counts": {
                    "materials": materials_count,
                    "confirmed_facts": confirmed_facts_count,
                    "unresolved_conflicts": unresolved_conflicts_count,
                    "planned_contents": 0,
                    "draft_contents": 0,
                    "monitoring_samples_30d": 0,
                },
                "level_progress": {
                    "current": client.current_level,
                    "next": next_level,
                    "missing_conditions": [client.next_action] if next_level else [],
                },
                "next_actions": (
                    [
                        {
                            "id": f"client-{client.id}-complete-profile",
                            "title": client.next_action,
                            "reason": "补全可公开、可追溯的企业事实后才能进入诊断和内容生成",
                            "target_level": next_level,
                            "target_page": "P02",
                            "priority": 1,
                        },
                    ]
                    if next_level
                    else []
                ),
                "recent_jobs": [
                    {
                        "id": str(job.id),
                        "client_id": str(job.client_id),
                        "type": job.job_type,
                        "status": job.status,
                        "progress": job.progress,
                        "current_step": (
                            "等待处理"
                            if job.status == "queued"
                            else "解析企业资料"
                            if job.status == "running"
                            else "已完成"
                            if job.status == "succeeded"
                            else "处理失败"
                        ),
                        "attempt": job.attempts,
                        "max_attempts": job.max_attempts,
                        "result_resource_type": "material" if job.material_id else None,
                        "result_resource_id": str(job.material_id) if job.material_id else None,
                        "error_code": None,
                        "error_message": job.error_message,
                        "retryable": job.status == "failed" and job.attempts < job.max_attempts,
                        "created_at": job.created_at.isoformat(),
                        "started_at": job.started_at.isoformat() if job.started_at else None,
                        "finished_at": (job.completed_at.isoformat() if job.completed_at else None),
                    }
                    for job in recent_jobs
                ],
            },
        )

    return router
