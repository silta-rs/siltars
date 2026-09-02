//! Runtime orchestration for Silta.
//!
//! The bootstrap runtime proves the core Silta boundary: Python can describe an
//! application, while supported HTTP, routing, database, and JSON response paths
//! execute in native Rust code.

use std::collections::BTreeMap;
use std::error::Error;
use std::fmt;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::time::Duration;

use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::response::IntoResponse;
use axum::routing::{delete, get, head, options, patch, post, put, MethodRouter};
use axum::{Json, Router};
use serde::Serialize;
use serde_json::{json, Value};
use silta_core::{Application, Method, Route};
use silta_router::{RouteTable, RouteTableError};
use sqlx::postgres::PgPoolOptions;
use sqlx::{Connection, PgConnection, PgPool};
use tokio::net::TcpListener;

/// Errors returned while preparing the runtime.
#[derive(Debug)]
pub enum RuntimeError {
    /// Route metadata could not be converted into a route table.
    RouteTable(RouteTableError),
    /// The runtime could not bind its HTTP listener.
    Bind(std::io::Error),
    /// The runtime server failed.
    Server(std::io::Error),
    /// The PostgreSQL pool could not be created.
    Database(sqlx::Error),
    /// The PostgreSQL server rejected or did not accept a connection.
    DatabaseConnectionRefused(sqlx::Error),
    /// A route path is malformed.
    InvalidRoutePath { path: String, reason: String },
}

impl fmt::Display for RuntimeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::RouteTable(error) => write!(f, "route table error: {error}"),
            Self::Bind(error) => write!(f, "bind error: {error}"),
            Self::Server(error) => write!(f, "server error: {error}"),
            Self::Database(error) => write!(f, "database error: {error}"),
            Self::DatabaseConnectionRefused(error) => {
                write!(f, "database connection refused: {error}")
            }
            Self::InvalidRoutePath { path, reason } => {
                write!(f, "invalid route path {path:?}: {reason}")
            }
        }
    }
}

impl Error for RuntimeError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::RouteTable(error) => Some(error),
            Self::Bind(error) => Some(error),
            Self::Server(error) => Some(error),
            Self::Database(error) => Some(error),
            Self::DatabaseConnectionRefused(error) => Some(error),
            Self::InvalidRoutePath { .. } => None,
        }
    }
}

impl From<RouteTableError> for RuntimeError {
    fn from(error: RouteTableError) -> Self {
        Self::RouteTable(error)
    }
}

impl From<sqlx::Error> for RuntimeError {
    fn from(error: sqlx::Error) -> Self {
        Self::Database(error)
    }
}

/// Runtime server configuration.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RuntimeConfig {
    /// Address to bind.
    pub host: IpAddr,
    /// Port to bind.
    pub port: u16,
    /// PostgreSQL connection URL used by native database routes.
    pub database_url: Option<String>,
    /// Minimum database connections kept by the native pool.
    pub db_min_connections: u32,
    /// Maximum database connections allowed by the native pool.
    pub db_max_connections: u32,
    /// Maximum time to wait for a database connection from the pool.
    pub db_acquire_timeout: Duration,
}

impl Default for RuntimeConfig {
    fn default() -> Self {
        Self {
            host: IpAddr::V4(Ipv4Addr::LOCALHOST),
            port: 8000,
            database_url: None,
            db_min_connections: 1,
            db_max_connections: 10,
            db_acquire_timeout: Duration::from_secs(5),
        }
    }
}

/// Prepared runtime state derived from an application description.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Runtime {
    application: Application,
    route_table: RouteTable,
}

impl Runtime {
    /// Prepares runtime state from an application description.
    pub fn prepare(application: Application) -> Result<Self, RuntimeError> {
        let route_table = RouteTable::from_routes(application.routes().iter().cloned())?;

        Ok(Self {
            application,
            route_table,
        })
    }

    /// Returns the source application description.
    pub fn application(&self) -> &Application {
        &self.application
    }

