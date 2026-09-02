#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${POSTGRES_CONTAINER:-fpcurhub-postgres-1}"

POSTGRES_USER="$(docker exec "$CONTAINER_NAME" printenv POSTGRES_USER)"
POSTGRES_DB="$(docker exec "$CONTAINER_NAME" printenv POSTGRES_DB)"

docker exec -i "$CONTAINER_NAME" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<'SQL'
SHOW max_connections;
SHOW shared_buffers;
SHOW effective_cache_size;
SHOW work_mem;
SHOW maintenance_work_mem;
SHOW checkpoint_completion_target;
SHOW wal_buffers;
SHOW random_page_cost;

SELECT count(*) AS active_connections FROM pg_stat_activity;
SELECT state, wait_event_type, wait_event, count(*)
FROM pg_stat_activity
GROUP BY 1, 2, 3
ORDER BY count(*) DESC;
SQL
