#!/bin/bash
set -e

# Create databases for business services
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    CREATE DATABASE procurement;
    CREATE DATABASE asset;
    CREATE DATABASE project;
    GRANT ALL PRIVILEGES ON DATABASE procurement TO $POSTGRES_USER;
    GRANT ALL PRIVILEGES ON DATABASE asset TO $POSTGRES_USER;
    GRANT ALL PRIVILEGES ON DATABASE project TO $POSTGRES_USER;
EOSQL
