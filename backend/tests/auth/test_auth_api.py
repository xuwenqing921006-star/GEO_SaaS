import asyncio
import base64
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from typing import Literal, cast

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database import Base, Owner, OwnerSession
from app.health import ReadinessSnapshot
from app.main import create_app
from app.security import hash_password, secret_digest


class ReadyHealthService:
    async def readiness(self) -> ReadinessSnapshot:
        return ReadinessSnapshot(
            status="ready",
            database="ok",
            storage="ok",
            worker_heartbeat="ok",
        )


def build_client(
    tmp_path: Path,
    *,
    app_env: Literal["test", "production"] = "test",
    base_url: str = "http://testserver",
    app_master_key: SecretStr | None = None,
    provider_transport: httpx.AsyncBaseTransport | None = None,
    model_execution_mode: Literal["live", "fixed_mock"] = "live",
    publishing_execution_mode: Literal["live_browser", "fixed_mock"] = "live_browser",
) -> TestClient:
    database_path = tmp_path / "auth.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")

    async def prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            session.add(
                Owner(
                    username="owner",
                    display_name="平台负责人",
                    password_hash=hash_password("CorrectPassword2026!"),
                ),
            )
            await session.commit()

    asyncio.run(prepare())
    settings = Settings(
        app_env=app_env,
        db_password=SecretStr(
            "production-test-password-2026!" if app_env == "production" else "unused",
        ),
        storage_root=tmp_path,
        app_master_key=(
            app_master_key
            or (
                SecretStr(base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"))
                if app_env == "production"
                else None
            )
        ),
        model_execution_mode=model_execution_mode,
        publishing_execution_mode=publishing_execution_mode,
    )
    return TestClient(
        create_app(
            settings=settings,
            health_service=ReadyHealthService(),
            engine_override=engine,
            provider_transport=provider_transport,
        ),
        base_url=base_url,
    )


@pytest.mark.integration
def test_login_session_logout_and_csrf_are_enforced(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "owner", "password": "CorrectPassword2026!"},
        )
        assert login.status_code == 200
        assert login.cookies.get("geo_session")
        set_cookie = login.headers.get_list("set-cookie")
        session_cookie = next(value for value in set_cookie if value.startswith("geo_session="))
        assert "HttpOnly" in session_cookie
        assert "SameSite=lax" in session_cookie
        csrf_token = login.json()["data"]["csrf_token"]

        session = client.get("/api/v1/auth/session")
        assert session.status_code == 200
        assert session.json()["data"]["user"]["username"] == "owner"
        assert session.json()["data"]["csrf_token"] == csrf_token
        csrf_token = session.json()["data"]["csrf_token"]

        rejected = client.delete("/api/v1/auth/session")
        assert rejected.status_code == 403
        assert rejected.json()["code"] == 40301

        logout = client.delete(
            "/api/v1/auth/session",
            headers={"X-CSRF-Token": csrf_token},
        )
        assert logout.status_code == 200
        assert logout.json()["data"] == {"logged_out": True}
        assert client.get("/api/v1/auth/session").status_code == 401


@pytest.mark.unit
def test_login_is_generic_and_rate_limited(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        for _ in range(5):
            response = client.post(
                "/api/v1/auth/login",
                json={"username": "owner", "password": "WrongPassword2026!"},
            )
            assert response.status_code == 401
            assert response.json()["message"] == "用户名或密码错误"

        limited = client.post(
            "/api/v1/auth/login",
            json={"username": "owner", "password": "WrongPassword2026!"},
        )
        assert limited.status_code == 429


@pytest.mark.unit
def test_concurrent_login_attempts_reserve_rate_limit_before_password_hash(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        barrier = Barrier(12)

        def attempt() -> int:
            barrier.wait()
            return int(
                client.post(
                    "/api/v1/auth/login",
                    json={"username": "owner", "password": "WrongPassword2026!"},
                ).status_code,
            )

        with ThreadPoolExecutor(max_workers=12) as executor:
            statuses = list(executor.map(lambda _: attempt(), range(12)))

        assert statuses.count(401) == 5
        assert statuses.count(429) == 7


@pytest.mark.unit
def test_production_session_cookie_is_secure(tmp_path: Path) -> None:
    with build_client(
        tmp_path,
        app_env="production",
        base_url="https://testserver",
    ) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "owner", "password": "CorrectPassword2026!"},
        )
        session_cookie = next(
            value
            for value in login.headers.get_list("set-cookie")
            if value.startswith("geo_session=")
        )
        assert "Secure" in session_cookie
        assert "HttpOnly" in session_cookie


