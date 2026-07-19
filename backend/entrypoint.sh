#!/bin/sh
# Waits for PostgreSQL to accept connections before running the container's
# main command (e.g. `manage.py runserver`). Uses pg_isready instead of a
# fixed sleep so startup time adapts to how long postgres actually takes.
set -e

: "${POSTGRES_HOST:=postgres}"
: "${POSTGRES_PORT:=5432}"
: "${POSTGRES_USER:=postgres}"

echo "Waiting for PostgreSQL at ${POSTGRES_HOST}:${POSTGRES_PORT}..."

until pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -q; do
  sleep 1
done

echo "PostgreSQL is ready."

exec "$@"
