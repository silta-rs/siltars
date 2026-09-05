//! Per-runtime OpenTelemetry meters. Export never runs on the HTTP request path.
use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::Arc;
use std::time::Duration;

use axum::extract::{MatchedPath, Request, State};
use axum::http::{header, StatusCode};
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use axum::Router;
use opentelemetry::metrics::{Counter, Gauge, Histogram, MeterProvider, UpDownCounter};
use opentelemetry::KeyValue;
use opentelemetry_otlp::{Protocol, WithExportConfig, WithHttpConfig};
use opentelemetry_sdk::metrics::{PeriodicReader, SdkMeterProvider, Temporality};
use opentelemetry_sdk::Resource;
use prometheus::{Encoder, Registry, TextEncoder};
use tokio::net::TcpListener;
use tokio::sync::{oneshot, Semaphore};
use tokio::task::JoinHandle;
use tokio::time::Instant;

use super::{axum_path, RuntimeError};
use silta_core::Application;

mod transport;

/// Metrics are opt-in. A scrape address and/or an OTLP endpoint enable recording.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MetricsConfig {
    /// Separate management listener; e.g. 127.0.0.1:9464. No public app route is reserved.
    pub listen: Option<SocketAddr>,
    /// Complete OTLP/HTTP protobuf metrics URL, including /v1/metrics.
    pub otlp_endpoint: Option<String>,
    /// OpenTelemetry service.name; otherwise the application name.
    pub service_name: Option<String>,
    /// Interval between cumulative exports.
    pub export_interval: Duration,
    /// Total time allowed per Collector HTTP request.
    pub export_timeout: Duration,
}

impl Default for MetricsConfig {
    fn default() -> Self {
        Self {
            listen: None,
            otlp_endpoint: None,
            service_name: None,
            export_interval: Duration::from_secs(15),
            export_timeout: Duration::from_secs(2),
        }
    }
}

impl MetricsConfig {
    pub(crate) fn validate(&self) -> Result<(), RuntimeError> {
        if let Some(endpoint) = &self.otlp_endpoint {
            let url = reqwest::Url::parse(endpoint)
                .map_err(|_| config_error("OTLP endpoint must be an absolute HTTP(S) URL"))?;
            if !matches!(url.scheme(), "http" | "https")
                || url.host_str().is_none()
                || !url.username().is_empty()
                || url.password().is_some()
                || url.fragment().is_some()
            {
                return Err(config_error(
                    "OTLP endpoint must use HTTP(S), without credentials or fragment",
                ));
            }
        }
        if self.service_name.as_ref().is_some_and(|name| {
            name.trim().is_empty() || name.len() > 256 || name.chars().any(char::is_control)
        }) {
            return Err(config_error(
                "metrics service name must contain 1–256 bytes without control characters",
            ));
        }
        if !(Duration::from_millis(100)..=Duration::from_secs(3600)).contains(&self.export_interval)
        {
            return Err(config_error(
                "metrics export interval must be 100–3600000 ms",
            ));
        }
        if !(Duration::from_millis(10)..=Duration::from_secs(5)).contains(&self.export_timeout) {
            return Err(config_error("metrics export timeout must be 10–5000 ms"));
        }
        Ok(())
    }
}

fn config_error(message: &str) -> RuntimeError {
    RuntimeError::Metrics(message.to_owned())
}

#[derive(Debug, Clone)]
pub(super) struct Metrics {
    requests: Counter<u64>,
    duration: Histogram<f64>,
    in_flight: UpDownCounter<i64>,
    pub(super) worker_starts: Counter<u64>,
    pub(super) worker_restarts: Counter<u64>,
    pub(super) worker_spawn_failures: Counter<u64>,
    pub(super) worker_ready: Gauge<u64>,
    pub(super) worker_busy: UpDownCounter<i64>,
    pub(super) queue_depth: UpDownCounter<i64>,
    pub(super) queue_wait: Histogram<f64>,
    pub(super) worker_duration: Histogram<f64>,
    pub(super) worker_calls: Counter<u64>,
    pub(super) worker_rejected: Counter<u64>,
}

