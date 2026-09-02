//! Runtime orchestration for Silta.
//!
//! The bootstrap runtime proves the core Silta boundary: Python can describe an
//! application, while supported HTTP, routing, database, and JSON response paths
//! execute in native Rust code.

use std::error::Error;
use std::fmt;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::time::Duration;

use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::response::IntoResponse;
use axum::routing::{delete, get, patch, post, put};
use axum::{Json, Router};
use serde::Serialize;
use serde_json::{json, Value};
use silta_core::Application;
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
        let app = native_router(state);
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

/// Builds the bootstrap native HTTP router.
pub fn native_router(state: AppState) -> Router {
    Router::new()
        .route("/ping", get(ping))
        .route("/rates", get(list_rates))
        .route("/rates/:base/:quote", get(get_rate))
        .route("/echo", post(create_echo))
        .route("/echo/:item_id", put(replace_echo))
        .route("/echo/:item_id", patch(update_echo))
        .route("/echo/:item_id", delete(delete_echo))
        .with_state(state)
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
}
