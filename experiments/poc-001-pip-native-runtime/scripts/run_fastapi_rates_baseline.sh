#!/usr/bin/env sh
set -eu

container="${SILTA_POSTGRES_CONTAINER:-fpcurhub-postgres-1}"
host="${SILTA_POSTGRES_HOST:-127.0.0.1}"
port="${SILTA_POSTGRES_PORT:-5432}"

pg_user="$(docker exec "$container" printenv POSTGRES_USER)"
pg_password="$(docker exec "$container" printenv POSTGRES_PASSWORD)"
pg_db="$(docker exec "$container" printenv POSTGRES_DB)"

export DATABASE_URL="postgresql://${pg_user}:${pg_password}@${host}:${port}/${pg_db}"

exec .venv/bin/python -m uvicorn baselines.fastapi_db_app:app \
  --host 127.0.0.1 \
  --port "${FASTAPI_PORT:-8103}" \
  --loop uvloop \
  --http httptools \
  --no-access-log
