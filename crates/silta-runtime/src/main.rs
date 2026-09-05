use std::env;
use std::fs;
use std::net::IpAddr;
use std::path::PathBuf;
use std::time::Duration;

use silta_core::{Application, Method, Route};
use silta_runtime::{Runtime, RuntimeConfig};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let command = parse_command()?;
    let application = match command.definition {
        Some(path) => load_application_definition(path)?,
        None => native_application(),
    };
    let runtime = Runtime::prepare(application)?;
    runtime.serve(command.runtime).await?;
    Ok(())
}

struct CommandConfig {
    runtime: RuntimeConfig,
    definition: Option<PathBuf>,
}

fn load_application_definition(path: PathBuf) -> anyhow::Result<Application> {
    let contents = fs::read_to_string(&path)?;
    let application = serde_json::from_str::<Application>(&contents)?;
    Ok(application)
}

fn native_application() -> Application {
    let mut app = Application::new("silta-native-runtime");
    app.add_route(Route::new(Method::Get, "/ping", "ping"));
    app.add_route(Route::new(Method::Get, "/rates", "list_rates"));
    app.add_route(Route::new(Method::Get, "/rates/bulk", "list_rates_bulk"));
    app.add_route(Route::new(Method::Get, "/rates/{base}/{quote}", "get_rate"));
    app.add_route(Route::new(Method::Get, "/ch/rates", "ch_list_rates"));
    app.add_route(Route::new(
        Method::Get,
        "/ch/rates/1000",
        "ch_list_rates_1000",
    ));
    app.add_route(Route::new(
        Method::Get,
        "/ch/rates/{base}/{quote}",
        "ch_get_rate",
    ));
    app.add_route(Route::new(Method::Get, "/setting", "get_setting"));
    app.add_route(Route::new(Method::Patch, "/setting", "patch_setting"));
    app.add_route(Route::new(Method::Post, "/echo", "create_echo"));
    app.add_route(Route::new(Method::Put, "/echo/{item_id}", "replace_echo"));
    app.add_route(Route::new(Method::Patch, "/echo/{item_id}", "update_echo"));
    app.add_route(Route::new(Method::Delete, "/echo/{item_id}", "delete_echo"));
    app
}

fn parse_command() -> anyhow::Result<CommandConfig> {
    let mut config = parse_config_from_env()?;
    let mut definition = None;

    let mut args = env::args().skip(1);
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--host" => {
                let value = args
                    .next()
                    .ok_or_else(|| anyhow::anyhow!("--host needs a value"))?;
                config.host = value.parse::<IpAddr>()?;
            }
            "--port" => {
                let value = args
                    .next()
                    .ok_or_else(|| anyhow::anyhow!("--port needs a value"))?;
                config.port = value.parse::<u16>()?;
            }
            "--request-timeout-ms" => {
                let value = args
                    .next()
                    .ok_or_else(|| anyhow::anyhow!("--request-timeout-ms needs a value"))?;
                config.request_timeout = Duration::from_millis(value.parse::<u64>()?);
            }
            "--metrics-listen" => {
                config.metrics.listen = Some(
                    args.next()
                        .ok_or_else(|| anyhow::anyhow!("--metrics-listen needs a value"))?
                        .parse()?,
                );
            }
            "--otlp-metrics-endpoint" => {
                config.metrics.otlp_endpoint = Some(
                    args.next()
                        .ok_or_else(|| anyhow::anyhow!("--otlp-metrics-endpoint needs a value"))?,
                );
            }
            "--service-name" => {
                config.metrics.service_name = Some(
                    args.next()
                        .ok_or_else(|| anyhow::anyhow!("--service-name needs a value"))?,
                );
            }
            "--metrics-export-interval-ms" => {
                config.metrics.export_interval = Duration::from_millis(
                    args.next()
                        .ok_or_else(|| {
                            anyhow::anyhow!("--metrics-export-interval-ms needs a value")
                        })?
                        .parse()?,
                );
            }
            "--metrics-export-timeout-ms" => {
                config.metrics.export_timeout = Duration::from_millis(
                    args.next()
                        .ok_or_else(|| {
                            anyhow::anyhow!("--metrics-export-timeout-ms needs a value")
                        })?
                        .parse()?,
                );
            }
            "--clickhouse-url" => {
                let value = args
                    .next()
                    .ok_or_else(|| anyhow::anyhow!("--clickhouse-url needs a value"))?;
                config.clickhouse_url = Some(value);
            }
            "--clickhouse-max-threads" => {
                let value = args
                    .next()
                    .ok_or_else(|| anyhow::anyhow!("--clickhouse-max-threads needs a value"))?;
                config.clickhouse_max_threads = Some(value.parse::<u32>()?);
            }
            "--clickhouse-database" => {
                let value = args
                    .next()
                    .ok_or_else(|| anyhow::anyhow!("--clickhouse-database needs a value"))?;
                config.clickhouse_database = value;
            }
            "--database-url" => {
                let value = args
                    .next()
                    .ok_or_else(|| anyhow::anyhow!("--database-url needs a value"))?;
                config.database_url = Some(value);
            }
            "--db-min-connections" => {
                let value = args
                    .next()
                    .ok_or_else(|| anyhow::anyhow!("--db-min-connections needs a value"))?;
                config.db_min_connections = value.parse::<u32>()?;
            }
            "--db-max-connections" => {
                let value = args
                    .next()
                    .ok_or_else(|| anyhow::anyhow!("--db-max-connections needs a value"))?;
                config.db_max_connections = value.parse::<u32>()?;
            }
            "--db-acquire-timeout-ms" => {
                let value = args
                    .next()
                    .ok_or_else(|| anyhow::anyhow!("--db-acquire-timeout-ms needs a value"))?;
                config.db_acquire_timeout = Duration::from_millis(value.parse::<u64>()?);
            }
            "--python-bridge-executable" => {
                let value = args
                    .next()
                    .ok_or_else(|| anyhow::anyhow!("--python-bridge-executable needs a value"))?;
                config.python_bridge_executable = Some(value);
            }
            "--python-bridge-target" => {
                let value = args
                    .next()
                    .ok_or_else(|| anyhow::anyhow!("--python-bridge-target needs a value"))?;
                config.python_bridge_target = Some(value);
            }
            "--definition" => {
                let value = args
                    .next()
                    .ok_or_else(|| anyhow::anyhow!("--definition needs a value"))?;
                definition = Some(PathBuf::from(value));
            }
            "--help" | "-h" => {
                print_help();
                std::process::exit(0);
            }
            unknown => anyhow::bail!("unknown argument: {unknown}"),
        }
    }

    Ok(CommandConfig {
        runtime: config,
        definition,
    })
}