impl Metrics {
    fn new(provider: &SdkMeterProvider) -> Self {
        let meter = provider.meter("silta-runtime");
        let histogram = |name: &'static str, description: &'static str| {
            meter
                .f64_histogram(name)
                .with_description(description)
                .with_unit("s")
                .with_boundaries(vec![
                    0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
                    30.0, 60.0,
                ])
                .build()
        };
        let metrics = Self {
            requests: meter
                .u64_counter("silta_http_requests")
                .with_description("HTTP requests completed or cancelled before response creation")
                .build(),
            duration: histogram(
                "silta_http_request_duration_seconds",
                "Time from parsed HTTP headers through response creation or cancellation",
            ),
            in_flight: meter
                .i64_up_down_counter("silta_http_requests_in_flight")
                .build(),
            worker_starts: meter.u64_counter("silta_python_worker_starts").build(),
            worker_restarts: meter.u64_counter("silta_python_worker_restarts").build(),
            worker_spawn_failures: meter
                .u64_counter("silta_python_worker_spawn_failures")
                .build(),
            worker_ready: meter.u64_gauge("silta_python_worker_ready").build(),
            worker_busy: meter
                .i64_up_down_counter("silta_python_worker_busy")
                .build(),
            queue_depth: meter
                .i64_up_down_counter("silta_python_queue_depth")
                .build(),
            queue_wait: histogram(
                "silta_python_queue_wait_seconds",
                "Time queued before dispatch, expiry or queue disposal",
            ),
            worker_duration: histogram(
                "silta_python_execution_duration_seconds",
                "IPC execution time, excluding reaping and restart delay",
            ),
            worker_calls: meter.u64_counter("silta_python_calls").build(),
            worker_rejected: meter.u64_counter("silta_python_requests_rejected").build(),
        };
        metrics.worker_ready.record(0, &[]);
        metrics.in_flight.add(0, &[]);
        metrics.worker_busy.add(0, &[]);
        metrics.queue_depth.add(0, &[]);
        metrics
    }

    pub(super) fn restart(&self, reason: &'static str) {
        self.worker_ready.record(0, &[]);
        self.worker_restarts
            .add(1, &[KeyValue::new("reason", reason)]);
    }

    pub(super) fn rejected(&self, reason: &'static str) {
        self.worker_rejected
            .add(1, &[KeyValue::new("reason", reason)]);
    }
}

/// Balanced even when a request future is dropped by Hyper or a timeout layer.
#[derive(Debug)]
pub(super) struct GaugeGuard(Option<UpDownCounter<i64>>);
impl GaugeGuard {
    pub(super) fn new(counter: Option<&UpDownCounter<i64>>) -> Self {
        if let Some(counter) = counter {
            counter.add(1, &[]);
        }
        Self(counter.cloned())
    }
}
impl Drop for GaugeGuard {
    fn drop(&mut self) {
        if let Some(counter) = &self.0 {
            counter.add(-1, &[]);
        }
    }
}

#[derive(Debug)]
pub(super) struct QueueGuard {
    _depth: GaugeGuard,
    histogram: Option<Histogram<f64>>,
    start: Instant,
}
impl QueueGuard {
    pub(super) fn new(metrics: Option<&Metrics>) -> Self {
        Self {
            _depth: GaugeGuard::new(metrics.map(|m| &m.queue_depth)),
            histogram: metrics.map(|m| m.queue_wait.clone()),
            start: Instant::now(),
        }
    }
}
impl Drop for QueueGuard {
    fn drop(&mut self) {
        if let Some(histogram) = &self.histogram {
            histogram.record(self.start.elapsed().as_secs_f64(), &[]);
        }
    }
}

struct RequestGuard {
    metrics: Metrics,
    attributes: Vec<KeyValue>,
    start: Instant,
    status: Option<String>,
    _active: GaugeGuard,
}
impl Drop for RequestGuard {
    fn drop(&mut self) {
        self.metrics
            .duration
            .record(self.start.elapsed().as_secs_f64(), &self.attributes);
        self.attributes.push(KeyValue::new(
            "status",
            self.status.take().unwrap_or_else(|| "cancelled".to_owned()),
        ));
        self.metrics.requests.add(1, &self.attributes);
    }
}

