import asyncio
import shutil
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database import Base, Owner
from app.health import ReadinessSnapshot
from app.jobs import process_one_job
from app.main import create_app
from app.security import hash_password

E2E_ROOT = Path(tempfile.mkdtemp(prefix="geo-saas-t007-e2e-"))
ENGINE = create_async_engine(f"sqlite+aiosqlite:///{E2E_ROOT / 'e2e.db'}")
SESSION_FACTORY = async_sessionmaker(ENGINE, expire_on_commit=False)
SETTINGS = Settings(
    _env_file=None,
    app_env="test",
    storage_root=E2E_ROOT / "storage",
    db_password=SecretStr("unused"),
    model_execution_mode="fixed_mock",
    publishing_execution_mode="fixed_mock",
)


class E2EHealthService:
    async def readiness(self) -> ReadinessSnapshot:
        return ReadinessSnapshot(
            status="ready",
            database="ok",
            storage="ok",
            worker_heartbeat="ok",
        )


app = create_app(
    settings=SETTINGS,
    health_service=E2EHealthService(),
    engine_override=ENGINE,
)


async def _worker_loop() -> None:
    while True:
        processed = await process_one_job(SESSION_FACTORY, SETTINGS)
        await asyncio.sleep(0.02 if processed else 0.1)


@asynccontextmanager
async def e2e_lifespan(_application: FastAPI) -> AsyncIterator[None]:
    async with ENGINE.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with SESSION_FACTORY() as database:
        database.add(
            Owner(
                username="owner",
                display_name="平台负责人",
                password_hash=hash_password("CorrectPassword2026!"),
            ),
        )
        await database.commit()
    worker_task = asyncio.create_task(_worker_loop())
    try:
        yield
    finally:
        worker_task.cancel()
        with suppress(asyncio.CancelledError):
            await worker_task
        await ENGINE.dispose()
        shutil.rmtree(E2E_ROOT, ignore_errors=True)


app.router.lifespan_context = e2e_lifespan
