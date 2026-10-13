from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.unit
def test_compose_passes_database_fields_without_building_a_dsn() -> None:
    compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "DATABASE_URL:" not in compose
    assert "postgresql+asyncpg://" not in compose
    assert 'DB_PASSWORD: "${GEO_APP_PASSWORD:' in compose
    assert 'MIGRATION_DB_PASSWORD: "${GEO_MIGRATION_PASSWORD:' in compose


@pytest.mark.unit
def test_runtime_processes_do_not_receive_or_use_migration_credentials() -> None:
    compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")
    worker_section = compose.split("  worker:", maxsplit=1)[1].split("  db:", maxsplit=1)[0]
    app_sources = "\n".join(
        [
            (PROJECT_ROOT / "backend/app/main.py").read_text(encoding="utf-8"),
            (PROJECT_ROOT / "backend/app/worker.py").read_text(encoding="utf-8"),
        ]
    )
    migration_source = (PROJECT_ROOT / "backend/migrations/env.py").read_text(encoding="utf-8")

    assert "MIGRATION_DB_" not in worker_section
    assert "alembic" not in worker_section
    assert "unset MIGRATION_DB_USER MIGRATION_DB_PASSWORD" in compose
    assert "MigrationSettings" not in app_sources
    assert "MigrationSettings" in migration_source


@pytest.mark.unit
def test_runtime_role_has_dml_but_not_schema_ownership_or_create() -> None:
    init_script = (PROJECT_ROOT / "backend/postgres/bootstrap-roles.sh").read_text(encoding="utf-8")

    assert 'ALTER SCHEMA public OWNER TO :"migration_user"' in init_script
    assert 'REASSIGN OWNED BY :"app_user" TO :"migration_user"' in init_script
    assert 'REVOKE CREATE ON SCHEMA public FROM :"app_user"' in init_script
    assert 'GRANT USAGE ON SCHEMA public TO :"app_user"' in init_script
    assert 'GRANT USAGE, CREATE ON SCHEMA public TO :"app_user"' not in init_script
    assert 'ALTER DEFAULT PRIVILEGES FOR ROLE :"migration_user" IN SCHEMA public' in init_script
    assert (
        'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"app_user"'
        in init_script
    )


@pytest.mark.unit
def test_role_bootstrap_runs_for_existing_volumes_and_is_idempotent() -> None:
    compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")
    start_script = (PROJECT_ROOT / "backend/postgres/start.sh").read_text(encoding="utf-8")
    bootstrap_script = (PROJECT_ROOT / "backend/postgres/bootstrap-roles.sh").read_text(
        encoding="utf-8"
    )

    assert "docker-entrypoint-initdb.d" not in compose
    assert "/usr/local/bin/docker-entrypoint.sh" in start_script
    assert "geo-saas-bootstrap-roles.sh" in start_script
    assert "PG_VERSION" not in start_script
    assert "WHERE NOT EXISTS" in bootstrap_script
    assert 'REASSIGN OWNED BY :"app_user" TO :"migration_user"' in bootstrap_script
    assert "geo-saas-bootstrap-ready" in compose


@pytest.mark.unit
def test_empty_and_existing_volume_paths_wait_for_the_final_tcp_server_before_bootstrap() -> None:
    compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")
    start_script = (PROJECT_ROOT / "backend/postgres/start.sh").read_text(encoding="utf-8")

    official_entrypoint_index = start_script.index("/usr/local/bin/docker-entrypoint.sh")
    tcp_ready_index = start_script.index("--host 127.0.0.1")
    bootstrap_index = start_script.index("geo-saas-bootstrap-roles.sh")
    ready_marker_index = start_script.index('touch "$BOOTSTRAP_READY_FILE"')

    assert "docker-entrypoint-initdb.d" not in compose
    assert "PG_VERSION" not in start_script
    assert official_entrypoint_index < tcp_ready_index < bootstrap_index < ready_marker_index
    assert "--port 5432" in start_script
    assert "pg_isready -h 127.0.0.1 -p 5432" in compose


@pytest.mark.unit
def test_database_startup_rotates_admin_password_and_rejects_weak_production_values() -> None:
    compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")
    api_section = compose.split("  api:", maxsplit=1)[1].split("  worker:", maxsplit=1)[0]
    worker_section = compose.split("  worker:", maxsplit=1)[1].split("  db:", maxsplit=1)[0]
    db_section = compose.rsplit("\n  db:", maxsplit=1)[1].split("networks:", maxsplit=1)[0]
    start_script = (PROJECT_ROOT / "backend/postgres/start.sh").read_text(encoding="utf-8")
    bootstrap_script = (PROJECT_ROOT / "backend/postgres/bootstrap-roles.sh").read_text(
        encoding="utf-8"
    )

    assert "POSTGRES_ADMIN_PASSWORD" not in api_section
    assert "POSTGRES_ADMIN_PASSWORD" not in worker_section
    assert 'APP_ENV: "${APP_ENV:-development}"' in db_section
    assert "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}" in start_script
    assert "production requires a strong administrator password" in start_script
    assert "postgres_dev" in start_script
    assert '"${#1}" -lt 16' in start_script
    assert "return 0\n}" in start_script
    assert 'ALTER ROLE :"admin_user" WITH LOGIN PASSWORD' in bootstrap_script
    assert 'if [ ! -f "$BOOTSTRAP_READY_FILE" ]' in start_script
    assert "roles, grants, or administrator password rotation could not be applied" in start_script
