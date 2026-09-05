#!/usr/bin/env bash
# Seed the local ClickHouse used by the experimental /ch/* routes.
#
# Creates database silta_poc and table rates with the same shape and the same
# 250,000 synthetic rows as the PostgreSQL compose seed (5 pairs x 50,000
# observations), so the two database paths return comparable payloads.
set -euo pipefail

CLICKHOUSE_URL="${CLICKHOUSE_URL:-http://127.0.0.1:8123}"
CLICKHOUSE_DATABASE="${CLICKHOUSE_DATABASE:-silta_poc}"

ch() {
  curl -sS --fail-with-body "$CLICKHOUSE_URL/" --data-binary "$1"
}

ch "CREATE DATABASE IF NOT EXISTS ${CLICKHOUSE_DATABASE}"
ch "CREATE TABLE IF NOT EXISTS ${CLICKHOUSE_DATABASE}.rates (
    id UInt64,
    rate_type LowCardinality(String),
    asset_class LowCardinality(String),
    base LowCardinality(String),
    quote LowCardinality(String),
    rate Decimal(18, 8),
    ts_utc DateTime64(6, 'UTC'),
    source LowCardinality(String)
) ENGINE = MergeTree ORDER BY (ts_utc, base, quote)"

existing="$(ch "SELECT count() FROM ${CLICKHOUSE_DATABASE}.rates WHERE source = 'silta-poc-seed'")"
if [[ "$existing" -gt 0 ]]; then
  echo "clickhouse seed present: $existing rows in ${CLICKHOUSE_DATABASE}.rates"
  exit 0
fi

ch "INSERT INTO ${CLICKHOUSE_DATABASE}.rates
SELECT
    number + 1 AS id,
    'spot' AS rate_type,
    'fiat' AS asset_class,
    pair.1 AS base,
    pair.2 AS quote,
    toDecimal64(pair.3, 8) + toDecimal64((number % 1000) / 100000, 8) AS rate,
    now64(6) - toIntervalSecond(number) AS ts_utc,
    'silta-poc-seed' AS source
FROM numbers(50000)
ARRAY JOIN
    [('EUR', 'USD', 1.08), ('USD', 'EUR', 0.925), ('GBP', 'USD', 1.27), ('USD', 'JPY', 146.5), ('BTC', 'USD', 65000.0)] AS pair"

ch "OPTIMIZE TABLE ${CLICKHOUSE_DATABASE}.rates FINAL"
echo "clickhouse seed complete: $(ch "SELECT count() FROM ${CLICKHOUSE_DATABASE}.rates") rows in ${CLICKHOUSE_DATABASE}.rates"