    /// Returns the prepared route table.
    pub fn route_table(&self) -> &RouteTable {
        &self.route_table
    }

    /// Starts the native HTTP runtime.
    pub async fn serve(self, config: RuntimeConfig) -> Result<(), RuntimeError> {
        let pool = match config.database_url.as_deref() {
            Some(database_url) => Some(create_pool(database_url, &config).await?),
            None => None,
        };

        let state = AppState { pool };
        let app = native_router(&self.application, state)?;
        let address = SocketAddr::new(config.host, config.port);
        let listener = TcpListener::bind(address)
            .await
            .map_err(RuntimeError::Bind)?;

        axum::serve(listener, app)
            .with_graceful_shutdown(shutdown_signal())
            .await
            .map_err(RuntimeError::Server)
    }
}

/// Builds the bootstrap native HTTP router from an application description.
pub fn native_router(application: &Application, state: AppState) -> Result<Router, RuntimeError> {
    let mut routes: BTreeMap<String, MethodRouter<AppState>> = BTreeMap::new();

    for route in application.routes() {
        let path = axum_path(route.path())?;
        let method_router = method_router_for_route(route);

        routes
            .entry(path)
            .and_modify(|existing| {
                *existing = existing.clone().merge(method_router.clone());
            })
            .or_insert(method_router);
    }

    let mut router = Router::new();
    for (path, method_router) in routes {
        router = router.route(&path, method_router);
    }

    Ok(router.with_state(state))
}

async fn create_pool(database_url: &str, config: &RuntimeConfig) -> Result<PgPool, RuntimeError> {
    PgConnection::connect(database_url)
        .await
        .map_err(|error| {
            if is_connection_refused(&error) {
                RuntimeError::DatabaseConnectionRefused(error)
            } else {
                RuntimeError::Database(error)
            }
        })?
        .close()
        .await
        .map_err(RuntimeError::Database)?;

    PgPoolOptions::new()
        .min_connections(config.db_min_connections)
        .max_connections(config.db_max_connections)
        .acquire_timeout(config.db_acquire_timeout)
        .connect(database_url)
        .await
        .map_err(RuntimeError::Database)
}

fn is_connection_refused(error: &sqlx::Error) -> bool {
    let mut source = error.source();
    while let Some(error) = source {
        if let Some(io_error) = error.downcast_ref::<std::io::Error>() {
            return io_error.kind() == std::io::ErrorKind::ConnectionRefused;
        }
        source = error.source();
    }

    error.to_string().contains("Connection refused")
}

fn axum_path(path: &str) -> Result<String, RuntimeError> {
    validate_route_path(path)?;

    let mut converted = String::with_capacity(path.len());
    let mut parameter = false;
    let mut parameter_name = String::new();

    for character in path.chars() {
        match character {
            '{' => {
                if parameter {
                    return Err(invalid_route_path(path, "nested route parameter"));
                }
                parameter = true;
                parameter_name.clear();
                converted.push(':');
            }
            '}' => {
                if !parameter {
                    return Err(invalid_route_path(
                        path,
                        "closing brace without opening brace",
                    ));
                }
                if parameter_name.is_empty()
                    || !parameter_name
                        .chars()
                        .all(|character| character == '_' || character.is_ascii_alphanumeric())
                    || parameter_name
                        .chars()
                        .next()
                        .is_some_and(|character| character.is_ascii_digit())
                {
                    return Err(invalid_route_path(path, "invalid route parameter name"));
                }
                parameter = false;
            }
            _ => {
                if parameter {
                    parameter_name.push(character);
                }
                converted.push(character);
            }
        }
    }

    if parameter {
        Err(invalid_route_path(path, "unclosed route parameter"))
    } else {
        Ok(converted)
    }
}

