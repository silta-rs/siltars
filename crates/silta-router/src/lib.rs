//! Router abstractions for Silta.
//!
//! The bootstrap router is limited to exact route metadata lookup. Dynamic path
//! matching and integration with an HTTP framework are intentionally deferred.

use std::error::Error;
use std::fmt;

use silta_core::{Method, Route};

/// Error returned while building a route table.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RouteTableError {
    /// Two route descriptions share the same method and path.
    DuplicateRoute { method: Method, path: String },
}

impl fmt::Display for RouteTableError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::DuplicateRoute { method, path } => {
                write!(f, "duplicate route: {} {}", method.as_str(), path)
            }
        }
    }
}

impl Error for RouteTableError {}

/// A route table built from an application description.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct RouteTable {
    routes: Vec<Route>,
}

impl RouteTable {
    /// Creates an empty route table.
    pub fn new() -> Self {
        Self::default()
    }

    /// Builds a route table from route descriptions.
    pub fn from_routes(routes: impl IntoIterator<Item = Route>) -> Result<Self, RouteTableError> {
        let mut table = Self::new();

        for route in routes {
            table.add(route)?;
        }

        Ok(table)
    }

    /// Adds a route description to the table.
    pub fn add(&mut self, route: Route) -> Result<(), RouteTableError> {
        if self
            .routes
            .iter()
            .any(|existing| existing.method() == route.method() && existing.path() == route.path())
        {
            return Err(RouteTableError::DuplicateRoute {
                method: route.method(),
                path: route.path().to_owned(),
            });
        }

        self.routes.push(route);
        Ok(())
    }

    /// Finds an exact route metadata match.
    pub fn exact_match(&self, method: Method, path: &str) -> Option<&Route> {
        self.routes
            .iter()
            .find(|route| route.method() == method && route.path() == path)
    }

    /// Returns all registered route descriptions.
    pub fn routes(&self) -> &[Route] {
        &self.routes
    }
}

#[cfg(test)]
mod tests {
    use super::{RouteTable, RouteTableError};
    use silta_core::{Method, Route};

    #[test]
    fn exact_match_returns_registered_route() {
        let route = Route::new(Method::Get, "/hello", "hello");
        let table = RouteTable::from_routes([route]).expect("route table");

        let matched = table.exact_match(Method::Get, "/hello").expect("match");

        assert_eq!(matched.handler(), "hello");
    }

    #[test]
    fn duplicate_method_and_path_is_rejected() {
        let routes = [
            Route::new(Method::Get, "/hello", "hello"),
            Route::new(Method::Get, "/hello", "hello_again"),
        ];

        let error = RouteTable::from_routes(routes).expect_err("duplicate route");

        assert_eq!(
            error,
            RouteTableError::DuplicateRoute {
                method: Method::Get,
                path: "/hello".to_owned(),
            }
        );
    }
}
