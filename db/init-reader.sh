#!/bin/sh
set -eu

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=reader_password="$ANALYTICS_READ_PASSWORD" <<'EOSQL'
SELECT format('CREATE ROLE analytics_reader LOGIN PASSWORD %L', :'reader_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'analytics_reader') \gexec
SELECT format('ALTER ROLE analytics_reader PASSWORD %L', :'reader_password') \gexec

CREATE SCHEMA IF NOT EXISTS analytics AUTHORIZATION analytics_owner;
CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION analytics_owner;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
SELECT format('GRANT CONNECT ON DATABASE %I TO analytics_reader', current_database()) \gexec
GRANT USAGE ON SCHEMA analytics TO analytics_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE analytics_owner IN SCHEMA analytics
  GRANT SELECT ON TABLES TO analytics_reader;
ALTER ROLE analytics_reader SET default_transaction_read_only = on;
ALTER ROLE analytics_reader SET statement_timeout = '5s';
EOSQL