fn validate_route_path(path: &str) -> Result<(), RuntimeError> {
    if !path.starts_with('/') {
        return Err(invalid_route_path(path, "route path must start with '/'"));
    }

    for segment in path.split('/') {
        if !segment.contains('{') && !segment.contains('}') {
            continue;
        }
        if !(segment.starts_with('{') && segment.ends_with('}')) {
            return Err(invalid_route_path(
                path,
                "route parameters must be complete path segments",
            ));
        }
        if !is_valid_route_parameter_name(&segment[1..segment.len() - 1]) {
            return Err(invalid_route_path(path, "invalid route parameter name"));
        }
    }

    Ok(())
}

fn is_valid_route_parameter_name(name: &str) -> bool {
    !name.is_empty()
        && !name
            .chars()
            .next()
            .is_some_and(|character| character.is_ascii_digit())
        && name
            .chars()
            .all(|character| character == '_' || character.is_ascii_alphanumeric())
}

fn invalid_route_path(path: &str, reason: impl Into<String>) -> RuntimeError {
    RuntimeError::InvalidRoutePath {
        path: path.to_owned(),
        reason: reason.into(),
    }
}

fn method_router_for_route(route: &Route) -> MethodRouter<AppState> {
    if let Some(response) = route.native_response() {
        return static_json_router(route.method(), response.clone());
    }

    match (route.method(), route.handler()) {
        (Method::Get, "ping") => get(ping),
        (Method::Get, "list_rates") => get(list_rates),
        (Method::Get, "list_rates_bulk") => get(list_rates_bulk),
        (Method::Get, "get_rate") => get(get_rate),
        (Method::Get, "get_setting") => get(get_setting),
        (Method::Patch, "patch_setting") => patch(patch_setting),
        (Method::Post, "create_echo") => post(create_echo),
        (Method::Put, "replace_echo") => put(replace_echo),
        (Method::Patch, "update_echo") => patch(update_echo),
        (Method::Delete, "delete_echo") => delete(delete_echo),
        (method, _) => not_implemented_router(method),
    }
}

fn static_json_router(method: Method, response: Value) -> MethodRouter<AppState> {
    match method {
        Method::Get => get({
            let response = response.clone();
            move || {
                let response = response.clone();
                async move { Json(response) }
            }
        }),
        Method::Post => post({
            let response = response.clone();
            move || {
                let response = response.clone();
                async move { Json(response) }
            }
        }),
        Method::Put => put({
            let response = response.clone();
            move || {
                let response = response.clone();
                async move { Json(response) }
            }
        }),
        Method::Patch => patch({
            let response = response.clone();
            move || {
                let response = response.clone();
                async move { Json(response) }
            }
        }),
        Method::Delete => delete({
            let response = response.clone();
            move || {
                let response = response.clone();
                async move { Json(response) }
            }
        }),
        Method::Options => options({
            let response = response.clone();
            move || {
                let response = response.clone();
                async move { Json(response) }
            }
        }),
        Method::Head => head(move || async move { StatusCode::OK }),
    }
}

fn not_implemented_router(method: Method) -> MethodRouter<AppState> {
    match method {
        Method::Get => get(not_implemented),
        Method::Post => post(not_implemented),
        Method::Put => put(not_implemented),
        Method::Patch => patch(not_implemented),
        Method::Delete => delete(not_implemented),
        Method::Options => options(not_implemented),
        Method::Head => head(not_implemented_head),
    }
}

async fn not_implemented() -> impl IntoResponse {
    (
        StatusCode::NOT_IMPLEMENTED,
        Json(json!({ "error": "route is described but has no native runtime handler yet" })),
    )
}

async fn not_implemented_head() -> StatusCode {
    StatusCode::NOT_IMPLEMENTED
}

/// Shared runtime state for native routes.
#[derive(Debug, Clone)]
pub struct AppState {
    pool: Option<PgPool>,
}

#[derive(Debug, Serialize, sqlx::FromRow)]
struct RateRow {
    rate_type: String,
    asset_class: String,
    base: String,
    quote: String,
    rate: String,
    ts_utc: String,
    source: String,
}

#[derive(Debug, sqlx::FromRow)]
struct BulkRateRow {
    id: i64,
    rate_type: String,
    asset_class: String,
    base: String,
    quote: String,
    rate: String,
    ts_utc: String,
    source: String,
    provider: String,
    region: String,
    tier: String,
}

