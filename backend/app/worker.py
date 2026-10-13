import asyncio
import logging
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.config import Settings
from app.jobs import process_one_job
from app.logging import configure_json_logging
from app.observability import (
    RequestMetrics,
    collect_operational_snapshot,
    evaluate_operational_alerts,
)
from app.publishing import (
    PUBLISHING_SESSION_SWEEP_INTERVAL_SECONDS,
    check_due_publishing_accounts,
    check_pending_publications,
)

LOGGER = logging.getLogger("geo-saas.worker")


class DatabaseConnection(Protocol):
    async def execute(self, statement: Any) -> Any: ...


async def send_database_heartbeat(connection: DatabaseConnection) -> None:
    await connection.execute(text("SELECT 1"))


def write_heartbeat_file(heartbeat_path: Path) -> None:
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = heartbeat_path.with_suffix(".tmp")
    temporary_path.write_text("ok", encoding="utf-8")
    temporary_path.replace(heartbeat_path)


async def probe_api_readiness(
    settings: Settings,
    request_metrics: RequestMetrics,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    started = perf_counter()
    status_code = 503
    try:
        async with httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(2),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.get(settings.api_readiness_url)
            status_code = response.status_code
    except httpx.HTTPError:
        pass
    request_metrics.observe(
        path="/api/v1/health/ready",
        status_code=status_code,
        duration_seconds=perf_counter() - started,
    )


async def run_worker(settings: Settings, engine: AsyncEngine) -> None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    active_alerts: set[str] = set()
    request_metrics = RequestMetrics()
    next_publishing_session_sweep_at = 0.0
    while True:
        try:
            async with engine.connect() as connection:
                await send_database_heartbeat(connection)
            await asyncio.to_thread(write_heartbeat_file, settings.worker_heartbeat_path)
            processed_jobs = 0
            while processed_jobs < 10 and await process_one_job(session_factory, settings):
                processed_jobs += 1
            checked_publishing_sessions = 0
            checked_pending_publications = 0
            sweep_started_at = perf_counter()
            if sweep_started_at >= next_publishing_session_sweep_at:
                next_publishing_session_sweep_at = (
                    sweep_started_at + PUBLISHING_SESSION_SWEEP_INTERVAL_SECONDS
                )
                checked_publishing_sessions = await check_due_publishing_accounts(
                    session_factory,
                    settings,
                )
                checked_pending_publications = await check_pending_publications(
                    session_factory,
                    settings,
                )
            await probe_api_readiness(settings, request_metrics)
            async with session_factory() as database:
                operational_snapshot = await collect_operational_snapshot(
                    database,
                    settings,
                    request_metrics,
                )
            current_alerts = {
                alert.code: alert for alert in evaluate_operational_alerts(operational_snapshot)
            }
            for alert_code in current_alerts.keys() - active_alerts:
                alert = current_alerts[alert_code]
                LOGGER.warning(
                    "operational_alert",
                    extra={
                        "event": "operational_alert",
                        "alert_code": alert.code,
                        "value": round(alert.value, 4),
                        "threshold": alert.threshold,
                    },
                )
            for alert_code in active_alerts - current_alerts.keys():
                LOGGER.info(
                    "operational_alert_resolved",
                    extra={
                        "event": "operational_alert_resolved",
                        "alert_code": alert_code,
                    },
                )
            active_alerts = set(current_alerts)
            LOGGER.info(
                "worker_heartbeat",
                extra={
                    "event": "worker_heartbeat",
                    "dependency": "database",
                    "processed_jobs": processed_jobs,
                    "checked_publishing_sessions": checked_publishing_sessions,
                    "checked_pending_publications": checked_pending_publications,
                },
            )
        except Exception:
            LOGGER.error(
                "worker_heartbeat_failed",
                extra={"event": "worker_heartbeat_failed", "dependency": "database"},
            )
        await asyncio.sleep(settings.worker_heartbeat_interval_seconds)


async def async_main(settings: Settings) -> None:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        await run_worker(settings, engine)
    finally:
        await engine.dispose()


def main() -> None:
    settings = Settings()
    configure_json_logging(settings.app_env)
    asyncio.run(async_main(settings))


if __name__ == "__main__":
    main()
