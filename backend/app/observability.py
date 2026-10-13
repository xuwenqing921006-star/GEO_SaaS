import json
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import Job, ModelUsage, ProviderSetting


@dataclass(frozen=True)
class RequestSnapshot:
    total: int
    errors: int
    duration_seconds: float
    readiness_unhealthy_seconds: float


class RequestMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._total = 0
        self._errors = 0
        self._duration_seconds = 0.0
        self._readiness_unhealthy_since: datetime | None = None

    def observe(
        self,
        *,
        path: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        now = datetime.now(UTC)
        with self._lock:
            self._total += 1
            self._errors += int(status_code >= 500)
            self._duration_seconds += max(0.0, duration_seconds)
            if path == "/api/v1/health/ready":
                if status_code >= 500 and self._readiness_unhealthy_since is None:
                    self._readiness_unhealthy_since = now
                elif status_code < 500:
                    self._readiness_unhealthy_since = None

    def snapshot(self) -> RequestSnapshot:
        now = datetime.now(UTC)
        with self._lock:
            unhealthy_seconds = (
                0.0
                if self._readiness_unhealthy_since is None
                else max(0.0, (now - self._readiness_unhealthy_since).total_seconds())
            )
            return RequestSnapshot(
                total=self._total,
                errors=self._errors,
                duration_seconds=self._duration_seconds,
                readiness_unhealthy_seconds=unhealthy_seconds,
            )


@dataclass(frozen=True)
class OperationalSnapshot:
    requests: RequestSnapshot
    queue_depth: int
    oldest_job_seconds: float
    provider_calls: int
    provider_successes: int
    provider_fallbacks: int
    provider_tokens: int
    provider_cost_cny_fen: int
    provider_budget_cny_fen: int
    storage_bytes: int
    storage_capacity_bytes: int
    backup_success: bool | None
    backup_age_seconds: float | None

    @property
    def provider_success_ratio(self) -> float:
        return self.provider_successes / self.provider_calls if self.provider_calls else 1.0

    @property
    def budget_ratio(self) -> float:
        return (
            self.provider_cost_cny_fen / self.provider_budget_cny_fen
            if self.provider_budget_cny_fen > 0
            else 0.0
        )

    @property
    def storage_ratio(self) -> float:
        return (
            self.storage_bytes / self.storage_capacity_bytes
            if self.storage_capacity_bytes > 0
            else 0.0
        )


@dataclass(frozen=True)
class OperationalAlert:
    code: str
    value: float
    threshold: float


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _directory_bytes(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(
        path.stat().st_size for path in root.rglob("*") if path.is_file() and not path.is_symlink()
    )


def _backup_status(path: Path) -> tuple[bool | None, float | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        completed_at = datetime.fromisoformat(payload["completed_at"].replace("Z", "+00:00"))
        return bool(payload["success"]), max(
            0.0,
            (datetime.now(UTC) - _aware(completed_at)).total_seconds(),
        )
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None, None


async def collect_operational_snapshot(
    database: AsyncSession,
    settings: Settings,
    request_metrics: RequestMetrics,
) -> OperationalSnapshot:
    queue_depth, oldest_job = (
        await database.execute(
            select(func.count(Job.id), func.min(Job.created_at)).where(
                Job.status.in_(("queued", "running")),
            ),
        )
    ).one()
    usage = (
        await database.execute(
            select(
                func.count(ModelUsage.id),
                func.coalesce(
                    func.sum(case((ModelUsage.status == "succeeded", 1), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(case((ModelUsage.fallback_reason.is_not(None), 1), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(ModelUsage.input_tokens + ModelUsage.output_tokens),
                    0,
                ),
                func.coalesce(func.sum(ModelUsage.cost_cny_fen), 0),
            ).where(
                ModelUsage.usage_date == date.today(),
                ModelUsage.status.in_(("succeeded", "failed")),
            ),
        )
    ).one()
    provider_budget = await database.scalar(
        select(func.coalesce(func.sum(ProviderSetting.daily_budget_cny_fen), 0)).where(
            ProviderSetting.enabled.is_(True),
        ),
    )
    now = datetime.now(UTC)
    oldest_job_seconds = (
        0.0 if oldest_job is None else max(0.0, (now - _aware(oldest_job)).total_seconds())
    )
    storage_bytes = await __import__("asyncio").to_thread(
        _directory_bytes,
        settings.storage_root,
    )
    disk = shutil.disk_usage(settings.storage_root)
    backup_success, backup_age_seconds = _backup_status(settings.backup_status_path)
    return OperationalSnapshot(
        requests=request_metrics.snapshot(),
        queue_depth=int(queue_depth or 0),
        oldest_job_seconds=oldest_job_seconds,
        provider_calls=int(usage[0] or 0),
        provider_successes=int(usage[1] or 0),
        provider_fallbacks=int(usage[2] or 0),
        provider_tokens=int(usage[3] or 0),
        provider_cost_cny_fen=int(usage[4] or 0),
        provider_budget_cny_fen=int(provider_budget or 0),
        storage_bytes=storage_bytes,
        storage_capacity_bytes=disk.total,
        backup_success=backup_success,
        backup_age_seconds=backup_age_seconds,
    )


def evaluate_operational_alerts(snapshot: OperationalSnapshot) -> list[OperationalAlert]:
    alerts: list[OperationalAlert] = []
    if snapshot.requests.readiness_unhealthy_seconds >= 300:
        alerts.append(
            OperationalAlert(
                "readiness_failed_5m",
                snapshot.requests.readiness_unhealthy_seconds,
                300,
            )
        )
    if snapshot.oldest_job_seconds >= 1200:
        alerts.append(OperationalAlert("oldest_job_over_20m", snapshot.oldest_job_seconds, 1200))
    if snapshot.budget_ratio >= 0.8:
        alerts.append(OperationalAlert("provider_budget_80pct", snapshot.budget_ratio, 0.8))
    if snapshot.storage_ratio >= 0.8:
        alerts.append(OperationalAlert("storage_80pct", snapshot.storage_ratio, 0.8))
    if snapshot.backup_success is False:
        alerts.append(OperationalAlert("backup_failed", 1, 1))
    if (
        snapshot.backup_success is True
        and snapshot.backup_age_seconds is not None
        and snapshot.backup_age_seconds >= 93600
    ):
        alerts.append(OperationalAlert("backup_stale_26h", snapshot.backup_age_seconds, 93600))
    return alerts


def render_prometheus(snapshot: OperationalSnapshot) -> str:
    backup_success = -1 if snapshot.backup_success is None else int(snapshot.backup_success)
    values = {
        "geo_http_requests_total": snapshot.requests.total,
        "geo_http_request_errors_total": snapshot.requests.errors,
        "geo_http_request_duration_seconds_total": snapshot.requests.duration_seconds,
        "geo_readiness_unhealthy_seconds": snapshot.requests.readiness_unhealthy_seconds,
        "geo_jobs_queue_depth": snapshot.queue_depth,
        "geo_jobs_oldest_seconds": snapshot.oldest_job_seconds,
        "geo_provider_calls_total": snapshot.provider_calls,
        "geo_provider_success_total": snapshot.provider_successes,
        "geo_provider_success_ratio": snapshot.provider_success_ratio,
        "geo_provider_fallback_total": snapshot.provider_fallbacks,
        "geo_provider_tokens_total": snapshot.provider_tokens,
        "geo_provider_cost_cny_fen": snapshot.provider_cost_cny_fen,
        "geo_provider_budget_ratio": snapshot.budget_ratio,
        "geo_storage_bytes": snapshot.storage_bytes,
        "geo_storage_capacity_bytes": snapshot.storage_capacity_bytes,
        "geo_storage_ratio": snapshot.storage_ratio,
        "geo_backup_success": backup_success,
        "geo_backup_age_seconds": snapshot.backup_age_seconds or 0,
    }
    return "".join(f"{name} {value}\n" for name, value in values.items())


def build_observability_router(
    settings: Settings,
    request_metrics: RequestMetrics,
) -> APIRouter:
    router = APIRouter(prefix="/internal", include_in_schema=False)

    @router.get("/metrics", response_class=PlainTextResponse)
    async def metrics(request: Request) -> PlainTextResponse:
        async with request.app.state.session_factory() as database:
            snapshot = await collect_operational_snapshot(
                database,
                settings,
                request_metrics,
            )
        return PlainTextResponse(
            render_prometheus(snapshot),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    return router