fn parse_config_from_env() -> anyhow::Result<RuntimeConfig> {
    let mut config = RuntimeConfig::default();
    config.request_timeout = env::var("SILTA_REQUEST_TIMEOUT_MS")
        .ok()
        .map(|value| value.parse::<u64>().map(Duration::from_millis))
        .transpose()?
        .unwrap_or(config.request_timeout);
    config.metrics.listen = env::var("SILTA_METRICS_LISTEN")
        .ok()
        .map(|value| value.parse())
        .transpose()?;
    config.metrics.otlp_endpoint = match env::var("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT").ok() {
        Some(endpoint) => Some(endpoint),
        None => env::var("OTEL_EXPORTER_OTLP_ENDPOINT")
            .ok()
            .map(|base| {
                let mut url = reqwest::Url::parse(&base)?;
                url.set_path(&format!("{}/v1/metrics", url.path().trim_end_matches('/')));
                Ok::<_, anyhow::Error>(url.to_string())
            })
            .transpose()?,
    };
    config.metrics.service_name = env::var("OTEL_SERVICE_NAME").ok();
    config.metrics.export_interval = env::var("OTEL_METRIC_EXPORT_INTERVAL")
        .ok()
        .map(|value| value.parse::<u64>().map(Duration::from_millis))
        .transpose()?
        .unwrap_or(config.metrics.export_interval);
    config.metrics.export_timeout = env::var("OTEL_METRIC_EXPORT_TIMEOUT")
        .ok()
        .map(|value| value.parse::<u64>().map(Duration::from_millis))
        .transpose()?
        .unwrap_or(config.metrics.export_timeout);
    config.database_url = env::var("DATABASE_URL").ok();
    config.db_min_connections = env::var("SILTA_DB_MIN_CONNECTIONS")
        .ok()
        .map(|value| value.parse::<u32>())
        .transpose()?
        .unwrap_or(config.db_min_connections);
    config.db_max_connections = env::var("SILTA_DB_MAX_CONNECTIONS")
        .ok()
        .map(|value| value.parse::<u32>())
        .transpose()?
        .unwrap_or(config.db_max_connections);
    config.db_acquire_timeout = env::var("SILTA_DB_ACQUIRE_TIMEOUT_MS")
        .ok()
        .map(|value| value.parse::<u64>().map(Duration::from_millis))
        .transpose()?
        .unwrap_or(config.db_acquire_timeout);
    config.clickhouse_url = env::var("CLICKHOUSE_URL").ok();
    if let Ok(database) = env::var("CLICKHOUSE_DATABASE") {
        config.clickhouse_database = database;
    }
    config.clickhouse_max_threads = env::var("CLICKHOUSE_MAX_THREADS")
        .ok()
        .map(|value| value.parse::<u32>())
        .transpose()?;
    config.python_bridge_executable = env::var("SILTA_PYTHON_BRIDGE_EXECUTABLE").ok();
    config.python_bridge_target = env::var("SILTA_PYTHON_BRIDGE_TARGET").ok();

    Ok(config)
}

fn print_help() {
    println!(
        "silta-runtime --host 127.0.0.1 --port 8000 [--definition app.json] \
         [--database-url postgresql://...] [--db-min-connections 1] \
         [--db-max-connections 10] \
         [--clickhouse-url http://127.0.0.1:8123] [--clickhouse-database silta_poc] [--clickhouse-max-threads 1] [--python-bridge-executable python] \
         [--python-bridge-target app.py:app] [--request-timeout-ms 30000] \
         [--metrics-listen 127.0.0.1:9464] [--otlp-metrics-endpoint http://localhost:4318/v1/metrics] \
         [--service-name my-api] [--metrics-export-interval-ms 15000] [--metrics-export-timeout-ms 2000]"
    );
}
