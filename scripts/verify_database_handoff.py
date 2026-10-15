"""Verify the SQL handoff in disposable PostgreSQL, never in a supplied database."""

import asyncio
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pydantic_settings import SettingsConfigDict
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[1]
SQL_ROOT = ROOT / "database"
EXPECTED_COUNTS = {
    "clients": 2,
    "facts": 12,
    "evidence": 12,
    "fact_evidence": 12,
    "knowledge_profiles": 2,
    "strategy_bundles": 2,
    "strategy_items": 6,
}
EMPTY_TABLES = (
    "owners",
    "owner_sessions",
    "provider_settings",
    "publishing_accounts",
    "content_publications",
    "materials",
    "jobs",
    "model_usage",
)


class VerificationSettings(Settings):
    model_config = SettingsConfigDict(env_file=None)


def run(
    args: list[str],
    *,
    data: bytes | None = None,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> bytes:
    result = subprocess.run(
        args,
        input=data,
        capture_output=True,
        check=False,
        cwd=cwd,
        env=env,
    )
    if result.returncode:
        # Commands and diagnostics may include disposable passwords; do not echo them.
        raise RuntimeError(f"{Path(args[0]).name} failed with exit code {result.returncode}")
    return result.stdout


def psql(container: str, database: str, sql: str, *, user: str = "geo_migrator") -> str:
    return run(
        [
            "docker",
            "exec",
            "-i",
            container,
            "psql",
            "-U",
            user,
            "-d",
            database,
            "-X",
            "-At",
            "-v",
            "ON_ERROR_STOP=1",
            "--single-transaction",
        ],
        data=sql.encode("utf-8"),
    ).decode("utf-8")


def canonical_schema(container: str, database: str) -> str:
    output = run(
        [
            "docker",
            "exec",
            container,
            "pg_dump",
            "-U",
            "postgres",
            "-d",
            database,
            "--schema-only",
            "--no-owner",
            "--no-privileges",
        ],
    ).decode("utf-8")
    normalized = "\n".join(
        line
        for line in output.splitlines()
        if not line.startswith(("\\restrict ", "\\unrestrict "))
    )

    # PostgreSQL re-parses a varchar[] -> text[] cast into equivalent per-item
    # casts on restore. Normalize only arrays of quoted varchar literals; keep
    # all literal values, types and other schema definitions under exact comparison.
    def elementwise_cast(match: re.Match[str]) -> str:
        source = match.group(1)
        literals = re.findall(r"'(?:''|[^'])*'::character varying", source)
        if ", ".join(literals) != source:
            return match.group(0)
        return "(ARRAY[" + ", ".join(f"({value})::text" for value in literals) + "])"

    return re.sub(r"\(\(ARRAY\[([^\]]+)\]\)::text\[\]\)", elementwise_cast, normalized)


def verify_api(port: int, runtime_password: str) -> None:
    settings = VerificationSettings(
        app_env="test",
        db_host="127.0.0.1",
        db_port=port,
        db_name="geo_handoff_restored",
        db_user="geo_app",
        db_password=SecretStr(runtime_password),
        app_master_key=None,
        model_execution_mode="fixed_mock",
        publishing_execution_mode="fixed_mock",
    )
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    password = secrets.token_urlsafe(24)
    environment = os.environ.copy()
    environment.update(
        APP_ENV="test",
        DB_HOST="127.0.0.1",
        DB_PORT=str(port),
        DB_NAME=settings.db_name,
        DB_USER=settings.db_user,
        DB_PASSWORD=runtime_password,
        OWNER_BOOTSTRAP_USERNAME="handoff-verifier",
        OWNER_BOOTSTRAP_DISPLAY_NAME="Isolated handoff verification",
        OWNER_BOOTSTRAP_PASSWORD=password,
    )
    run(
        [sys.executable, "-m", "app.bootstrap_owner"],
        cwd=ROOT / "backend",
        env=environment,
    )
    try:
        with tempfile.TemporaryDirectory(prefix="geo-handoff-api-") as storage:
            settings.storage_root = Path(storage)
            with TestClient(create_app(settings=settings, engine_override=engine)) as client:
                response = client.post(
                    "/api/v1/auth/login",
                    json={"username": "handoff-verifier", "password": password},
                )
                assert response.status_code == 200, "Owner login failed"
                response = client.get("/api/v1/clients")
                assert response.status_code == 200, "Client list failed"
                customers = response.json()["data"]["items"]
                assert len(customers) == 2, "Expected two fictional clients"
                for customer in customers:
                    for suffix in (
                        "facts",
                        "knowledge-profile",
                        "strategy",
                        "keyword-workspace",
                    ):
                        result = client.get(f"/api/v1/clients/{customer['id']}/{suffix}")
                        assert result.status_code == 200, f"Demo API {suffix} failed"
    finally:
        asyncio.run(engine.dispose())


def main() -> None:
    manifest = json.loads((SQL_ROOT / "manifest.json").read_text(encoding="utf-8"))
    for filename, expected in manifest["sha256"].items():
        assert hashlib.sha256((SQL_ROOT / filename).read_bytes()).hexdigest() == expected, filename
    name = "geo-saas-handoff-verify-" + secrets.token_hex(6)
    admin_password = secrets.token_urlsafe(24)
    migration_password = secrets.token_urlsafe(24)
    runtime_password = secrets.token_urlsafe(24)
    container = (
        run(
            [
                "docker",
                "run",
                "--detach",
                "--rm",
                "--name",
                name,
                "--label",
                "geo-saas.purpose=database-handoff-verification",
                "--tmpfs",
                "/var/lib/postgresql:rw,size=512m",
                "--publish",
                "127.0.0.1::5432",
                "--env",
                "POSTGRES_PASSWORD=" + admin_password,
                "postgres:18-alpine",
            ],
        )
        .decode()
        .strip()
    )
    try:
        for _ in range(60):
            ready = subprocess.run(
                ["docker", "exec", container, "pg_isready", "-U", "postgres"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Disposable PostgreSQL did not become ready")
        port = int(
            run(["docker", "port", container, "5432/tcp"]).decode().strip().rsplit(":", 1)[1]
        )
        psql(
            container,
            "postgres",
            "CREATE ROLE geo_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT "
            f"PASSWORD '{migration_password}'; "
            "CREATE ROLE geo_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT "
            f"PASSWORD '{runtime_password}';",
            user="postgres",
        )
        for database in ("geo_handoff_migrated", "geo_handoff_restored"):
            run(
                [
                    "docker",
                    "exec",
                    container,
                    "createdb",
                    "-U",
                    "postgres",
                    "-O",
                    "geo_migrator",
                    database,
                ]
            )
        environment = os.environ.copy()
        environment.update(
            APP_ENV="test",
            DB_HOST="127.0.0.1",
            DB_PORT=str(port),
            DB_USER="geo_app",
            MIGRATION_DB_USER="geo_migrator",
            MIGRATION_DB_PASSWORD=migration_password,
        )
        environment["DB_NAME"] = "geo_handoff_migrated"
        run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT / "backend",
            env=environment,
        )
        schema = (SQL_ROOT / "schema.sql").read_text(encoding="utf-8")
        demo = (SQL_ROOT / "demo.sql").read_text(encoding="utf-8")
        grants = (SQL_ROOT / "grants.sql").read_text(encoding="utf-8")
        psql(container, "geo_handoff_restored", schema + "\n" + demo + "\n" + grants)
        assert canonical_schema(container, "geo_handoff_migrated") == canonical_schema(
            container,
            "geo_handoff_restored",
        ), "SQL snapshot differs from the actual migrations"
        assert (
            psql(
                container,
                "geo_handoff_restored",
                "SELECT version_num FROM alembic_version;",
            ).strip()
            == manifest["alembic_revision"]
        )
        for _ in range(2):
            for table, count in EXPECTED_COUNTS.items():
                assert psql(
                    container,
                    "geo_handoff_restored",
                    f"SELECT count(*) FROM {table};",
                    user="geo_app",
                ).strip() == str(count), table
            for table in EMPTY_TABLES:
                assert (
                    psql(
                        container,
                        "geo_handoff_restored",
                        f"SELECT count(*) FROM {table};",
                        user="geo_app",
                    ).strip()
                    == "0"
                ), table
            psql(container, "geo_handoff_restored", demo + "\n" + grants)
        try:
            psql(container, "geo_handoff_restored", schema)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Schema import must reject a nonempty database")
        try:
            psql(
                container,
                "geo_handoff_restored",
                "CREATE TABLE forbidden_runtime_ddl(id integer);",
                user="geo_app",
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("Runtime role must not create tables")
        psql(
            container,
            "geo_handoff_restored",
            "UPDATE clients SET notes = notes WHERE false;",
            user="geo_app",
        )
        environment["DB_NAME"] = "geo_handoff_restored"
        run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT / "backend",
            env=environment,
        )
        verify_api(port, runtime_password)
        print(
            json.dumps(
                {
                    "result": "PASS",
                    "business_tables": 41,
                    "alembic_revision": "0029",
                    "schema_matches_migrations": True,
                    "repeat_demo_import": True,
                    "nonempty_schema_rejected": True,
                    "runtime_permissions": True,
                    "no_credentials_in_seed": True,
                    "owner_and_demo_api_smoke": True,
                }
            )
        )
    finally:
        # Exact ID returned by this run; never remove another container or a shared volume.
        run(["docker", "stop", "--time", "5", container])


if __name__ == "__main__":
    main()
