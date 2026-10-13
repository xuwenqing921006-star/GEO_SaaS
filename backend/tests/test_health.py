import os
import time
from pathlib import Path
from typing import Literal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.health import DependencyUnavailable, ReadinessSnapshot, worker_heartbeat_status
from app.main import create_app


class ReadyHealthService:
    async def readiness(self) -> ReadinessSnapshot:
        return ReadinessSnapshot(
            status="ready",
            database="ok",
            storage="ok",
            worker_heartbeat="ok",
        )


class UnavailableHealthService:
    def __init__(self, dependency: Literal["database", "storage"]) -> None:
        self._dependency = dependency

    async def readiness(self) -> ReadinessSnapshot:
        raise DependencyUnavailable(self._dependency)


class StaleWorkerHealthService:
    async def readiness(self) -> ReadinessSnapshot:
        return ReadinessSnapshot(
            status="ready",
            database="ok",
            storage="ok",
            worker_heartbeat="stale",
        )


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        app_version="test-version",
        db_password=SecretStr("unused"),
        storage_root=tmp_path,
    )


@pytest.mark.unit
def test_live_health_matches_api_contract(tmp_path: Path) -> None:
    app = create_app(settings=make_settings(tmp_path), health_service=ReadyHealthService())

    with TestClient(app) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json()["code"] == 200
    assert response.json()["message"] == "success"
    assert response.json()["data"] == {
        "status": "ok",
        "service": "geo-api",
        "version": "test-version",
    }
    assert UUID(response.json()["request_id"])
    assert response.headers["x-request-id"] == response.json()["request_id"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["permissions-policy"] == ("camera=(), microphone=(), geolocation=()")
    assert response.headers["cache-control"] == "no-store"
    assert "strict-transport-security" not in response.headers


@pytest.mark.unit
def test_production_api_adds_hsts(tmp_path: Path) -> None:
    settings = make_settings(tmp_path).model_copy(update={"app_env": "production"})
    app = create_app(settings=settings, health_service=ReadyHealthService())

    with TestClient(app, base_url="https://geo.example.test") as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.headers["strict-transport-security"] == ("max-age=31536000; includeSubDomains")


@pytest.mark.unit
def test_ready_health_matches_api_contract(tmp_path: Path) -> None:
    app = create_app(settings=make_settings(tmp_path), health_service=ReadyHealthService())

    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json()["code"] == 200
    assert response.json()["message"] == "success"
    assert response.json()["data"] == {
        "status": "ready",
        "database": "ok",
        "storage": "ok",
        "worker_heartbeat": "ok",
    }
    assert UUID(response.json()["request_id"])


@pytest.mark.unit
@pytest.mark.parametrize("dependency", ["database", "storage"])
def test_ready_returns_uniform_503_envelope_when_a_required_dependency_fails(
    tmp_path: Path,
    dependency: Literal["database", "storage"],
) -> None:
    app = create_app(
        settings=make_settings(tmp_path),
        health_service=UnavailableHealthService(dependency),
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["code"] == 50301
    assert response.json()["message"] == "数据库或文件存储不可用"
    assert response.json()["data"] == {
        "field_errors": [],
        "retryable": True,
        "provider": None,
        "job_id": None,
    }
    assert UUID(response.json()["request_id"])


@pytest.mark.unit
def test_ready_remains_available_when_worker_heartbeat_is_stale(tmp_path: Path) -> None:
    app = create_app(
        settings=make_settings(tmp_path),
        health_service=StaleWorkerHealthService(),
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "status": "ready",
        "database": "ok",
        "storage": "ok",
        "worker_heartbeat": "stale",
    }


@pytest.mark.unit
def test_worker_heartbeat_uses_real_file_age_to_report_stale(tmp_path: Path) -> None:
    heartbeat_path = tmp_path / "worker-heartbeat"
    heartbeat_path.write_text("ok", encoding="utf-8")
    expired_at = time.time() - 21
    os.utime(heartbeat_path, (expired_at, expired_at))

    status = worker_heartbeat_status(
        heartbeat_path,
        timeout_seconds=20,
        current_time=time.time(),
    )

    assert status == "stale"


@pytest.mark.unit
def test_unhandled_exception_returns_redacted_uniform_envelope(tmp_path: Path) -> None:
    app = create_app(settings=make_settings(tmp_path), health_service=ReadyHealthService())

    @app.get("/test/unhandled")
    async def unhandled() -> None:
        raise RuntimeError("Authorization: Bearer must-not-reach-response")

    with TestClient(app) as client:
        response = client.get("/test/unhandled")

    payload = response.json()
    assert response.status_code == 500
    assert payload["code"] == 50001
    assert payload["message"] == "系统内部错误"
    assert payload["data"] == {
        "field_errors": [],
        "retryable": False,
        "provider": None,
        "job_id": None,
    }
    assert "must-not-reach-response" not in response.text
    assert UUID(payload["request_id"])
    assert response.headers["x-request-id"] == payload["request_id"]
