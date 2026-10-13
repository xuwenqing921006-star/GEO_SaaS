from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database import (
    Base,
    ContentDocument,
    ContentPublication,
    ContentVersion,
    PublishingAccount,
)
from app.publishing import (
    PublishResult,
    _as_utc,
    check_due_publishing_accounts,
    check_pending_publications,
    publishing_session_health,
    toutiao_publication_guard,
)


def _account(
    *,
    display_name: str = "测试账号",
    status: str = "connected",
    checked_at: datetime | None = None,
    error: str | None = None,
) -> PublishingAccount:
    return PublishingAccount(
        channel_id="toutiao",
        display_name=display_name,
        enabled=status == "connected",
        connection_status=status,
        last_checked_at=checked_at,
        last_error=error,
    )


@pytest.mark.unit
def test_session_health_distinguishes_due_soon_due_and_expired() -> None:
    now = datetime(2026, 8, 4, 12, tzinfo=UTC)

    healthy = publishing_session_health(
        _account(checked_at=now - timedelta(hours=6)),
        now=now,
    )
    due_soon = publishing_session_health(
        _account(checked_at=now - timedelta(hours=23)),
        now=now,
    )
    due = publishing_session_health(
        _account(checked_at=now - timedelta(hours=25)),
        now=now,
    )
    expired = publishing_session_health(
        _account(status="needs_login", error="头条号登录已失效"),
        now=now,
    )

    assert healthy.status == "healthy"
    assert due_soon.status == "check_due_soon"
    assert due.status == "check_due"
    assert expired.status == "expired"
    assert expired.next_check_at is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_toutiao_publication_guard_spaces_submissions_and_caps_24_hours(tmp_path) -> None:
    current = datetime(2026, 8, 10, 12, tzinfo=UTC)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'cadence.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as database:
            account = _account(display_name="头条节流账号", checked_at=current)
            database.add(account)
            await database.flush()
            database.add(
                ContentPublication(
                    document_id=uuid4(),
                    version_id=uuid4(),
                    publishing_account_id=account.id,
                    channel_id="toutiao",
                    status="pending_review",
                    submitted_at=current - timedelta(hours=1),
                    updated_at=current - timedelta(hours=1),
                ),
            )
            await database.commit()
            interval_message = await toutiao_publication_guard(
                database,
                account.id,
                now=current,
            )
            assert interval_message is not None
            assert "至少间隔3小时" in interval_message

            database.add(
                ContentPublication(
                    document_id=uuid4(),
                    version_id=uuid4(),
                    publishing_account_id=account.id,
                    channel_id="toutiao",
                    status="published",
                    submitted_at=current - timedelta(hours=8),
                    updated_at=current - timedelta(hours=8),
                ),
            )
            await database.commit()
            daily_message = await toutiao_publication_guard(
                database,
                account.id,
                now=current,
            )
            assert daily_message is not None
            assert "过去24小时已提交2篇" in daily_message
    finally:
        await engine.dispose()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_daily_check_only_rechecks_connected_accounts_that_are_due(tmp_path) -> None:
    current = datetime(2026, 8, 4, 12, tzinfo=UTC)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'publishing.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as database:
            due = _account(display_name="待复检账号", checked_at=current - timedelta(hours=25))
            recent = _account(display_name="近期已检账号", checked_at=current - timedelta(hours=1))
            expired = _account(
                display_name="已失效账号",
                status="needs_login",
                checked_at=current - timedelta(days=2),
            )
            database.add_all([due, recent, expired])
            await database.commit()
            due_id = due.id
            recent_id = recent.id
            expired_id = expired.id

        settings = Settings(
            app_env="test",
            db_password=SecretStr("unused"),
            storage_root=tmp_path,
            publishing_execution_mode="fixed_mock",
        )
        checked = await check_due_publishing_accounts(
            factory,
            settings,
            now=current,
            limit=5,
        )

        assert checked == 1
        async with factory() as database:
            refreshed_due = await database.get(PublishingAccount, due_id)
            refreshed_recent = await database.get(PublishingAccount, recent_id)
            refreshed_expired = await database.get(PublishingAccount, expired_id)
            assert refreshed_due is not None
            assert refreshed_recent is not None
            assert refreshed_expired is not None
            assert _as_utc(refreshed_due.last_checked_at) == current
            assert _as_utc(refreshed_recent.last_checked_at) == current - timedelta(hours=1)
            assert _as_utc(refreshed_expired.last_checked_at) == current - timedelta(days=2)
    finally:
        await engine.dispose()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pending_review_is_reconciled_to_published(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = datetime(2026, 8, 4, 12, tzinfo=UTC)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'review.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as database:
            client_id = uuid4()
            brief_id = uuid4()
            snapshot_id = uuid4()
            document = ContentDocument(
                client_id=client_id,
                brief_id=brief_id,
                title="审核中的文章",
                status="checked",
            )
            database.add(document)
            await database.flush()
            version = ContentVersion(
                document_id=document.id,
                version_number=1,
                title="审核中的文章",
                title_candidates=None,
                body_markdown="正文内容" * 100,
                outline_markdown=None,
                change_type="generated",
                provider="rules",
                model=None,
                fact_snapshot_id=snapshot_id,
                prompt_version=None,
                prompt_template_code=None,
                prompt_template_version=None,
                target_channel_id="sohu",
                contact_policy="omit",
                prompt_layers_snapshot=[],
                contact_allowed_urls=[],
                contact_sanitization_report={},
                image_material_ids=[],
                input_hash=None,
                output_hash=None,
                fallback_reason=None,
            )
            account = PublishingAccount(
                channel_id="sohu",
                display_name="搜狐测试账号",
                enabled=True,
                connection_status="connected",
                last_checked_at=current,
            )
            database.add_all([version, account])
            await database.flush()
            document.current_version_id = version.id
            publication = ContentPublication(
                document_id=document.id,
                version_id=version.id,
                publishing_account_id=account.id,
                channel_id="sohu",
                status="pending_review",
                submitted_at=current - timedelta(minutes=30),
                updated_at=current - timedelta(minutes=20),
            )
            database.add(publication)
            await database.commit()
            publication_id = publication.id

        async def published_result(*_args, **_kwargs) -> PublishResult:
            return PublishResult(
                status="published",
                public_url="https://www.sohu.com/a/1058760902_122960875",
                platform_post_id="1058760902_122960875",
            )

        monkeypatch.setattr(
            "app.publishing._lookup_pending_publication",
            published_result,
        )
        settings = Settings(
            app_env="test",
            db_password=SecretStr("unused"),
            storage_root=tmp_path,
            publishing_execution_mode="fixed_mock",
        )

        checked = await check_pending_publications(
            factory,
            settings,
            now=current,
        )

        assert checked == 1
        async with factory() as database:
            refreshed = await database.get(ContentPublication, publication_id)
            assert refreshed is not None
            assert refreshed.status == "published"
            assert refreshed.published_at is not None
            assert refreshed.public_url == "https://www.sohu.com/a/1058760902_122960875"
    finally:
        await engine.dispose()
