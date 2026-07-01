#!/usr/bin/env bash
# 10-temporal.sh — create the Temporal role + databases on fresh postgres-ext.
#
# temporalio/auto-setup:1.27.0 connects as user "temporal" (password
# "temporal_password", see docker-compose.temporal.yaml) and expects the
# `temporal` + `temporal_visibility` databases to exist. A freshly init'd
# postgres-ext only has the agentflow user, so without this script Temporal
# crash-loops on first boot (docs/OFFLINE_DEPLOYMENT_GUIDE.md §F.3).
#
# Runs once during postgres first-init (empty data dir). Idempotent guards
# so re-running on a preserved volume is safe.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  DO \$do\$
  BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'temporal') THEN
      CREATE ROLE temporal WITH LOGIN SUPERUSER PASSWORD 'temporal_password';
      RAISE NOTICE 'Created role temporal';
    ELSE
      RAISE NOTICE 'Role temporal already exists';
    END IF;
  END
  \$do\$;

  -- CREATE DATABASE cannot run inside a transaction / DO block; \gexec runs
  -- the generated statement at top level.
  SELECT 'CREATE DATABASE temporal OWNER temporal'
  WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'temporal')\gexec
  SELECT 'CREATE DATABASE temporal_visibility OWNER temporal'
  WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'temporal_visibility')\gexec
EOSQL

echo "10-temporal.sh: temporal role + databases ready."
