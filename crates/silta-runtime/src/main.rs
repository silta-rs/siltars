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

    Ok(config)
}

fn print_help() {
    println!(
        "silta-runtime --host 127.0.0.1 --port 8000 [--definition app.json] \
         [--database-url postgresql://...] [--db-min-connections 1] \
         [--db-max-connections 10]"
    );
}
