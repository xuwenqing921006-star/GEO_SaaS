import asyncio
import os
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.content import _append_version, _get_document
from app.database import (
    Client,
    ContentBrief,
    ContentDocument,
    ContentVersion,
    DiagnosticRun,
    FactSnapshot,
    Job,
    Material,
    StrategyBundle,
)
from app.jobs import claim_next_job
from app.knowledge_context import lock_content_fact_set


@pytest.mark.integration
def test_postgres_skip_locked_prevents_duplicate_worker_claims() -> None:
    database_url = os.getenv("TEST_POSTGRES_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_POSTGRES_DATABASE_URL is required for the PostgreSQL lock test")

    async def exercise() -> None:
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        client_id = uuid4()
        material_id = uuid4()
        async with factory() as database:
            # This test exercises the global worker queue. Remove only stale rows
            # created by earlier interrupted runs of this same test so the two
            # claims cannot be consumed by unrelated leftovers.
            await database.execute(
                delete(Job).where(Job.idempotency_key.like("lock-test-%")),
            )
            database.add(
                Client(
                    id=client_id,
                    standard_name=f"PostgreSQL 锁测试-{client_id}",
                    normalized_name=f"postgres-lock-{client_id}",
                    industry_code="repair",
                    industry_name="维修服务",
                    province="山东省",
                    city="青岛市",
                    district="即墨区",
                    address="测试地址",
                    cooperation_started_on=date(2026, 7, 27),
                ),
            )
            await database.flush()
            database.add(
                Material(
                    id=material_id,
                    client_id=client_id,
                    file_name="lock-test.txt",
                    media_type="text/plain",
                    size_bytes=4,
                    sha256="0" * 64,
                    storage_key=f"lock-tests/{material_id}.txt",
                    category="other",
                    authorization_status="authorized",
                ),
            )
            await database.flush()
            job = Job(
                client_id=client_id,
                material_id=material_id,
                job_type="material_extract",
                idempotency_key=f"lock-test-{client_id}",
                payload={"force": False, "languages": ["zh-CN"]},
                created_at=datetime.now(UTC) - timedelta(days=3650),
            )
            database.add(job)
            await database.commit()
            job_id = job.id

        try:
            claimed = await asyncio.gather(
                claim_next_job(factory),
                claim_next_job(factory),
            )
            claimed_ids = [job.id for job in claimed if job is not None]
            assert claimed_ids.count(job_id) == 1
            assert len(claimed_ids) == len(set(claimed_ids))
        finally:
            async with factory() as database:
                await database.execute(delete(Job).where(Job.id == job_id))
                await database.execute(delete(Material).where(Material.id == material_id))
                await database.execute(delete(Client).where(Client.id == client_id))
                await database.commit()
            await engine.dispose()

    asyncio.run(exercise())


@pytest.mark.integration
def test_postgres_client_fact_set_lock_serializes_phantom_inserts() -> None:
    database_url = os.getenv("TEST_POSTGRES_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_POSTGRES_DATABASE_URL is required for the PostgreSQL lock test")

    async def exercise() -> None:
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        client_id = uuid4()
        first_acquired = asyncio.Event()
        release_first = asyncio.Event()
        second_acquired = asyncio.Event()

        async def hold_first() -> None:
            async with factory() as database:
                async with database.begin():
                    await lock_content_fact_set(database, client_id)
                    first_acquired.set()
                    await release_first.wait()

        async def wait_second() -> None:
            async with factory() as database:
                async with database.begin():
                    await lock_content_fact_set(database, client_id)
                    second_acquired.set()

        first = asyncio.create_task(hold_first())
        await first_acquired.wait()
        second = asyncio.create_task(wait_second())
        await asyncio.sleep(0.1)
        assert second_acquired.is_set() is False
        release_first.set()
        await asyncio.gather(first, second)
        assert second_acquired.is_set() is True
        await engine.dispose()

    asyncio.run(exercise())


