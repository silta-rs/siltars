#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${POSTGRES_CONTAINER:-silta-poc-postgres}"
MAX_CONNECTIONS="${POSTGRES_MAX_CONNECTIONS:-200}"
SHARED_BUFFERS="${POSTGRES_SHARED_BUFFERS:-512MB}"
EFFECTIVE_CACHE_SIZE="${POSTGRES_EFFECTIVE_CACHE_SIZE:-2GB}"
WORK_MEM="${POSTGRES_WORK_MEM:-16MB}"
MAINTENANCE_WORK_MEM="${POSTGRES_MAINTENANCE_WORK_MEM:-256MB}"
WAL_BUFFERS="${POSTGRES_WAL_BUFFERS:-16MB}"
RANDOM_PAGE_COST="${POSTGRES_RANDOM_PAGE_COST:-1.1}"

POSTGRES_USER="$(docker exec "$CONTAINER_NAME" printenv POSTGRES_USER)"
POSTGRES_DB="$(docker exec "$CONTAINER_NAME" printenv POSTGRES_DB)"

cat <<EOF
Target container: $CONTAINER_NAME

Planned local benchmark tuning:
  max_connections = $MAX_CONNECTIONS
  shared_buffers = $SHARED_BUFFERS
  effective_cache_size = $EFFECTIVE_CACHE_SIZE
  work_mem = $WORK_MEM
  maintenance_work_mem = $MAINTENANCE_WORK_MEM
  checkpoint_completion_target = 0.9
  wal_buffers = $WAL_BUFFERS
  random_page_cost = $RANDOM_PAGE_COST

This script changes PostgreSQL server settings with ALTER SYSTEM and restarts
the Docker container. Run with APPLY=1 to apply.
EOF

if [[ "${APPLY:-0}" != "1" ]]; then
  exit 0
fi

docker exec -i "$CONTAINER_NAME" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<SQL
ALTER SYSTEM SET max_connections = '$MAX_CONNECTIONS';
ALTER SYSTEM SET shared_buffers = '$SHARED_BUFFERS';
ALTER SYSTEM SET effective_cache_size = '$EFFECTIVE_CACHE_SIZE';
ALTER SYSTEM SET work_mem = '$WORK_MEM';
ALTER SYSTEM SET maintenance_work_mem = '$MAINTENANCE_WORK_MEM';
ALTER SYSTEM SET checkpoint_completion_target = '0.9';
ALTER SYSTEM SET wal_buffers = '$WAL_BUFFERS';
ALTER SYSTEM SET random_page_cost = '$RANDOM_PAGE_COST';
SQL

docker restart "$CONTAINER_NAME" >/dev/null

until docker exec "$CONTAINER_NAME" pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null; do
  sleep 1
done

docker exec -i "$CONTAINER_NAME" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<'SQL'
SHOW max_connections;
SHOW shared_buffers;
SHOW effective_cache_size;
SHOW work_mem;
SHOW maintenance_work_mem;
SHOW checkpoint_completion_target;
SHOW wal_buffers;
SHOW random_page_cost;
SQL
