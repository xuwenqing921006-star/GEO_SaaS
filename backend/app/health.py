import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings
from app.schemas import ApiEnvelope, ErrorData, LivenessData, ReadinessData

READINESS_ERROR_CODE = 50301
READINESS_ERROR_MESSAGE = "数据库或文件存储不可用"


class DependencyUnavailable(RuntimeError):
    def __init__(self, dependency: Literal["database", "storage"]) -> None:
        super().__init__(dependency)
        self.dependency = dependency


@dataclass(frozen=True)
class ReadinessSnapshot:
    status: Literal["ready"]
    database: Literal["ok"]
    storage: Literal["ok"]
    worker_heartbeat: Literal["ok", "stale"]


class HealthServiceProtocol(Protocol):
    async def readiness(self) -> ReadinessSnapshot: ...


class HealthService:
    def __init__(self, engine: AsyncEngine, settings: Settings) -> None:
        self._engine = engine
        self._settings = settings

    async def readiness(self) -> ReadinessSnapshot:
        await self._check_database()
        await asyncio.to_thread(self._check_storage)
        worker_heartbeat = await asyncio.to_thread(
            worker_heartbeat_status,
            self._settings.worker_heartbeat_path,
            self._settings.worker_heartbeat_timeout_seconds,
        )
        return ReadinessSnapshot(
            status="ready",
            database="ok",
            storage="ok",
            worker_heartbeat=worker_heartbeat,
        )

    async def _check_database(self) -> None:
        try:
            async with self._engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception as error:
            raise DependencyUnavailable("database") from error

    def _check_storage(self) -> None:
        probe_path = self._settings.storage_root / ".readiness-probe"
        try:
            self._settings.storage_root.mkdir(parents=True, exist_ok=True)
            probe_path.write_text("ok", encoding="utf-8")
            probe_path.unlink()
        except OSError as error:
            raise DependencyUnavailable("storage") from error


def worker_heartbeat_status(
    heartbeat_path: Path,
    timeout_seconds: float,
    *,
    current_time: float | None = None,
) -> Literal["ok", "stale"]:
    try:
        modified_at = heartbeat_path.stat().st_mtime
    except OSError:
        return "stale"
    heartbeat_age = (current_time if current_time is not None else time.time()) - modified_at
    return "ok" if heartbeat_age <= timeout_seconds else "stale"


def _request_id(request: Request) -> UUID:
    return cast(UUID, request.state.request_id)


def build_health_router(
    settings: Settings,
    health_service: HealthServiceProtocol,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/health", tags=["health"])

    @router.get("/live", response_model=ApiEnvelope[LivenessData])
    async def live(request: Request) -> ApiEnvelope[LivenessData]:
        return ApiEnvelope(
            code=200,
            message="success",
            data=LivenessData(
                service=settings.app_name,
                version=settings.app_version,
            ),
            request_id=_request_id(request),
        )

    @router.get(
        "/ready",
        response_model=ApiEnvelope[ReadinessData],
        responses={503: {"model": ApiEnvelope[ErrorData]}},
    )
    async def ready(request: Request) -> ApiEnvelope[ReadinessData] | JSONResponse:
        try:
            snapshot = await health_service.readiness()
        except DependencyUnavailable:
            envelope = ApiEnvelope[ErrorData](
                code=READINESS_ERROR_CODE,
                message=READINESS_ERROR_MESSAGE,
                data=ErrorData(retryable=True),
                request_id=_request_id(request),
            )
            return JSONResponse(status_code=503, content=envelope.model_dump(mode="json"))

        return ApiEnvelope(
            code=200,
            message="success",
            data=ReadinessData(
                status=snapshot.status,
                database=snapshot.database,
                storage=snapshot.storage,
                worker_heartbeat=snapshot.worker_heartbeat,
            ),
            request_id=_request_id(request),
        )

    return router