#[derive(Debug, Serialize)]
struct BulkRatesResponse {
    count: usize,
    rates: Vec<BulkRateItem>,
}

#[derive(Debug, Serialize)]
struct BulkRateItem {
    id: i64,
    instrument: BulkInstrument,
    value: BulkRateValue,
    source: BulkSource,
}

#[derive(Debug, Serialize)]
struct BulkInstrument {
    rate_type: String,
    asset_class: String,
    base: String,
    quote: String,
}

#[derive(Debug, Serialize)]
struct BulkRateValue {
    rate: String,
    ts_utc: String,
}

#[derive(Debug, Serialize)]
struct BulkSource {
    code: String,
    provider: String,
    region: String,
    tier: String,
}

#[derive(Debug, Serialize, sqlx::FromRow)]
struct SettingRow {
    id: i64,
    name: String,
    value: String,
    version: i64,
}

async fn ping() -> Json<Value> {
    Json(json!({ "ok": true }))
}

async fn list_rates(State(state): State<AppState>) -> Result<Json<Value>, RuntimeRouteError> {
    let pool = state.pool()?;
    let rows = sqlx::query_as::<_, RateRow>(
        r#"
        SELECT rate_type, asset_class, base, quote, rate::text AS rate, ts_utc::text AS ts_utc, source
        FROM public.rates
        ORDER BY public.rates.ts_utc DESC
        LIMIT 100
        "#,
    )
    .fetch_all(pool)
    .await?;

    Ok(Json(json!({ "rates": rows })))
}

async fn list_rates_bulk(State(state): State<AppState>) -> Result<Json<Value>, RuntimeRouteError> {
    let pool = state.pool()?;
    let rows = sqlx::query_as::<_, BulkRateRow>(
        r#"
        SELECT
            r.id,
            r.rate_type,
            r.asset_class,
            r.base,
            r.quote,
            r.rate::text AS rate,
            r.ts_utc::text AS ts_utc,
            r.source,
            s.provider,
            s.region,
            s.tier
        FROM public.rates AS r
        JOIN public.silta_rate_sources AS s ON s.source = r.source
        ORDER BY r.ts_utc DESC
        LIMIT 3000
        "#,
    )
    .fetch_all(pool)
    .await?;

    let rates = rows
        .into_iter()
        .map(|row| BulkRateItem {
            id: row.id,
            instrument: BulkInstrument {
                rate_type: row.rate_type,
                asset_class: row.asset_class,
                base: row.base,
                quote: row.quote,
            },
            value: BulkRateValue {
                rate: row.rate,
                ts_utc: row.ts_utc,
            },
            source: BulkSource {
                code: row.source,
                provider: row.provider,
                region: row.region,
                tier: row.tier,
            },
        })
        .collect::<Vec<_>>();

    Ok(Json(json!(BulkRatesResponse {
        count: rates.len(),
        rates,
    })))
}

async fn get_rate(
    State(state): State<AppState>,
    Path((base, quote)): Path<(String, String)>,
) -> Result<Json<Value>, RuntimeRouteError> {
    let pool = state.pool()?;
    let row = sqlx::query_as::<_, RateRow>(
        r#"
        SELECT rate_type, asset_class, base, quote, rate::text AS rate, ts_utc::text AS ts_utc, source
        FROM public.rates
        WHERE base = $1 AND quote = $2
        ORDER BY public.rates.ts_utc DESC
        LIMIT 1
        "#,
    )
    .bind(base.to_uppercase())
    .bind(quote.to_uppercase())
    .fetch_optional(pool)
    .await?;

    Ok(Json(match row {
        Some(row) => json!(row),
        None => json!({ "missing": true }),
    }))
}

async fn get_setting(State(state): State<AppState>) -> Result<Json<Value>, RuntimeRouteError> {
    let pool = state.pool()?;
    let row = sqlx::query_as::<_, SettingRow>(
        r#"
        SELECT id, name, value, version
        FROM public.silta_settings
        WHERE id = 1
        "#,
    )
    .fetch_one(pool)
    .await?;

    Ok(Json(json!(row)))
}

