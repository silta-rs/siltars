use std::env;
use std::net::IpAddr;

use silta_core::{Application, Method, Route};
use silta_runtime::{Runtime, RuntimeConfig};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let config = parse_config()?;
    let runtime = Runtime::prepare(native_application())?;
    runtime.serve(config).await?;
    Ok(())
}

fn native_application() -> Application {
    let mut app = Application::new("silta-native-runtime");
    app.add_route(Route::new(Method::Get, "/ping", "ping"));
    app.add_route(Route::new(Method::Get, "/rates", "list_rates"));
    app.add_route(Route::new(Method::Get, "/rates/{base}/{quote}", "get_rate"));
    app.add_route(Route::new(Method::Post, "/echo", "create_echo"));
    app.add_route(Route::new(Method::Put, "/echo/{item_id}", "replace_echo"));
    app.add_route(Route::new(Method::Patch, "/echo/{item_id}", "update_echo"));
    app.add_route(Route::new(Method::Delete, "/echo/{item_id}", "delete_echo"));
    app
}

fn parse_config() -> anyhow::Result<RuntimeConfig> {
    let mut config = RuntimeConfig::default();
    config.database_url = env::var("DATABASE_URL").ok();

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
            "--definition" => {
                let _ = args
                    .next()
                    .ok_or_else(|| anyhow::anyhow!("--definition needs a value"))?;
            }
            "--help" | "-h" => {
                print_help();
                std::process::exit(0);
            }
            unknown => anyhow::bail!("unknown argument: {unknown}"),
        }
    }

    Ok(config)
}

fn print_help() {
    println!("silta-runtime --host 127.0.0.1 --port 8000 [--database-url postgresql://...]");
}
