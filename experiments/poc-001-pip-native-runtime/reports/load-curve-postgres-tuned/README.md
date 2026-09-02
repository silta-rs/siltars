# POC-001 Load Curve: Tuned PostgreSQL

This report compares Silta's native Rust runtime against FastAPI on the same
local PostgreSQL container after benchmark tuning.

## Environment

- PostgreSQL container: `fpcurhub-postgres-1`.
- PostgreSQL `max_connections`: `200`.
- PostgreSQL `shared_buffers`: `512MB`.
- PostgreSQL `wal_buffers`: `16MB`.
- PostgreSQL `random_page_cost`: `1.1`.
- Silta runtime: release build.
- Silta database pool: `SILTA_DB_MAX_CONNECTIONS=50`.
- FastAPI database pool: `FASTAPI_DB_MAX_CONNECTIONS=50`.
- Benchmark tool: `oha 1.16.0`.
- Requests per point: `5000`.
- Concurrency sweep: `1,10,25,50,100,200,400`.

## Charts

### Larger JSON Response

![Silta vs FastAPI /rates](rates.svg)

### Single Row PostgreSQL Response

![Silta vs FastAPI /rates/EUR/USD](rates-EUR-USD.svg)

### HTTP Runtime Overhead

![Silta vs FastAPI /ping](ping.svg)

## Raw Data

[load-curve.csv](load-curve.csv) contains the raw points used by the charts.

## Key Points

| Endpoint | Silta Best RPS | FastAPI Best RPS | Main Finding |
| --- | ---: | ---: | --- |
| `/ping` | 133,413 | 48,662 | Silta has much lower HTTP/runtime overhead. |
| `/rates/EUR/USD` | 15,753 | 11,958 | Silta leads after PostgreSQL tuning; FastAPI p95 grows faster at high concurrency. |
| `/rates` | 9,652 | 3,873 | Silta is materially faster for larger JSON responses. |

This is a local POC result, not a public production claim. The important signal
is the load-curve shape: at higher concurrency, FastAPI response times rise
faster on the larger database-backed JSON endpoint.
