#!/usr/bin/env bash
set -Eeuo pipefail

: "${PGHOST:?PGHOST is required}"
: "${PGDATABASE:?PGDATABASE is required}"
: "${PGUSER:?PGUSER is required}"
: "${PGPASSWORD:?PGPASSWORD is required}"
: "${BACKUP_AGE_RECIPIENT:?BACKUP_AGE_RECIPIENT is required}"

daily_days="${BACKUP_DAILY_RETENTION_DAYS:-14}"
weekly_days="${BACKUP_WEEKLY_RETENTION_DAYS:-56}"
force_weekly="${BACKUP_FORCE_WEEKLY:-0}"
if [[ "${force_weekly}" != "0" && "${force_weekly}" != "1" ]]; then
  printf 'backup_refused BACKUP_FORCE_WEEKLY_must_be_0_or_1\n' >&2
  exit 2
fi
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_name="geo-saas-${timestamp}"
work_dir="/work/${backup_name}"
daily_dir="/backups/daily"
weekly_dir="/backups/weekly"
status_file="/backups/backup-status.json"
backup_completed=0

mkdir -p "${work_dir}" "${daily_dir}" "${weekly_dir}"
cleanup() {
  exit_code=$?
  status_tmp="${status_file}.tmp"
  printf '{"success":%s,"completed_at":"%s","app_version":"%s"}\n' \
    "$([[ "${backup_completed}" == "1" ]] && printf true || printf false)" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "${APP_VERSION:-unknown}" \
    > "${status_tmp}"
  mv "${status_tmp}" "${status_file}"
  rm -rf -- "${work_dir}"
  exit "${exit_code}"
}
trap cleanup EXIT

pg_dump \
  --format=custom \
  --no-owner \
  --no-privileges \
  --file="${work_dir}/database.dump" \
  "${PGDATABASE}"

tar \
  --create \
  --file="${work_dir}/files.tar" \
  --directory=/data \
  .

psql \
  --no-psqlrc \
  --tuples-only \
  --no-align \
  --command="
    SELECT json_build_object(
      'clients', (SELECT count(*) FROM clients),
      'facts', (SELECT count(*) FROM facts),
      'content_versions', (SELECT count(*) FROM content_versions),
      'monitoring_samples', (SELECT count(*) FROM monitoring_samples),
      'schema', (SELECT version_num FROM alembic_version)
    );
  " \
  > "${work_dir}/database-counts.json"

{
  printf 'created_at=%s\n' "${timestamp}"
  printf 'app_version=%s\n' "${APP_VERSION:-unknown}"
  printf 'database=%s\n' "${PGDATABASE}"
  printf 'file_count=%s\n' "$(find /data -type f | wc -l | tr -d ' ')"
} > "${work_dir}/backup-metadata.txt"

(
  cd /data
  find . -type f -print0 \
    | sort -z \
    | xargs -0 -r sha256sum \
    > "${work_dir}/files.sha256"
)

(
  cd "${work_dir}"
  sha256sum \
    database.dump \
    files.tar \
    database-counts.json \
    backup-metadata.txt \
    files.sha256 \
    > archive.sha256
)

tar \
  --create \
  --file=- \
  --directory="${work_dir}" \
  . \
  | age \
      --recipient "${BACKUP_AGE_RECIPIENT}" \
      --output="${daily_dir}/${backup_name}.tar.age"

(
  cd "${daily_dir}"
  sha256sum "${backup_name}.tar.age" \
    > "${backup_name}.tar.age.sha256"
)

if [[ "$(date -u +%u)" == "7" || "${force_weekly}" == "1" ]]; then
  cp --preserve=timestamps \
    "${daily_dir}/${backup_name}.tar.age" \
    "${weekly_dir}/${backup_name}.tar.age"
  (
    cd "${weekly_dir}"
    sha256sum "${backup_name}.tar.age" \
      > "${backup_name}.tar.age.sha256"
  )
fi

find "${daily_dir}" -type f -mtime "+${daily_days}" -delete
find "${weekly_dir}" -type f -mtime "+${weekly_days}" -delete

backup_completed=1
printf 'backup_completed file=%s\n' "${daily_dir}/${backup_name}.tar.age"
