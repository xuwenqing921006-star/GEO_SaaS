from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.unit
def test_backend_image_prepares_the_shared_volume_before_switching_to_non_root() -> None:
    dockerfile = (PROJECT_ROOT / "backend/Dockerfile").read_text(encoding="utf-8")

    create_data_index = dockerfile.index("mkdir -p /app /data")
    chown_data_index = dockerfile.index("chown 10001:10001 /app /data")
    non_root_user_index = dockerfile.index("USER app")

    assert create_data_index < chown_data_index < non_root_user_index
    assert "useradd --uid 10001 --gid app" in dockerfile


@pytest.mark.unit
def test_api_and_worker_are_the_only_services_using_the_heartbeat_volume() -> None:
    compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")
    web_section = compose.split("  web:", maxsplit=1)[1].split("  api:", maxsplit=1)[0]
    api_section = compose.split("  api:", maxsplit=1)[1].split("  worker:", maxsplit=1)[0]
    worker_section = compose.split("  worker:", maxsplit=1)[1].split("\n  db:", maxsplit=1)[0]
    db_section = compose.rsplit("\n  db:", maxsplit=1)[1].split("\nnetworks:", maxsplit=1)[0]

    assert "- geo_data:/data" in api_section
    assert "- geo_data:/data" in worker_section
    assert "read_only: true" in api_section
    assert "read_only: true" in worker_section
    assert "geo_data:/data" not in web_section
    assert "geo_data:/data" not in db_section
    assert compose.count("- geo_data:/data") == 2

    for unapproved_client in ("mobile", "desktop", "electron", "miniprogram", "miniapp"):
        assert not (PROJECT_ROOT / unapproved_client).exists()


@pytest.mark.unit
def test_production_images_are_versioned_and_base_images_are_digest_pinned() -> None:
    compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")
    production = (PROJECT_ROOT / "compose.production.yaml").read_text(encoding="utf-8")
    backend_dockerfile = (PROJECT_ROOT / "backend/Dockerfile").read_text(encoding="utf-8")
    frontend_dockerfile = (PROJECT_ROOT / "frontend/Dockerfile").read_text(encoding="utf-8")
    backup_dockerfile = (PROJECT_ROOT / "ops/Dockerfile.backup").read_text(encoding="utf-8")
    caddy_dockerfile = (PROJECT_ROOT / "ops/Dockerfile.caddy").read_text(encoding="utf-8")
    postgres_dockerfile = (PROJECT_ROOT / "backend/postgres/Dockerfile").read_text(encoding="utf-8")

    assert "FROM python:3.13-slim@sha256:" in backend_dockerfile
    assert "COPY --from=ghcr.io/astral-sh/uv:0.11.30@sha256:" in backend_dockerfile
    assert "FROM node:24-alpine@sha256:" in frontend_dockerfile
    assert "FROM nginxinc/nginx-unprivileged:1.29-alpine@sha256:" in frontend_dockerfile
    assert "FROM postgres:18-alpine@sha256:" in backup_dockerfile
    assert "FROM golang:1.26.4-alpine3.24@sha256:" in backup_dockerfile
    assert "FROM golang:1.26.4-alpine3.24@sha256:" in caddy_dockerfile
    assert "FROM alpine:3.24@sha256:" in caddy_dockerfile
    assert "FROM postgres:18-alpine@sha256:" in postgres_dockerfile
    assert "apk add --no-cache su-exec" in postgres_dockerfile
    versioned_image_lines = [
        line
        for line in production.splitlines()
        if line.strip().startswith("image:") and "${APP_VERSION:-0.1.0}" in line
    ]
    versioned_compose_lines = [
        line
        for line in compose.splitlines()
        if line.strip().startswith("image:") and "${APP_VERSION:-0.1.0}" in line
    ]
    assert len(versioned_image_lines) == 6
    assert len(versioned_compose_lines) == 1
    for service in ("caddy", "web", "api", "worker", "backup"):
        assert f"/{service}:${{APP_VERSION:-0.1.0}}" in production
    assert production.count("/backup:${APP_VERSION:-0.1.0}") == 2
    restore_section = production.split("  restore:", maxsplit=1)[1]
    assert "cap_drop:\n      - ALL" in restore_section
    assert "cap_add:\n      - CHOWN\n      - DAC_OVERRIDE" in restore_section
    assert "/postgres:${APP_VERSION:-0.1.0}" in compose


@pytest.mark.unit
def test_weekly_backups_are_self_contained_and_restore_is_transactional() -> None:
    backup = (PROJECT_ROOT / "ops/backup.sh").read_text(encoding="utf-8")
    restore = (PROJECT_ROOT / "ops/restore.sh").read_text(encoding="utf-8")

    assert 'cd "${daily_dir}"' in backup
    assert 'cd "${weekly_dir}"' in backup
    assert 'sha256sum "${backup_name}.tar.age"' in backup
    assert 'force_weekly="${BACKUP_FORCE_WEEKLY:-0}"' in backup
    assert (
        'cp --preserve=timestamps \\\n    "${daily_dir}/${backup_name}.tar.age.sha256"'
        not in backup
    )

    assert "--single-transaction" in restore
    assert 'previous_files="${work_dir}/previous-files.tar"' in restore
    assert 'previous_database="${work_dir}/previous-database.dump"' in restore
    assert "restore_rolled_back_files" in restore
    assert "restore_rolled_back_database" in restore
    assert restore.count("--no-same-owner") == 3
    assert restore.count("chown -R 10001:10001 /data") == 2
    assert "--no-overwrite-dir" in restore
    assert 'cp -R "${restored_files}/." /data/' in restore


@pytest.mark.unit
def test_release_drill_uses_random_stack_and_the_documented_restore_profile() -> None:
    drill = (PROJECT_ROOT / "scripts/t013_release_drill.ps1").read_text(encoding="utf-8")

    assert '[guid]::NewGuid().ToString("N").Substring(0, 12)' in drill
    assert "$stackCreated = $false" in drill
    assert "--profile restore" in drill
    assert "run --rm `" in drill
    assert "/run/secrets/backup_age_identity:ro" in drill
    assert "--entrypoint /usr/local/bin/geo-restore" not in drill