type RouteLabels = HashMap<(String, String), (String, &'static str)>;

#[derive(Clone)]
pub(super) struct HttpMetrics {
    metrics: Metrics,
    // Keys use router-internal paths; values contain declared route templates.
    routes: Arc<RouteLabels>,
}
impl HttpMetrics {
    pub(super) fn new(metrics: Metrics, app: &Application) -> Result<Self, RuntimeError> {
        let mut routes = HashMap::new();
        for route in app.routes() {
            routes.insert(
                (
                    axum_path(route.path())?,
                    match route.method() {
                        silta_core::Method::Get => "GET",
                        silta_core::Method::Post => "POST",
                        silta_core::Method::Put => "PUT",
                        silta_core::Method::Patch => "PATCH",
                        silta_core::Method::Delete => "DELETE",
                        silta_core::Method::Head => "HEAD",
                        silta_core::Method::Options => "OPTIONS",
                    }
                    .to_owned(),
                ),
                (
                    route.path().to_owned(),
                    if route.python_handler() {
                        "python"
                    } else {
                        "native"
                    },
                ),
            );
        }
        Ok(Self {
            metrics,
            routes: Arc::new(routes),
        })
    }
}

pub(super) async fn observe(
    State(state): State<HttpMetrics>,
    request: Request,
    next: Next,
) -> Response {
    let method = match request.method().as_str() {
        "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | "HEAD" | "OPTIONS" | "CONNECT" | "TRACE" => {
            request.method().as_str()
        }
        _ => "OTHER",
    };
    let path = request
        .extensions()
        .get::<MatchedPath>()
        .map(MatchedPath::as_str)
        .unwrap_or("");
    let route = state
        .routes
        .get(&(path.to_owned(), method.to_owned()))
        .or_else(|| {
            (method == "HEAD")
                .then(|| state.routes.get(&(path.to_owned(), "GET".to_owned())))
                .flatten()
        });
    let (route, execution) = route
        .map(|(route, execution)| (route.as_str(), *execution))
        .unwrap_or(("__unmatched__", "unmatched"));
    let mut guard = RequestGuard {
        _active: GaugeGuard::new(Some(&state.metrics.in_flight)),
        metrics: state.metrics,
        start: Instant::now(),
        status: None,
        attributes: vec![
            KeyValue::new("method", method.to_owned()),
            KeyValue::new("route", route.to_owned()),
            KeyValue::new("execution", execution),
        ],
    };
    let response = next.run(request).await;
    guard.status = Some(response.status().as_u16().to_string());
    response
}

#[derive(Clone)]
struct ScrapeState {
    registry: Registry,
    permits: Arc<Semaphore>,
}
async fn scrape(State(state): State<ScrapeState>) -> Response {
    // Avoid unbounded blocking tasks when many scrapers arrive together.
    let Ok(permit) = state.permits.try_acquire_owned() else {
        return StatusCode::SERVICE_UNAVAILABLE.into_response();
    };
    let result = tokio::task::spawn_blocking(move || {
        let _permit = permit;
        let mut bytes = Vec::new();
        TextEncoder::new()
            .encode(&state.registry.gather(), &mut bytes)
            .map(|()| bytes)
    })
    .await;
    match result {
        Ok(Ok(bytes)) => (
            [(
                header::CONTENT_TYPE,
                "text/plain; version=0.0.4; charset=utf-8",
            )],
            bytes,
        )
            .into_response(),
        _ => StatusCode::INTERNAL_SERVER_ERROR.into_response(),
    }
}

pub(super) struct Telemetry {
    pub(super) metrics: Option<Metrics>,
    provider: Option<SdkMeterProvider>,
    stop: Option<oneshot::Sender<()>>,
    server: Option<JoinHandle<std::io::Result<()>>>,
}
impl Telemetry {
    pub(super) async fn start(
        config: &MetricsConfig,
        app_name: &str,
    ) -> Result<Self, RuntimeError> {
        config.validate()?;
        if config.listen.is_none() && config.otlp_endpoint.is_none() {
            return Ok(Self {
                metrics: None,
                provider: None,
                stop: None,
                server: None,
            });
        }
        // Bind before creating background export threads. Invalid config/bind
        // errors cannot leave a Python worker or telemetry exporter behind.
        let listener = match config.listen {
            Some(address) => Some(
                TcpListener::bind(address)
                    .await
                    .map_err(RuntimeError::Bind)?,
            ),
            None => None,
        };
        let config = config.clone();
        let service = config
            .service_name
            .clone()
            .unwrap_or_else(|| app_name.to_owned());
        let (provider, metrics, registry) =
            tokio::task::spawn_blocking(move || build_provider(&config, service))
                .await
                .map_err(|_| config_error("metrics initialization task failed"))??;
        let (stop, server) = if let Some(listener) = listener {
            let app = Router::new()
                .route("/metrics", get(scrape))
                .with_state(ScrapeState {
                    registry,
                    permits: Arc::new(Semaphore::new(2)),
                });
            let (stop, stopped) = oneshot::channel();
            let server = tokio::spawn(async move {
                axum::serve(listener, app)
                    .with_graceful_shutdown(async {
                        let _ = stopped.await;
                    })
                    .await
            });
            (Some(stop), Some(server))
        } else {
            (None, None)
        };
        Ok(Self {
            metrics: Some(metrics),
            provider: Some(provider),
            stop,
            server,
        })
    }

