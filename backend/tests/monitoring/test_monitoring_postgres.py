import asyncio
import os
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Client, MonitoringQuestionSet
from app.monitoring import lock_monitoring_client, lock_monitoring_question_set


@pytest.mark.integration
def test_postgres_monitoring_locks_serialize_version_and_batch_creation() -> None:
    database_url = os.getenv("TEST_POSTGRES_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_POSTGRES_DATABASE_URL is required for the PostgreSQL lock test")

    async def exercise() -> None:
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        client_id = uuid4()
        question_set_id = uuid4()
        async with factory() as database:
            database.add(
                Client(
                    id=client_id,
                    standard_name=f"监测并发测试-{client_id}",
                    normalized_name=f"monitoring-lock-{client_id}",
                    industry_code="repair",
                    industry_name="维修服务",
                    province="山东省",
                    city="青岛市",
                    district="即墨区",
                    address="测试地址",
                    cooperation_started_on=date(2026, 7, 28),
                ),
            )
            await database.flush()
            database.add(
                MonitoringQuestionSet(
                    id=question_set_id,
                    client_id=client_id,
                    name="并发问题集",
                    frozen=False,
                    questions=[
                        {
                            "id": str(uuid4()),
                            "text": "即墨维修服务怎么选?",
                            "family": "category_discovery",
                            "is_brand_query": False,
                            "target_level": "L2",
                            "priority": 1,
                        },
                    ],
                ),
            )
            await database.commit()

        first_locked = asyncio.Event()
        release_first = asyncio.Event()
        second_locked = asyncio.Event()
        observed_version: list[int] = []

        async def first_update() -> None:
            async with factory() as database:
                async with database.begin():
                    question_set = await lock_monitoring_question_set(
                        database,
                        question_set_id,
                    )
                    assert question_set is not None
                    first_locked.set()
                    await release_first.wait()
                    question_set.version += 1

        async def second_update() -> None:
            async with factory() as database:
                async with database.begin():
                    question_set = await lock_monitoring_question_set(
                        database,
                        question_set_id,
                    )
                    assert question_set is not None
                    observed_version.append(question_set.version)
                    second_locked.set()

        first = asyncio.create_task(first_update())
        await first_locked.wait()
        second = asyncio.create_task(second_update())
        await asyncio.sleep(0.1)
        assert second_locked.is_set() is False
        release_first.set()
        await asyncio.gather(first, second)
        assert observed_version == [2]

        client_first_locked = asyncio.Event()
        release_client_first = asyncio.Event()
        client_second_locked = asyncio.Event()

        async def first_batch_gate() -> None:
            async with factory() as database:
                async with database.begin():
                    assert await lock_monitoring_client(database, client_id) is not None
                    client_first_locked.set()
                    await release_client_first.wait()

        async def second_batch_gate() -> None:
            async with factory() as database:
                async with database.begin():
                    assert await lock_monitoring_client(database, client_id) is not None
                    client_second_locked.set()

        first_client = asyncio.create_task(first_batch_gate())
        await client_first_locked.wait()
        second_client = asyncio.create_task(second_batch_gate())
        await asyncio.sleep(0.1)
        assert client_second_locked.is_set() is False
        release_client_first.set()
        await asyncio.gather(first_client, second_client)
        assert client_second_locked.is_set() is True
        await engine.dispose()

    asyncio.run(exercise())
