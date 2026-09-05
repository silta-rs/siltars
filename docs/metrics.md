# Native Metrics Export

Silta records HTTP and Python-worker metrics in Rust. No Python instrumentation
package or handler decorator is required. Metrics are opt-in and support two
independent outputs: Prometheus text exposition and periodic OTLP/HTTP protobuf.
Both outputs can be enabled together and use the same OpenTelemetry meter.

## Prometheus: one flag

From the checkout, after installing the package and building the runtime as in
the [cookbook](cookbook.md):

```bash
uv run --no-project silta dev examples/cookbook/app.py:app \
  --runtime-bin ./target/debug/silta-runtime \
  --metrics-listen 127.0.0.1:9464
```

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:9464/metrics
```

The management listener is separate from the application port. It does not
reserve `/metrics` in the application or depend on a healthy Python worker.
Scrapes do not contribute to application request counts. The response content
type is `text/plain; version=0.0.4; charset=utf-8`.

A [Prometheus configuration](../examples/observability/prometheus.yml) is included:

```bash
prometheus --config.file=examples/observability/prometheus.yml
```

Use a reachable private management address for remote scraping. The metrics
listener has no built-in authentication or TLS: restrict it using the deployment
network or a management proxy. It is disabled unless an address is configured.
Do not expose it through the public application's ingress by default.

## OpenTelemetry: automatic background export

```bash
OTEL_SERVICE_NAME=orders-api \
OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://127.0.0.1:4318/v1/metrics \
uv run --no-project silta dev examples/cookbook/app.py:app \
  --runtime-bin ./target/debug/silta-runtime