    pub(super) async fn shutdown(mut self) {
        if let Some(stop) = self.stop.take() {
            let _ = stop.send(());
        }
        if let Some(mut server) = self.server.take() {
            if tokio::time::timeout(Duration::from_secs(1), &mut server)
                .await
                .is_err()
            {
                server.abort();
                let _ = server.await;
            }
        }
        if let Some(provider) = self.provider.take() {
            // The dedicated reader thread and bounded HTTP transport make this
            // independent of Python and the Tokio async worker threads.
            let _ = tokio::task::spawn_blocking(move || provider.shutdown()).await;
        }
    }
}

fn build_provider(
    config: &MetricsConfig,
    service: String,
) -> Result<(SdkMeterProvider, Metrics, Registry), RuntimeError> {
    let registry = Registry::new();
    let resource = Resource::builder_empty()
        .with_attributes([
            KeyValue::new("service.name", service),
            KeyValue::new("service.instance.id", uuid::Uuid::new_v4().to_string()),
            KeyValue::new("service.version", env!("CARGO_PKG_VERSION")),
        ])
        .build();
    let mut builder = SdkMeterProvider::builder().with_resource(resource);
    if config.listen.is_some() {
        let exporter = opentelemetry_prometheus::exporter()
            .with_registry(registry.clone())
            .without_units()
            .without_scope_info()
            .build()
            .map_err(|_| config_error("Prometheus exporter initialization failed"))?;
        builder = builder.with_reader(exporter);
    }
    let stats = Arc::new(transport::ExportStats::default());
    if let Some(endpoint) = &config.otlp_endpoint {
        let client = transport::BoundedClient::new(config.export_timeout, stats.clone())?;
        let exporter = opentelemetry_otlp::MetricExporter::builder()
            .with_http()
            .with_http_client(client)
            .with_protocol(Protocol::HttpBinary)
            .with_endpoint(endpoint)
            .with_timeout(config.export_timeout)
            .with_temporality(Temporality::Cumulative)
            .build()
            .map_err(|_| {
                config_error("OTLP exporter initialization failed; check endpoint and OTEL headers")
            })?;
        builder = builder.with_reader(
            PeriodicReader::builder(exporter)
                .with_interval(config.export_interval)
                .build(),
        );
    }
    let provider = builder.build();
    if config.otlp_endpoint.is_some() {
        stats.register(&provider);
    }
    let metrics = Metrics::new(&provider);
    Ok((provider, metrics, registry))
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::Bytes;
    use axum::http::HeaderMap;
    use axum::routing::post;
    use opentelemetry_proto::tonic::collector::metrics::v1::{
        ExportMetricsPartialSuccess, ExportMetricsServiceRequest, ExportMetricsServiceResponse,
    };
    use opentelemetry_proto::tonic::metrics::v1::{metric::Data, number_data_point::Value};
    use prost::Message;
    use std::sync::{
        atomic::{AtomicUsize, Ordering},
        Mutex,
    };

    #[derive(Default)]
    struct Collector {
        mode: AtomicUsize,
        received: Mutex<Vec<ExportMetricsServiceRequest>>,
    }
    async fn collect(
        State(state): State<Arc<Collector>>,
        headers: HeaderMap,
        body: Bytes,
    ) -> Response {
        assert_eq!(headers[header::CONTENT_TYPE], "application/x-protobuf");
        state
            .received
            .lock()
            .unwrap()
            .push(ExportMetricsServiceRequest::decode(body).unwrap());
        match state.mode.load(Ordering::Relaxed) {
            1 => StatusCode::SERVICE_UNAVAILABLE.into_response(),
            2 => {
                let reply = ExportMetricsServiceResponse {
                    partial_success: Some(ExportMetricsPartialSuccess {
                        rejected_data_points: 3,
                        error_message: "test partial rejection".into(),
                    }),
                };
                reply.encode_to_vec().into_response()
            }
            3 => b"invalid protobuf".to_vec().into_response(),
            4 => vec![0u8; 65537].into_response(),
            5 => {
                tokio::time::sleep(Duration::from_secs(2)).await;
                StatusCode::OK.into_response()
            }
            6 => (
                StatusCode::TEMPORARY_REDIRECT,
                [(header::LOCATION, "/redirect-target")],
            )
                .into_response(),
            _ => Bytes::new().into_response(),
        }
    }

    #[tokio::test]
    async fn otlp_protobuf_is_cumulative_and_collector_failures_are_observable() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let collector = Arc::new(Collector::default());
        let app = Router::new()
            .route("/v1/metrics", post(collect))
            .with_state(collector.clone());
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        let config = MetricsConfig {
            listen: Some("127.0.0.1:0".parse().unwrap()),
            otlp_endpoint: Some(format!("http://{address}/v1/metrics")),
            service_name: Some("metrics-test".into()),
            export_interval: Duration::from_secs(3600),
            export_timeout: Duration::from_millis(100),
        };
        let telemetry = Telemetry::start(&config, "ignored").await.unwrap();
        let metrics = telemetry.metrics.as_ref().unwrap();
        let provider = telemetry.provider.as_ref().unwrap().clone();
        metrics
            .requests
            .add(2, &[KeyValue::new("route", "/orders/{id}")]);
        let flush = |provider: SdkMeterProvider| {
            tokio::task::spawn_blocking(move || provider.force_flush())
        };
        flush(provider.clone()).await.unwrap().unwrap();
        metrics
            .requests
            .add(1, &[KeyValue::new("route", "/orders/{id}")]);
        flush(provider.clone()).await.unwrap().unwrap();
        {
            let requests = collector.received.lock().unwrap();
            assert_eq!(requests.len(), 2);
            for (request, expected) in requests.iter().zip([2, 3]) {
                let resource = &request.resource_metrics[0];
                assert!(resource
                    .resource
                    .as_ref()
                    .unwrap()
                    .attributes
                    .iter()
                    .any(|a| a.key == "service.name"));
                let metric = resource
                    .scope_metrics
                    .iter()
                    .flat_map(|scope| &scope.metrics)
                    .find(|m| m.name == "silta_http_requests")
                    .unwrap();
                let Some(Data::Sum(sum)) = &metric.data else {
                    panic!("expected cumulative counter")
                };
                assert_eq!(sum.aggregation_temporality, 2);
                assert!(sum.is_monotonic);
                assert_eq!(sum.data_points[0].value, Some(Value::AsInt(expected)));
            }
        }
        // Success, partial acceptance, malformed/oversized replies, HTTP error,
        // redirects and a hung collector all stay on the exporter thread.
        for mode in [1, 2, 3, 4, 5, 6] {
            collector.mode.store(mode, Ordering::Relaxed);
            let started = Instant::now();
            let _ = flush(provider.clone()).await.unwrap();
            assert!(started.elapsed() < Duration::from_secs(1));
        }
        collector.mode.store(0, Ordering::Relaxed);
        flush(provider.clone()).await.unwrap().unwrap();
        {
            let requests = collector.received.lock().unwrap();
            let last = requests.last().unwrap();
            let exports = last
                .resource_metrics
                .iter()
                .flat_map(|r| &r.scope_metrics)
                .flat_map(|s| &s.metrics)
                .find(|m| m.name == "silta_metrics_exports")
                .unwrap();
            let Some(Data::Sum(sum)) = &exports.data else {
                panic!("counter expected")
            };
            let values: Vec<_> = sum
                .data_points
                .iter()
                .map(|point| point.value.unwrap())
                .collect();
            assert!(
                values.contains(&Value::AsInt(5)),
                "five transport/protocol failures"
            );
            assert!(
                values.contains(&Value::AsInt(1)),
                "partial acceptance is separate"
            );
        }
        telemetry.shutdown().await;
        server.abort();
        let _ = server.await;
    }

    #[test]
    fn invalid_metrics_configuration_is_rejected() {
        for endpoint in [
            "",
            "collector:4318",
            "ftp://localhost/x",
            "http://user:secret@localhost/x",
            "http://localhost/x#fragment",
        ] {
            let config = MetricsConfig {
                otlp_endpoint: Some(endpoint.into()),
                ..Default::default()
            };
            assert!(config.validate().is_err());
        }
        for duration in [Duration::ZERO, Duration::from_secs(3601)] {
            let config = MetricsConfig {
                export_interval: duration,
                ..Default::default()
            };
            assert!(config.validate().is_err());
        }
        let config = MetricsConfig {
            export_timeout: Duration::from_secs(6),
            ..Default::default()
        };
        assert!(config.validate().is_err());
    }
}
