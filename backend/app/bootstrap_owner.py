import asyncio
import logging
import os

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database import Owner
from app.security import hash_password

LOGGER = logging.getLogger("geo-saas.bootstrap")


async def bootstrap_owner() -> None:
    username = os.environ.get("OWNER_BOOTSTRAP_USERNAME", "owner").strip()
    display_name = os.environ.get("OWNER_BOOTSTRAP_DISPLAY_NAME", "平台负责人").strip()
    password = os.environ.get("OWNER_BOOTSTRAP_PASSWORD", "")
    if len(username) < 3 or len(password) < 12:
        raise RuntimeError("owner bootstrap credentials are missing or too short")

    settings = Settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            existing = await session.scalar(select(Owner).limit(1))
            if existing is not None:
                raise RuntimeError("owner already exists; bootstrap does not overwrite passwords")
            session.add(
                Owner(
                    username=username,
                    display_name=display_name,
                    password_hash=hash_password(password),
                ),
            )
            try:
                await session.commit()
            except IntegrityError as error:
                await session.rollback()
                raise RuntimeError(
                    "owner already exists; bootstrap does not overwrite passwords",
                ) from error
            LOGGER.info("owner_bootstrap_completed", extra={"event": "owner_bootstrap"})
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(bootstrap_owner())
