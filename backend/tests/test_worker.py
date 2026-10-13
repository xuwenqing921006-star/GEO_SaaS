from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.observability import RequestMetrics
from app.worker import probe_api_readiness, send_database_heartbeat


class RecordingConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, statement: Any) -> None:
        self.statements.append(str(statement))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_worker_heartbeat_uses_the_database_without_claiming_business_work() -> None:
    connection = RecordingConnection()

    await send_database_heartbeat(connection)

    assert connection.statements == ["SELECT 1"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_worker_probes_real_api_readiness_and_recovers() -> None:
    metrics = RequestMetrics()
    settings = Settings(
        app_env="test",
        db_password=SecretStr("unused"),
        api_readiness_url="http://api.test/api/v1/health/ready",
    )

    await probe_api_readiness(
        settings,
        metrics,
        httpx.MockTransport(lambda _: httpx.Response(503)),
    )
    unhealthy = metrics.snapshot()
    assert unhealthy.total == 1
    assert unhealthy.errors == 1
    assert unhealthy.readiness_unhealthy_seconds >= 0

    await probe_api_readiness(
        settings,
        metrics,
        httpx.MockTransport(lambda _: httpx.Response(200)),
    )
    recovered = metrics.snapshot()
    assert recovered.total == 2
    assert recovered.errors == 1
    assert recovered.readiness_unhealthy_seconds == 0

    def unavailable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("api unavailable", request=request)

    await probe_api_readiness(settings, metrics, httpx.MockTransport(unavailable))
    assert metrics.snapshot().errors == 2
