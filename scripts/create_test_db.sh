#!/bin/bash
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE askit_test'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'askit_test')\gexec
    GRANT ALL PRIVILEGES ON DATABASE askit_test TO $POSTGRES_USER;
EOSQL