async fn patch_setting(
    State(state): State<AppState>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, RuntimeRouteError> {
    let pool = state.pool()?;
    let value = payload
        .get("value")
        .and_then(Value::as_str)
        .unwrap_or("patched");

    let row = sqlx::query_as::<_, SettingRow>(
        r#"
        UPDATE public.silta_settings
        SET value = $1,
            version = version + 1
        WHERE id = 1
        RETURNING id, name, value, version
        "#,
    )
    .bind(value)
    .fetch_one(pool)
    .await?;

    Ok(Json(json!(row)))
}

async fn create_echo(Json(payload): Json<Value>) -> Json<Value> {
    Json(json!({ "method": "POST", "payload": payload }))
}

async fn replace_echo(Path(item_id): Path<i64>, Json(payload): Json<Value>) -> Json<Value> {
    Json(json!({ "method": "PUT", "item_id": item_id, "payload": payload }))
}

async fn update_echo(Path(item_id): Path<i64>, Json(payload): Json<Value>) -> Json<Value> {
    Json(json!({ "method": "PATCH", "item_id": item_id, "payload": payload }))
}

async fn delete_echo(Path(item_id): Path<i64>) -> Json<Value> {
    Json(json!({ "method": "DELETE", "item_id": item_id, "deleted": true }))
}

impl AppState {
    fn pool(&self) -> Result<&PgPool, RuntimeRouteError> {
        self.pool
            .as_ref()
            .ok_or(RuntimeRouteError::DatabaseNotConfigured)
    }
}

#[derive(Debug)]
enum RuntimeRouteError {
    DatabaseNotConfigured,
    Database(sqlx::Error),
}

impl From<sqlx::Error> for RuntimeRouteError {
    fn from(error: sqlx::Error) -> Self {
        Self::Database(error)
    }
}

impl IntoResponse for RuntimeRouteError {
    fn into_response(self) -> axum::response::Response {
        let (status, message) = match self {
            Self::DatabaseNotConfigured => (
                StatusCode::SERVICE_UNAVAILABLE,
                "database is not configured for this runtime",
            ),
            Self::Database(error) => {
                eprintln!("silta runtime database query failed: {error}");
                (StatusCode::INTERNAL_SERVER_ERROR, "database query failed")
            }
        };

        (status, Json(json!({ "error": message }))).into_response()
    }
}

async fn shutdown_signal() {
    let _ = tokio::signal::ctrl_c().await;
}

#[cfg(test)]
mod tests {
    use super::Runtime;
    use silta_core::{Application, Method, Route};

    #[test]
    fn runtime_prepares_route_table() {
        let mut application = Application::new("hello");
        application.add_route(Route::new(Method::Get, "/hello", "hello"));

        let runtime = Runtime::prepare(application).expect("runtime");

        assert!(runtime
            .route_table()
            .exact_match(Method::Get, "/hello")
            .is_some());
    }

    #[test]
    fn axum_path_converts_python_parameters() {
        assert_eq!(
            super::axum_path("/rates/{base}/{quote}").expect("valid path"),
            "/rates/:base/:quote"
        );
    }

    #[test]
    fn axum_path_rejects_unclosed_parameter() {
        assert!(super::axum_path("/rates/{base").is_err());
    }

    #[test]
    fn axum_path_rejects_partial_segment_parameter() {
        assert!(super::axum_path("/rates/base-{quote}").is_err());
    }

    #[test]
    fn runtime_can_prepare_static_native_response_route() {
        let mut application = Application::new("hello");
        application.add_route(Route::with_native_response(
            Method::Get,
            "/hello",
            "hello",
            serde_json::json!({ "hello": "world" }),
        ));

        let runtime = Runtime::prepare(application).expect("runtime");

        assert!(runtime
            .route_table()
            .exact_match(Method::Get, "/hello")
            .is_some());
    }
}