@pytest.mark.integration
def test_idle_expired_session_is_revoked(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "owner", "password": "CorrectPassword2026!"},
        )
        assert login.status_code == 200

        async def expire() -> None:
            factory = cast(FastAPI, client.app).state.session_factory
            async with factory() as session:
                owner_session = await session.get(
                    OwnerSession,
                    secret_digest(login.cookies["geo_session"]),
                )
                assert owner_session is not None
                owner_session.idle_expires_at = datetime.now(UTC) - timedelta(seconds=1)
                await session.commit()

        asyncio.run(expire())
        expired = client.get("/api/v1/auth/session")
        assert expired.status_code == 401
        assert expired.json()["code"] == 40101


@pytest.mark.integration
def test_password_change_revokes_every_session_and_no_signup_route_exists(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "owner", "password": "CorrectPassword2026!"},
        )
        csrf_token = login.json()["data"]["csrf_token"]
        invalid = client.put(
            "/api/v1/auth/password",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "current_password": "CorrectPassword2026!",
                "new_password": "short",
            },
        )
        assert invalid.status_code == 422
        assert invalid.json()["message"] == "新密码不符合安全要求"
        changed = client.put(
            "/api/v1/auth/password",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "current_password": "CorrectPassword2026!",
                "new_password": "NewCorrectPassword2026!",
            },
        )
        assert changed.status_code == 200
        assert changed.json()["data"]["relogin_required"] is True
        assert client.get("/api/v1/auth/session").status_code == 401
        assert client.post("/api/v1/auth/register", json={}).status_code == 404


@pytest.mark.integration
def test_session_generation_rejects_login_committed_with_old_password_version(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "owner", "password": "CorrectPassword2026!"},
        )
        csrf_token = login.json()["data"]["csrf_token"]
        changed = client.put(
            "/api/v1/auth/password",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "current_password": "CorrectPassword2026!",
                "new_password": "NewCorrectPassword2026!",
            },
        )
        assert changed.status_code == 200

        stale_token = "stale-login-token"

        async def insert_stale_session() -> None:
            factory = cast(FastAPI, client.app).state.session_factory
            async with factory() as session:
                owner = await session.scalar(select(Owner))
                assert owner is not None
                now = datetime.now(UTC)
                session.add(
                    OwnerSession(
                        token_hash=secret_digest(stale_token),
                        owner_id=owner.id,
                        csrf_hash=secret_digest("stale-csrf"),
                        session_version=owner.session_version - 1,
                        created_at=now,
                        last_seen_at=now,
                        idle_expires_at=now + timedelta(hours=1),
                        absolute_expires_at=now + timedelta(days=1),
                    ),
                )
                await session.commit()

        asyncio.run(insert_stale_session())
        client.cookies.set("geo_session", stale_token)
        assert client.get("/api/v1/auth/session").status_code == 401


@pytest.mark.integration
def test_database_enforces_single_owner_even_with_another_username(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:

        async def insert_second_owner() -> None:
            factory = cast(FastAPI, client.app).state.session_factory
            async with factory() as session:
                session.add(
                    Owner(
                        username="another-owner",
                        display_name="另一个负责人",
                        password_hash=hash_password("AnotherPassword2026!"),
                    ),
                )
                with pytest.raises(IntegrityError):
                    await session.commit()

        asyncio.run(insert_second_owner())
