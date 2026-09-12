#!/bin/sh
# Second database for `uv run pytest`; the integration tests need a real
# PostgreSQL and must not touch the development data.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-SQL
    CREATE DATABASE app_test;
SQL