```

This starts OTLP export without opening a management listener. To also inspect
export failures and worker gauges through Prometheus, add
`--metrics-listen 127.0.0.1:9464`.

The endpoint is the complete metrics URL. The generic
`OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318` is also supported; Silta
appends `/v1/metrics` to its URL path. A metrics-specific endpoint takes precedence
and is used as-is. Transport is **HTTP/protobuf**, not gRPC or JSON; use the
Collector's HTTP receiver (commonly port 4318).

The application sends real OTLP protobuf metrics. It does not forward HTTP
requests or Python request bodies to the Collector. Every runtime has a generated
`service.instance.id` UUID, plus `service.name` and `service.version`, so separate
runtime instances do not overwrite the same cumulative metric stream. Worker
restarts preserve that runtime's metric identity and counters.

If the Collector needs authentication, configure headers through
`OTEL_EXPORTER_OTLP_METRICS_HEADERS` or the generic `OTEL_EXPORTER_OTLP_HEADERS`,
using the OpenTelemetry exporter syntax. Prefer injecting credentials from the
deployment secret store. URI credentials are rejected; redirects are not followed.
HTTPS uses the Rustls trust roots. Custom client certificates and custom CA
configuration are not exposed in this increment.

## Local Collector recipe

The included [Collector configuration](../examples/observability/collector.yml)
receives OTLP/HTTP on `127.0.0.1:4318` and exposes received metrics for inspection
on `127.0.0.1:9465/metrics`:

```bash
otelcol-contrib --config=examples/observability/collector.yml
```

Start the Silta command above, make a few HTTP requests, wait for the export
interval, then inspect:

```bash
curl http://127.0.0.1:9465/metrics
```

Run these processes in the same network namespace for the loopback addresses
to work. For containers, configure addresses appropriate to the container network.
Silta does not install or manage the Collector, Prometheus, or Grafana. Point an
existing Grafana Prometheus data source at your Prometheus server.

The recipe uses standard Collector
[configuration](https://opentelemetry.io/docs/collector/configuration/) and the
[Prometheus exporter](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/exporter/prometheusexporter/README.md).
The tests use controlled Collector-compatible receivers to inspect protobuf and
simulate failure; they do not launch a Collector distribution.

## Configuration reference

| CLI flag | Environment variable | Default / valid range |
| --- | --- | --- |
| `--metrics-listen` | `SILTA_METRICS_LISTEN` | Disabled; IP address and port |
| `--otlp-metrics-endpoint` | `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` | Disabled; complete HTTP(S) metrics URL |
| — | `OTEL_EXPORTER_OTLP_ENDPOINT` | Fallback base URL; `/v1/metrics` appended |
| `--service-name` | `OTEL_SERVICE_NAME` | Application name; explicit value: 1–256 bytes, no control characters |
| `--metrics-export-interval-ms` | `OTEL_METRIC_EXPORT_INTERVAL` | 15000 ms; 100–3600000 ms |
| `--metrics-export-timeout-ms` | `OTEL_METRIC_EXPORT_TIMEOUT` | 2000 ms; 10–5000 ms |
| — | `OTEL_EXPORTER_OTLP_METRICS_HEADERS` / `OTEL_EXPORTER_OTLP_HEADERS` | Optional Collector authentication/metadata headers |

CLI options override parsed environment defaults. Malformed environment values
fail startup even if an override is supplied. Setting only a service name or
interval does not enable metrics. Other OpenTelemetry environment options are
not part of Silta's configuration contract; transport and cumulative temporality
are selected explicitly by the runtime.

The Rust embedding API exposes the same settings in `RuntimeConfig.metrics`
(`MetricsConfig`). There is no global meter-provider replacement, so runtime
instances and other embedded OpenTelemetry users remain isolated.

## Exported instruments

Names below are for Silta's native Prometheus endpoint. OTLP counters omit the
Prometheus `_total` suffix. Histograms include `_bucket`, `_sum`, and `_count`.

| Instrument | Type | Labels / meaning |
| --- | --- | --- |
| `silta_http_requests_total` | Counter | `method`, `route`, `execution`, `status` |
| `silta_http_request_duration_seconds` | Histogram | `method`, `route`, `execution` |
| `silta_http_requests_in_flight` | Gauge | Requests before response creation |
| `silta_python_worker_starts_total` | Counter | Successful process spawns, including initial startup |
| `silta_python_worker_restarts_total` | Counter | Worker invalidations scheduling recovery, by `reason` |
| `silta_python_worker_spawn_failures_total` | Counter | Failed replacement spawn attempts |
| `silta_python_worker_ready` | Gauge | 1 after readiness handshake; 0 while unavailable |
| `silta_python_worker_busy` | Gauge | Active IPC execution, excluding reaping |
| `silta_python_queue_depth` | Gauge | Accepted envelopes retained in the waiting queue |
| `silta_python_queue_wait_seconds` | Histogram | Enqueue through dispatch or queue disposal |
| `silta_python_execution_duration_seconds` | Histogram | IPC execution time by `outcome`, excluding cleanup |
| `silta_python_calls_total` | Counter | Dispatched calls by `outcome` |
| `silta_python_requests_rejected_total` | Counter | Rejected/skipped requests by `reason` |
| `silta_metrics_exports_total` | Counter | OTLP attempts by `outcome`: success, failure, partial |
| `silta_metrics_rejected_data_points_total` | Counter | Collector-reported partial rejection count |
| `target_info` | Gauge | Service resource metadata on Prometheus scrapes |

HTTP `execution` is `native`, `python`, or `unmatched`. Status is the response
code, or `cancelled` when the HTTP task is dropped before creating a response.
Cancellation is not presented as an HTTP code sent to the client. `504` is counted
once by the outer HTTP observer; Python timeout/restart counters describe the
same event at a different layer.

Restart reasons are `idle_exit`, `startup_error`, `startup_timeout`, `eof`,
`protocol_error`, `io_error`, `timeout`, and `cancelled`. Dispatched-call outcomes
also include `success`, `handler_error`, and `shutdown`. Rejection reasons are
`queue_full`, `shutdown`, `queue_timeout`, and `queue_cancelled`. Valid Python
error replies increment `handler_error` without restarting a healthy worker.
Queued envelopes cancelled during recovery remain part of queue depth until
the supervisor removes them; depth measures retained queue capacity.

Duration ends at response creation, matching the current request-deadline
contract. It excludes initial header receipt and response-body transmission.
Concurrent scrapes are snapshots, not an atomic transaction across all gauges.
Counters persist across Python restarts and reset with the Rust runtime.
Unobserved label combinations may be absent instead of explicitly zero.

## Cardinality and overhead

Routes use declared templates such as `/items/{item_id}`. Unknown paths and
unmatched methods use `__unmatched__`; nonstandard methods are grouped as `OTHER`.
Raw URLs, query strings, filenames, request IDs, and body content are not labels.
The pinned OpenTelemetry SDK also limits each metric stream to 2000 attribute
sets before aggregating into its overflow series.

Request processing only updates in-process metric aggregates. A dedicated SDK
reader thread periodically serializes and sends cumulative snapshots. There is
no per-request export queue. Failed snapshots are not accumulated in memory;
a later successful cumulative export includes counts accrued during an outage.
Gauge history and intermediate time resolution cannot be recovered this way.
There is no durable export spool and no immediate retry loop.

Collector requests have a total timeout, replies are capped at 64 KiB, and HTTP
errors, malformed protobuf, and oversized replies count as failures. A 200 reply
with rejected data points or a partial-success warning counts as `partial`, not
`success`. Collector-controlled error text is not logged. Export-health counters
appear in the next export; the independent scrape endpoint can expose them while
OTLP is unavailable.

Prometheus encoding runs on a blocking pool with at most two concurrent scrape
jobs; excess concurrent jobs return 503 instead of creating an unbounded queue.
Slow scrapers do not own the Python bridge. Shutdown first reaps Python and then
stops the metrics listener and flushes/shuts down the metric provider. It can add
up to roughly six seconds to shutdown when export or scrapes are stalled, on top
of the application drain period. No telemetry is guaranteed after SIGKILL.

A reproducible local [overhead smoke comparison](../experiments/metrics-export/README.md)
is included. It does not establish a production throughput limit or zero overhead.

## Example PromQL

Request rate by route:

```promql
sum by (route) (rate(silta_http_requests_total[5m]))
```

p95 response-creation latency:

```promql
histogram_quantile(0.95,
  sum by (le, route) (rate(silta_http_request_duration_seconds_bucket[5m])))
```

Worker restarts and export failures:

```promql
sum by (reason) (increase(silta_python_worker_restarts_total[5m]))
sum(increase(silta_metrics_exports_total{outcome="failure"}[5m]))
```

These examples target the native scrape format. Collector/backend name translation
can differ; inspect the resulting metric names before copying dashboard queries.

## Remaining observability work

Distributed traces, propagation of trace context through IPC, correlated log
export, automatic instrumentation inside arbitrary Python libraries, CPU/RSS
metrics, and a Python custom-business-metrics API remain separate increments.
The implemented feature is native framework **metrics** with working exporters.
