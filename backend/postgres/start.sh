#!/bin/sh
set -eu

BOOTSTRAP_READY_FILE=/tmp/geo-saas-bootstrap-ready
MAX_BOOTSTRAP_ATTEMPTS=90

fail() {
  echo "database bootstrap refused: $1" >&2
  exit 1
}

is_weak_password() {
  [ "${#1}" -lt 16 ] && return 0
  normalized_password=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
  case "$normalized_password" in
    "" | changeme | geo_app_dev | geo_migrator_dev | password | postgres | postgres_dev)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

validate_environment() {
  : "${APP_ENV:?APP_ENV is required}"
  : "${POSTGRES_USER:?POSTGRES_USER is required}"
  : "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
  : "${POSTGRES_DB:?POSTGRES_DB is required}"
  : "${GEO_APP_USER:?GEO_APP_USER is required}"
  : "${GEO_APP_PASSWORD:?GEO_APP_PASSWORD is required}"
  : "${GEO_MIGRATION_USER:?GEO_MIGRATION_USER is required}"
  : "${GEO_MIGRATION_PASSWORD:?GEO_MIGRATION_PASSWORD is required}"

  case "$APP_ENV" in
    development | test | production) ;;
    *) fail "APP_ENV must be development, test, or production" ;;
  esac

  [ "$GEO_APP_USER" != "$GEO_MIGRATION_USER" ] \
    || fail "runtime and migration users must be different"

  if [ "$APP_ENV" = "production" ]; then
    is_weak_password "$POSTGRES_PASSWORD" \
      && fail "production requires a strong administrator password"
    is_weak_password "$GEO_APP_PASSWORD" \
      && fail "production requires a strong runtime password"
    is_weak_password "$GEO_MIGRATION_PASSWORD" \
      && fail "production requires a strong migration password"
  fi

  # A strong final password makes is_weak_password return 1. Return success
  # explicitly so `set -e` does not mistake the successful validation for a
  # startup failure.
  return 0
}

stop_postgres() {
  kill -TERM "$postgres_pid" 2>/dev/null || true
  wait "$postgres_pid" || true
}

validate_environment
rm -f "$BOOTSTRAP_READY_FILE"

/usr/local/bin/docker-entrypoint.sh "$@" &
postgres_pid=$!
trap stop_postgres INT TERM

attempt=1
while [ "$attempt" -le "$MAX_BOOTSTRAP_ATTEMPTS" ]; do
  if ! kill -0 "$postgres_pid" 2>/dev/null; then
    wait "$postgres_pid"
    fail "postgres exited before bootstrap completed"
  fi

  if pg_isready \
    --host 127.0.0.1 \
    --port 5432 \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" >/dev/null 2>&1 \
    && sh /usr/local/bin/geo-saas-bootstrap-roles.sh; then
    touch "$BOOTSTRAP_READY_FILE"
    break
  fi

  attempt=$((attempt + 1))
  sleep 1
done

if [ ! -f "$BOOTSTRAP_READY_FILE" ]; then
  stop_postgres
  fail "roles, grants, or administrator password rotation could not be applied"
fi

wait "$postgres_pid"
