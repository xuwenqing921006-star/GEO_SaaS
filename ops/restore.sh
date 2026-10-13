#!/usr/bin/env bash
set -Eeuo pipefail

: "${PGHOST:?PGHOST is required}"
: "${PGDATABASE:?PGDATABASE is required}"
: "${PGUSER:?PGUSER is required}"
: "${PGPASSWORD:?PGPASSWORD is required}"
: "${BACKUP_FILE:?BACKUP_FILE is required}"
: "${AGE_IDENTITY_FILE:?AGE_IDENTITY_FILE is required}"

expected_confirmation="restore-${PGDATABASE}"
if [[ "${CONFIRM_RESTORE:-}" != "${expected_confirmation}" ]]; then
  printf 'restore_refused expected_confirmation=%s\n' "${expected_confirmation}" >&2
  exit 2
fi
if [[ "${BACKUP_FILE}" != /backups/*.tar.age ]]; then
  printf 'restore_refused backup_must_be_under_/backups\n' >&2
  exit 2
fi
if [[ ! -f "${BACKUP_FILE}" || ! -f "${BACKUP_FILE}.sha256" ]]; then
  printf 'restore_refused backup_or_checksum_missing\n' >&2
  exit 2
fi
if [[ ! -r "${AGE_IDENTITY_FILE}" ]]; then
  printf 'restore_refused_age_identity_missing\n' >&2
  exit 2
fi
if [[ "$(readlink -f /data)" != "/data" ]]; then
  printf 'restore_refused_unexpected_data_mount\n' >&2
  exit 2
fi

work_dir="/work/restore-$(date -u +%Y%m%dT%H%M%SZ)"
archive_path="${work_dir}/archive.tar"
payload_dir="${work_dir}/payload"
restored_files="${work_dir}/restored-files"
previous_files="${work_dir}/previous-files.tar"
previous_database="${work_dir}/previous-database.dump"
files_replaced=0
database_replaced=0
mkdir -p "${payload_dir}" "${restored_files}"

cleanup() {
  exit_code=$?
  if [[ "${files_replaced}" == "1" && -f "${previous_files}" ]]; then
    find /data -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
    tar \
      --extract \
      --no-same-owner \
      --no-overwrite-dir \
      --file="${previous_files}" \
      --directory=/data
    chown -R 10001:10001 /data
    printf 'restore_rolled_back_files\n' >&2
  fi
  if [[ "${exit_code}" != "0" && "${database_replaced}" == "1" && -f "${previous_database}" ]]; then
    if pg_restore \
      --clean \
      --if-exists \
      --single-transaction \
      --no-owner \
      --no-privileges \
      --exit-on-error \
      --dbname="${PGDATABASE}" \
      "${previous_database}"; then
      printf 'restore_rolled_back_database\n' >&2
    else
      printf 'restore_database_rollback_failed_manual_recovery_required\n' >&2
    fi
  fi
  rm -rf -- "${work_dir}"
  exit "${exit_code}"
}
trap cleanup EXIT

(
  cd "$(dirname "${BACKUP_FILE}")"
  sha256sum --check "$(basename "${BACKUP_FILE}").sha256"
)

age \
  --decrypt \
  --identity "${AGE_IDENTITY_FILE}" \
  --output "${archive_path}" \
  "${BACKUP_FILE}"

tar \
  --extract \
  --no-same-owner \
  --file="${archive_path}" \
  --directory="${payload_dir}"
(
  cd "${payload_dir}"
  sha256sum --check archive.sha256
)

tar \
  --extract \
  --no-same-owner \
  --file="${payload_dir}/files.tar" \
  --directory="${restored_files}"
(
  cd "${restored_files}"
  sha256sum --check "${payload_dir}/files.sha256"
)

pg_dump \
  --format=custom \
  --no-owner \
  --no-privileges \
  --file="${previous_database}" \
  "${PGDATABASE}"

pg_restore \
  --clean \
  --if-exists \
  --single-transaction \
  --no-owner \
  --no-privileges \
  --exit-on-error \
  --dbname="${PGDATABASE}" \
  "${payload_dir}/database.dump"
database_replaced=1

actual_counts="$(
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
    "
)"
if [[ "$(tr -d '[:space:]' <<<"${actual_counts}")" != "$(
  tr -d '[:space:]' < "${payload_dir}/database-counts.json"
)" ]]; then
  printf 'restore_failed_database_counts_mismatch\n' >&2
  exit 1
fi

tar --create --file="${previous_files}" --directory=/data .
files_replaced=1
find /data -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
cp -R "${restored_files}/." /data/
chown -R 10001:10001 /data

(
  cd /data
  sha256sum --check "${payload_dir}/files.sha256"
)
files_replaced=0
database_replaced=0

printf 'restore_completed backup=%s\n' "${BACKUP_FILE}"
