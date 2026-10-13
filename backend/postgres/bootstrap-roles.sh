#!/bin/sh
set -eu

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${GEO_APP_USER:?GEO_APP_USER is required}"
: "${GEO_APP_PASSWORD:?GEO_APP_PASSWORD is required}"
: "${GEO_MIGRATION_USER:?GEO_MIGRATION_USER is required}"
: "${GEO_MIGRATION_PASSWORD:?GEO_MIGRATION_PASSWORD is required}"

psql \
  --set=ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" <<'SQL'
\getenv admin_user POSTGRES_USER
\getenv admin_password POSTGRES_PASSWORD
\getenv database_name POSTGRES_DB
\getenv app_user GEO_APP_USER
\getenv app_password GEO_APP_PASSWORD
\getenv migration_user GEO_MIGRATION_USER
\getenv migration_password GEO_MIGRATION_PASSWORD

ALTER ROLE :"admin_user" WITH LOGIN PASSWORD :'admin_password';

SELECT format(
  'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION PASSWORD %L',
  :'migration_user',
  :'migration_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'migration_user')
\gexec

SELECT format(
  'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION PASSWORD %L',
  :'app_user',
  :'app_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user')
\gexec

ALTER ROLE :"migration_user"
  WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION
  PASSWORD :'migration_password';
ALTER ROLE :"app_user"
  WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION
  PASSWORD :'app_password';

REVOKE CREATE, TEMPORARY ON DATABASE :"database_name" FROM PUBLIC;
REVOKE CREATE, TEMPORARY ON DATABASE :"database_name" FROM :"app_user";
GRANT CONNECT ON DATABASE :"database_name" TO :"migration_user", :"app_user";

ALTER SCHEMA public OWNER TO :"migration_user";
REASSIGN OWNED BY :"app_user" TO :"migration_user";
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM :"app_user";
GRANT USAGE ON SCHEMA public TO :"app_user";
GRANT USAGE, CREATE ON SCHEMA public TO :"migration_user";

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"app_user";
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO :"app_user";

ALTER DEFAULT PRIVILEGES FOR ROLE :"migration_user" IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_user";
ALTER DEFAULT PRIVILEGES FOR ROLE :"migration_user" IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO :"app_user";
SQL
