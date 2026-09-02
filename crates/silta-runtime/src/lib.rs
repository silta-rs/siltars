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
use sqlx::PgPool;
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
}

impl fmt::Display for RuntimeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::RouteTable(error) => write!(f, "route table error: {error}"),
            Self::Bind(error) => write!(f, "bind error: {error}"),
            Self::Server(error) => write!(f, "server error: {error}"),
            Self::Database(error) => write!(f, "database error: {error}"),
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
            Some(database_url) => Some(
                PgPoolOptions::new()
                    .min_connections(config.db_min_connections)
                    .max_connections(config.db_max_connections)
                    .acquire_timeout(config.db_acquire_timeout)
                    .connect(database_url)
                    .await?,
            ),
            None => None,
        };

        let state = AppState { pool };
        let app = native_router(&self.application, state);
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
pub fn native_router(application: &Application, state: AppState) -> Router {
    let mut routes: BTreeMap<String, MethodRouter<AppState>> = BTreeMap::new();

    for route in application.routes() {
        let path = axum_path(route.path());
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

    router.with_state(state)
}

fn axum_path(path: &str) -> String {
    let mut converted = String::with_capacity(path.len());
    let mut parameter = false;

    for character in path.chars() {
        match character {
            '{' => {
                parameter = true;
                converted.push(':');
            }
            '}' => {
                parameter = false;
            }
            _ => converted.push(character),
        }
    }

    if parameter {
        path.to_owned()
    } else {
        converted
    }
}

fn method_router_for_route(route: &Route) -> MethodRouter<AppState> {
    if let Some(response) = route.native_response() {
        return static_json_router(route.method(), response.clone());
    }

    match (route.method(), route.handler()) {
        (Method::Get, "ping") => get(ping),
        (Method::Get, "list_rates") => get(list_rates),
        (Method::Get, "get_rate") => get(get_rate),
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
        Method::Head => head(move || async move { StatusCode::NO_CONTENT }),
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
            super::axum_path("/rates/{base}/{quote}"),
            "/rates/:base/:quote"
        );
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
