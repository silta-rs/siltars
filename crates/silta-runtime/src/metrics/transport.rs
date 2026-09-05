//! Standard OTLP encoder with bounded, validated Collector replies.
use std::io::Read;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Duration;

use async_trait::async_trait;
use axum::body::Bytes;
use axum::http::{Request, Response, StatusCode};
use opentelemetry::metrics::MeterProvider;
use opentelemetry::KeyValue;
use opentelemetry_http::{HttpClient, HttpError};
use opentelemetry_proto::tonic::collector::metrics::v1::ExportMetricsServiceResponse;
use opentelemetry_sdk::metrics::SdkMeterProvider;
use prost::Message;

use super::{config_error, RuntimeError};

const MAX_REPLY_BYTES: u64 = 64 * 1024;

#[derive(Debug, Default)]
pub(super) struct ExportStats {
    success: AtomicU64,
    failure: AtomicU64,
    partial: AtomicU64,
    rejected: AtomicU64,
}
impl ExportStats {
    pub(super) fn register(self: &Arc<Self>, provider: &SdkMeterProvider) {
        let meter = provider.meter("silta-runtime");
        let stats = self.clone();
        meter
            .u64_observable_counter("silta_metrics_exports")
            .with_callback(move |observer| {
                for (outcome, value) in [
                    ("success", &stats.success),
                    ("failure", &stats.failure),
                    ("partial", &stats.partial),
                ] {
                    observer.observe(
                        value.load(Ordering::Relaxed),
                        &[KeyValue::new("outcome", outcome)],
                    );
                }
            })
            .build();
        let stats = self.clone();
        meter
            .u64_observable_counter("silta_metrics_rejected_data_points")
            .with_callback(move |observer| {
                observer.observe(stats.rejected.load(Ordering::Relaxed), &[]);
            })
            .build();
    }
}

#[derive(Debug)]
pub(super) struct BoundedClient {
    client: reqwest::blocking::Client,
    stats: Arc<ExportStats>,
}
impl BoundedClient {
    pub(super) fn new(timeout: Duration, stats: Arc<ExportStats>) -> Result<Self, RuntimeError> {
        let client = reqwest::blocking::Client::builder()
            .timeout(timeout)
            .connect_timeout(timeout)
            .redirect(reqwest::redirect::Policy::none())
            .build()
            .map_err(|_| config_error("OTLP HTTP client initialization failed"))?;
        Ok(Self { client, stats })
    }

    fn send_blocking(&self, request: Request<Bytes>) -> Result<Response<Bytes>, HttpError> {
        let (parts, body) = request.into_parts();
        let response = self
            .client
            .request(parts.method, parts.uri.to_string())
            .headers(parts.headers)
            .body(body)
            .send()
            .map_err(|_| "Collector transport failed or timed out")?;
        if response.status() != StatusCode::OK {
            return Err("Collector returned non-200 status".into());
        }
        let mut bytes = Vec::new();
        response
            .take(MAX_REPLY_BYTES + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| "Collector reply read failed")?;
        if bytes.len() as u64 > MAX_REPLY_BYTES {
            return Err("Collector reply exceeds 64 KiB".into());
        }
        let reply = ExportMetricsServiceResponse::decode(bytes.as_slice())
            .map_err(|_| "invalid Collector protobuf reply")?;
        if let Some(partial) = reply.partial_success {
            if partial.rejected_data_points < 0 {
                return Err("invalid negative rejected datapoint count".into());
            }
            if partial.rejected_data_points > 0 || !partial.error_message.is_empty() {
                self.stats.partial.fetch_add(1, Ordering::Relaxed);
                self.stats
                    .rejected
                    .fetch_add(partial.rejected_data_points as u64, Ordering::Relaxed);
                // Partial acceptance is not retried immediately. Do not log the
                // server-controlled error message or credentials from the URI.
                return Ok(Response::new(Bytes::new()));
            }
        }
        self.stats.success.fetch_add(1, Ordering::Relaxed);
        Ok(Response::new(Bytes::new()))
    }
}
#[async_trait]
impl HttpClient for BoundedClient {
    async fn send_bytes(&self, request: Request<Bytes>) -> Result<Response<Bytes>, HttpError> {
        // Called by PeriodicReader's dedicated thread, never by an HTTP handler.
        let result = self.send_blocking(request);
        if result.is_err() {
            self.stats.failure.fetch_add(1, Ordering::Relaxed);
        }
        result
    }
}
