import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.observability as observability
from app.config import Settings
from app.database import Base, Client, Job, ModelUsage, ProviderSetting
from app.observability import (
    OperationalSnapshot,
    RequestMetrics,
    RequestSnapshot,
    collect_operational_snapshot,
    evaluate_operational_alerts,
    render_prometheus,
)


def request_snapshot(*, readiness_unhealthy_seconds: float = 0) -> RequestSnapshot:
    return RequestSnapshot(
        total=10,
        errors=1,
        duration_seconds=2.5,
        readiness_unhealthy_seconds=readiness_unhealthy_seconds,
    )


@pytest.mark.unit
def test_alert_thresholds_and_prometheus_metrics_cover_release_requirements() -> None:
    snapshot = OperationalSnapshot(
        requests=request_snapshot(readiness_unhealthy_seconds=301),
        queue_depth=4,
        oldest_job_seconds=1201,
        provider_calls=10,
        provider_successes=8,
        provider_fallbacks=2,
        provider_tokens=12_000,
        provider_cost_cny_fen=8_000,
        provider_budget_cny_fen=10_000,
        storage_bytes=800,
        storage_capacity_bytes=1_000,
        backup_success=False,
        backup_age_seconds=60,
    )

    assert {alert.code for alert in evaluate_operational_alerts(snapshot)} == {
        "readiness_failed_5m",
        "oldest_job_over_20m",
        "provider_budget_80pct",
        "storage_80pct",
        "backup_failed",
    }
    metrics = render_prometheus(snapshot)
    for metric in (
        "geo_http_request_errors_total 1",
        "geo_jobs_queue_depth 4",
        "geo_provider_success_ratio 0.8",
        "geo_provider_fallback_total 2",
        "geo_provider_tokens_total 12000",
        "geo_provider_budget_ratio 0.8",
        "geo_storage_ratio 0.8",
        "geo_backup_success 0",
    ):
        assert metric in metrics


@pytest.mark.integration
@pytest.mark.asyncio
async def test_operational_collection_uses_live_database_storage_and_backup_state(
    tmp_path: Path,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'metrics.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    client_id = uuid4()
    now = datetime.now(UTC)
    backup_path = tmp_path / "backups" / "backup-status.json"
    backup_path.parent.mkdir()
    backup_path.write_text(
        json.dumps(
            {
                "success": True,
                "completed_at": now.isoformat(),
                "app_version": "test",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "business-file.txt").write_text("measured", encoding="utf-8")

    async with factory() as database:
        database.add(
            Client(
                id=client_id,
                standard_name="监测示例企业",
                normalized_name="监测示例企业",
                industry_code="LOCAL_SERVICE",
                industry_name="本地服务",
                province="山东省",
                city="青岛市",
                district="即墨区",
                address="测试地址",
                cooperation_started_on=date.today(),
            )
        )
        database.add(
            Job(
                client_id=client_id,
                job_type="diagnostic_generate",
                idempotency_key=str(uuid4()),
                created_at=now - timedelta(minutes=21),
            )
        )
        database.add(
            ProviderSetting(
                provider="deepseek",
                enabled=True,
                base_url="https://api.deepseek.com",
                daily_budget_cny_fen=1_000,
            )
        )
        database.add(
            ModelUsage(
                client_id=client_id,
                provider="deepseek",
                model="test-model",
                purpose="content_draft",
                usage_date=date.today(),
                input_tokens=100,
                output_tokens=50,
                cost_cny_fen=850,
                status="succeeded",
                fallback_reason="primary_timeout",
            )
        )
        await database.commit()

        request_metrics = RequestMetrics()
        request_metrics.observe(
            path="/api/v1/clients",
            status_code=500,
            duration_seconds=0.25,
        )
        snapshot = await collect_operational_snapshot(
            database,
            Settings(
                app_env="test",
                db_password=SecretStr("unused"),
                storage_root=tmp_path,
                backup_status_path=backup_path,
            ),
            request_metrics,
        )

    await engine.dispose()

    assert snapshot.queue_depth == 1
    assert snapshot.oldest_job_seconds >= 1200
    assert snapshot.provider_successes == 1
    assert snapshot.provider_fallbacks == 1
    assert snapshot.provider_tokens == 150
    assert snapshot.budget_ratio == 0.85
    assert snapshot.requests.errors == 1
    assert snapshot.storage_bytes > 0
    assert snapshot.backup_success is True
    assert snapshot.backup_age_seconds is not None


@pytest.mark.unit
def test_metrics_recovery_missing_inputs_and_stale_backup_paths(tmp_path: Path) -> None:
    metrics = RequestMetrics()
    metrics.observe(
        path="/api/v1/health/ready",
        status_code=503,
        duration_seconds=-1,
    )
    metrics._readiness_unhealthy_since = datetime.now(UTC) - timedelta(seconds=301)
    assert metrics.snapshot().readiness_unhealthy_seconds >= 300

    metrics.observe(
        path="/api/v1/health/ready",
        status_code=503,
        duration_seconds=0,
    )
    metrics.observe(
        path="/api/v1/health/ready",
        status_code=200,
        duration_seconds=0,
    )
    assert metrics.snapshot().readiness_unhealthy_seconds == 0

    empty = OperationalSnapshot(
        requests=request_snapshot(),
        queue_depth=0,
        oldest_job_seconds=0,
        provider_calls=0,
        provider_successes=0,
        provider_fallbacks=0,
        provider_tokens=0,
        provider_cost_cny_fen=100,
        provider_budget_cny_fen=0,
        storage_bytes=100,
        storage_capacity_bytes=0,
        backup_success=None,
        backup_age_seconds=None,
    )
    assert empty.provider_success_ratio == 1
    assert empty.budget_ratio == 0
    assert empty.storage_ratio == 0
    assert "geo_backup_success -1" in render_prometheus(empty)
    assert observability._directory_bytes(tmp_path / "missing") == 0
    assert observability._backup_status(tmp_path / "missing.json") == (None, None)

    invalid_status = tmp_path / "invalid-backup.json"
    invalid_status.write_text("not-json", encoding="utf-8")
    assert observability._backup_status(invalid_status) == (None, None)

    stale = OperationalSnapshot(
        **{
            **empty.__dict__,
            "backup_success": True,
            "backup_age_seconds": 93_600,
        }
    )
    assert {alert.code for alert in evaluate_operational_alerts(stale)} == {"backup_stale_26h"}
