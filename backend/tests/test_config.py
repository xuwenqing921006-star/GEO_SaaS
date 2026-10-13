import base64
import os

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import async_engine_from_config, create_async_engine

from app.config import MigrationSettings, Settings

STRONG_SPECIAL_PASSWORD = "Strong@:/?#Password"


def generated_master_key() -> SecretStr:
    return SecretStr(base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"))


@pytest.mark.unit
def test_production_rejects_the_default_database_password() -> None:
    with pytest.raises(ValidationError, match="non-default database password"):
        Settings(_env_file=None, app_env="production")


@pytest.mark.unit
def test_production_rejects_the_default_migration_password() -> None:
    with pytest.raises(ValidationError, match="non-default migration database password"):
        MigrationSettings(_env_file=None, app_env="production")


@pytest.mark.unit
def test_production_rejects_a_short_database_password() -> None:
    with pytest.raises(ValidationError, match="non-default database password"):
        Settings(app_env="production", db_password=SecretStr("short-secret"))


@pytest.mark.unit
def test_production_accepts_a_non_default_database_password() -> None:
    settings = Settings(
        app_env="production",
        db_password=SecretStr(STRONG_SPECIAL_PASSWORD),
        app_master_key=generated_master_key(),
    )

    assert settings.app_env == "production"


@pytest.mark.unit
def test_production_requires_a_valid_master_key() -> None:
    with pytest.raises(ValidationError, match="requires APP_MASTER_KEY"):
        Settings(
            _env_file=None,
            app_env="production",
            db_password=SecretStr(STRONG_SPECIAL_PASSWORD),
        )
    with pytest.raises(ValidationError, match="exactly 32 bytes"):
        Settings(app_master_key=SecretStr("not-a-valid-master-key"))


@pytest.mark.unit
def test_runtime_database_url_round_trips_a_password_with_reserved_characters() -> None:
    settings = Settings(db_password=SecretStr(STRONG_SPECIAL_PASSWORD))

    parsed_url = make_url(settings.database_url.render_as_string(hide_password=False))

    assert parsed_url.username == "geo_app"
    assert parsed_url.password == STRONG_SPECIAL_PASSWORD


@pytest.mark.unit
def test_migration_database_url_uses_a_distinct_owner_and_reserved_password() -> None:
    settings = MigrationSettings(
        migration_db_user="geo_migrator",
        migration_db_password=SecretStr(STRONG_SPECIAL_PASSWORD),
    )

    parsed_url = make_url(settings.database_url.render_as_string(hide_password=False))

    assert parsed_url.username == "geo_migrator"
    assert parsed_url.password == STRONG_SPECIAL_PASSWORD


@pytest.mark.unit
def test_migration_owner_cannot_be_the_runtime_user() -> None:
    with pytest.raises(ValidationError, match="must be different"):
        MigrationSettings(migration_db_user="geo_app")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runtime_and_alembic_engines_accept_reserved_password_characters() -> None:
    runtime_settings = Settings(db_password=SecretStr(STRONG_SPECIAL_PASSWORD))
    migration_settings = MigrationSettings(
        migration_db_password=SecretStr(STRONG_SPECIAL_PASSWORD),
    )
    runtime_engine = create_async_engine(runtime_settings.database_url)
    migration_engine = async_engine_from_config(
        {"sqlalchemy.url": migration_settings.database_url},
        prefix="sqlalchemy.",
    )

    assert runtime_engine.url.password == STRONG_SPECIAL_PASSWORD
    assert migration_engine.url.password == STRONG_SPECIAL_PASSWORD

    await runtime_engine.dispose()
    await migration_engine.dispose()
