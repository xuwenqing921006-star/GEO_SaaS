import asyncio
import os
from datetime import date
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database import Client, MonitoringBatch, MonitoringQuestionSet, Owner
from app.health import ReadinessSnapshot
from app.main import create_app
from app.security import hash_password


class ReadyHealthService:
    async def readiness(self) -> ReadinessSnapshot:
        return ReadinessSnapshot(
            status="ready",
            database="ok",
            storage="ok",
            worker_heartbeat="ok",
        )


@pytest.mark.performance
def test_monitoring_metrics_meet_100k_sample_target(tmp_path: Path) -> None:
    database_url = os.getenv("TEST_POSTGRES_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_POSTGRES_DATABASE_URL is required for the capacity test")
    seed_engine = create_async_engine(database_url)
    client_id = uuid4()
    question_set_id = uuid4()
    batch_id = uuid4()
    created_owner_id = None
    original_owner: tuple[str, str, str, int] | None = None

    async def seed() -> None:
        nonlocal created_owner_id, original_owner
        session_factory = async_sessionmaker(seed_engine, expire_on_commit=False)
        async with session_factory() as database:
            owner = await database.scalar(select(Owner).where(Owner.singleton_key == 1))
            password_hash = hash_password("CapacityPassword2026!")
            if owner is None:
                owner = Owner(
                    username="capacity-owner",
                    display_name="容量测试负责人",
                    password_hash=password_hash,
                )
                database.add(owner)
                created_owner_id = owner.id
            else:
                original_owner = (
                    owner.username,
                    owner.display_name,
                    owner.password_hash,
                    owner.session_version,
                )
                owner.username = "capacity-owner"
                owner.display_name = "容量测试负责人"
                owner.password_hash = password_hash
            database.add(
                Client(
                    id=client_id,
                    standard_name="容量测试客户",
                    normalized_name=f"capacity-{client_id}",
                    industry_code="repair",
                    industry_name="维修服务",
                    province="山东省",
                    city="青岛市",
                    district="即墨区",
                    address="容量测试地址",
                    cooperation_started_on=date(2026, 7, 28),
                ),
            )
            database.add(
                MonitoringQuestionSet(
                    id=question_set_id,
                    client_id=client_id,
                    name="容量测试问题集",
                    frozen=True,
                    questions=[],
                ),
            )
            await database.flush()
            database.add(
                MonitoringBatch(
                    id=batch_id,
                    client_id=client_id,
                    question_set_id=question_set_id,
                    question_set_version=1,
                    question_snapshot=[],
                    platform_ids=["deepseek"],
                    api_sample_count=1,
                    status="succeeded",
                ),
            )
            await database.commit()
        async with seed_engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO monitoring_samples (
                        id, batch_id, client_id, platform_id, platform_name,
                        collection_mode, question_id, question_text,
                        question_family, is_brand_query, question_priority,
                        attempt, status, raw_answer, asked_at, created_at, updated_at
                    )
                    SELECT
                        gen_random_uuid(), :batch_id, :client_id, 'deepseek',
                        'DeepSeek', 'api', 'capacity-' || item,
                        '即墨维修服务怎么选?', 'category_discovery', false, 1,
                        1, 'succeeded', '容量测试回答', now(), now(), now()
                    FROM generate_series(1, 100000) AS item
                    """,
                ),
                {"batch_id": batch_id, "client_id": client_id},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO monitoring_evaluations (
                        id, sample_id, client_id, brand_found,
                        correctly_associated, recommended,
                        recommendation_supported, facts_accurate,
                        source_visible, reasons, incorrect_facts,
                        visible_sources, evaluator, version, created_at, updated_at
                    )
                    SELECT
                        gen_random_uuid(), id, :client_id,
                        true, true, false, NULL, true, false,
                        '[]'::json, '[]'::json, '[]'::json,
                        'user', 1, now(), now()
                    FROM monitoring_samples
                    WHERE batch_id = :batch_id
                    """,
                ),
                {"batch_id": batch_id, "client_id": client_id},
            )
        await seed_engine.dispose()

    async def cleanup() -> None:
        cleanup_engine = create_async_engine(database_url)
        async with cleanup_engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM monitoring_evaluations WHERE client_id = :client_id"),
                {"client_id": client_id},
            )
            await connection.execute(
                text("DELETE FROM monitoring_samples WHERE client_id = :client_id"),
                {"client_id": client_id},
            )
            await connection.execute(
                text("DELETE FROM monitoring_batches WHERE client_id = :client_id"),
                {"client_id": client_id},
            )
            await connection.execute(
                text("DELETE FROM monitoring_question_sets WHERE client_id = :client_id"),
                {"client_id": client_id},
            )
            await connection.execute(
                text("DELETE FROM clients WHERE id = :client_id"),
                {"client_id": client_id},
            )
            if created_owner_id is not None:
                await connection.execute(
                    text("DELETE FROM owners WHERE id = :owner_id"),
                    {"owner_id": created_owner_id},
                )
            elif original_owner is not None:
                await connection.execute(
                    text(
                        """
                        UPDATE owners
                        SET username = :username,
                            display_name = :display_name,
                            password_hash = :password_hash,
                            session_version = :session_version
                        WHERE singleton_key = 1
                        """,
                    ),
                    {
                        "username": original_owner[0],
                        "display_name": original_owner[1],
                        "password_hash": original_owner[2],
                        "session_version": original_owner[3],
                    },
                )
        await cleanup_engine.dispose()

    asyncio.run(seed())
    runtime_engine = create_async_engine(database_url)
    app = create_app(
        settings=Settings(
            app_env="test",
            db_password=SecretStr("unused"),
            storage_root=tmp_path,
        ),
        health_service=ReadyHealthService(),
        engine_override=runtime_engine,
    )
    try:
        with TestClient(app) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"username": "capacity-owner", "password": "CapacityPassword2026!"},
            )
            assert login.status_code == 200
            started = perf_counter()
            response = client.get(
                f"/api/v1/clients/{client_id}/monitoring-metrics",
                params={"from": "2026-01-01", "to": "2026-12-31"},
            )
            elapsed = perf_counter() - started

        assert response.status_code == 200
        assert response.json()["data"]["sample_count"] == 100000
        assert elapsed < 3
    finally:
        asyncio.run(cleanup())