@pytest.mark.integration
def test_postgres_document_lock_allows_only_one_same_version_save() -> None:
    database_url = os.getenv("TEST_POSTGRES_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_POSTGRES_DATABASE_URL is required for the PostgreSQL lock test")

    async def exercise() -> None:
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        client_id = uuid4()
        diagnostic_id = uuid4()
        bundle_id = uuid4()
        brief_id = uuid4()
        snapshot_id = uuid4()
        document_id = uuid4()
        source_id = uuid4()
        async with factory() as database:
            client = Client(
                id=client_id,
                standard_name=f"PostgreSQL 内容锁测试-{client_id}",
                normalized_name=f"postgres-content-lock-{client_id}",
                industry_code="repair",
                industry_name="维修服务",
                province="山东省",
                city="青岛市",
                district="即墨区",
                address="测试地址",
                cooperation_started_on=date(2026, 7, 27),
            )
            diagnostic = DiagnosticRun(
                id=diagnostic_id,
                client_id=client_id,
                status="completed",
                monitoring_window_days=30,
            )
            bundle = StrategyBundle(
                id=bundle_id,
                client_id=client_id,
                diagnostic_run_id=diagnostic_id,
            )
            brief = ContentBrief(
                id=brief_id,
                bundle_id=bundle_id,
                client_id=client_id,
                title="并发编辑测试",
                content_type="service_explainer",
                target_level="L1",
                audience="本地用户",
                angle="事实说明",
                expected_recommendation_reason="测试",
                priority=1,
            )
            snapshot = FactSnapshot(
                id=snapshot_id,
                client_id=client_id,
                brief_id=brief_id,
                brief_version=1,
                facts=[],
                evidence=[],
                brief_context={},
            )
            document = ContentDocument(
                id=document_id,
                client_id=client_id,
                brief_id=brief_id,
                title="并发编辑测试",
                status="checked",
                current_version_id=source_id,
                version=1,
            )
            source = ContentVersion(
                id=source_id,
                document_id=document_id,
                version_number=1,
                title="并发编辑测试",
                body_markdown="初始正文",
                change_type="generated",
                provider="rules",
                fact_snapshot_id=snapshot_id,
            )
            database.add(client)
            await database.flush()
            database.add(diagnostic)
            await database.flush()
            database.add(bundle)
            await database.flush()
            database.add(brief)
            await database.flush()
            database.add(snapshot)
            await database.flush()
            database.add(document)
            await database.flush()
            database.add(source)
            await database.commit()

        first_locked = asyncio.Event()
        release_first = asyncio.Event()
        second_finished = asyncio.Event()

        async def save(suffix: str, hold_lock: bool) -> int:
            async with factory() as database:
                async with database.begin():
                    document = await _get_document(
                        database,
                        document_id,
                        for_update=True,
                    )
                    if document.version != 1:
                        second_finished.set()
                        return 409
                    source = await database.get(ContentVersion, document.current_version_id)
                    assert source is not None
                    if hold_lock:
                        first_locked.set()
                        await release_first.wait()
                    await _append_version(
                        database,
                        document,
                        title=source.title,
                        body=f"{source.body_markdown}-{suffix}",
                        outline=source.outline_markdown,
                        change_type="manual_edit",
                        provider="user",
                        model=None,
                        snapshot_id=source.fact_snapshot_id,
                        prompt_version=None,
                    )
                    second_finished.set()
                    return 200

        first = asyncio.create_task(save("first", True))
        await first_locked.wait()
        second = asyncio.create_task(save("second", False))
        await asyncio.sleep(0.1)
        assert second_finished.is_set() is False
        release_first.set()
        statuses = await asyncio.gather(first, second)
        assert sorted(statuses) == [200, 409]

        async with factory() as database:
            versions = list(
                (
                    await database.scalars(
                        select(ContentVersion).where(
                            ContentVersion.document_id == document_id,
                        ),
                    )
                ).all(),
            )
            document = await database.get(ContentDocument, document_id)
            assert len(versions) == 2
            assert document is not None
            assert document.version == 2
        await engine.dispose()

    asyncio.run(exercise())
