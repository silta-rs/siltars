//! Runtime orchestration skeleton for Silta.
//!
//! This crate is the future home of runtime startup and hot-path orchestration.
//! It does not start an HTTP server or embed Python in the bootstrap phase.

use std::error::Error;
use std::fmt;

use silta_core::Application;
use silta_router::{RouteTable, RouteTableError};

/// Errors returned while preparing the runtime.
#[derive(Debug)]
pub enum RuntimeError {
    /// Route metadata could not be converted into a route table.
    RouteTable(RouteTableError),
}

impl fmt::Display for RuntimeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::RouteTable(error) => write!(f, "route table error: {error}"),
        }
    }
}

impl Error for RuntimeError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::RouteTable(error) => Some(error),
        }
    }
}

impl From<RouteTableError> for RuntimeError {
    fn from(error: RouteTableError) -> Self {
        Self::RouteTable(error)
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
