import base64
import binascii
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

WEAK_DATABASE_PASSWORDS = frozenset(
    {
        "",
        "changeme",
        "geo_app_dev",
        "geo_migrator_dev",
        "password",
        "postgres",
        "postgres_dev",
    }
)

SETTINGS_CONFIG = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    extra="ignore",
)


def _is_weak_password(password: SecretStr) -> bool:
    password_value = password.get_secret_value()
    return len(password_value) < 16 or password_value.casefold() in WEAK_DATABASE_PASSWORDS


def _valid_master_key(key: SecretStr | None) -> bool:
    if key is None:
        return False
    try:
        decoded = base64.urlsafe_b64decode(key.get_secret_value().encode("ascii"))
    except (UnicodeEncodeError, binascii.Error, ValueError):
        return False
    return len(decoded) == 32


class Settings(BaseSettings):
    model_config = SETTINGS_CONFIG

    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "geo-api"
    app_version: str = "0.1.0"
    db_host: str = "localhost"
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str = "geo_saas"
    db_user: str = "geo_app"
    db_password: SecretStr = SecretStr("geo_app_dev")
    app_master_key: SecretStr | None = None
    model_execution_mode: Literal["live", "fixed_mock"] = "live"
    publishing_execution_mode: Literal["live_browser", "fixed_mock"] = "live_browser"
    browser_executable_path: Path | None = None
    storage_root: Path = Path("./data")
    backup_status_path: Path = Path("./backups/backup-status.json")
    api_readiness_url: str = "http://api:8000/api/v1/health/ready"
    worker_heartbeat_interval_seconds: float = Field(default=5.0, gt=0)
    worker_heartbeat_timeout_seconds: float = Field(default=20.0, gt=0)

    @field_validator("app_master_key", mode="before")
    @classmethod
    def normalize_empty_master_key(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def reject_weak_production_database_credentials(self) -> Self:
        if self.app_env == "production" and _is_weak_password(self.db_password):
            raise ValueError("production requires a non-default database password")
        if self.app_master_key is not None and not _valid_master_key(self.app_master_key):
            raise ValueError("APP_MASTER_KEY must decode to exactly 32 bytes")
        if self.app_env == "production" and self.app_master_key is None:
            raise ValueError("production requires APP_MASTER_KEY")
        if self.app_env == "production" and self.model_execution_mode != "live":
            raise ValueError("production requires live model execution")
        return self

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )

    @property
    def worker_heartbeat_path(self) -> Path:
        return self.storage_root / "worker-heartbeat"


class MigrationSettings(BaseSettings):
    model_config = SETTINGS_CONFIG

    app_env: Literal["development", "test", "production"] = "development"
    db_host: str = "localhost"
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str = "geo_saas"
    db_user: str = "geo_app"
    migration_db_user: str = "geo_migrator"
    migration_db_password: SecretStr = SecretStr("geo_migrator_dev")

    @model_validator(mode="after")
    def protect_migration_ownership(self) -> Self:
        if self.migration_db_user == self.db_user:
            raise ValueError("migration and runtime database users must be different")
        if self.app_env == "production" and _is_weak_password(self.migration_db_password):
            raise ValueError("production requires a non-default migration database password")
        return self

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.migration_db_user,
            password=self.migration_db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )
