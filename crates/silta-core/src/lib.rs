//! Core application representation types for Silta.
//!
//! These types are intentionally small. They model the application boundary that
//! the Python API will eventually produce and the Rust runtime will consume.

/// A Silta application description.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Application {
    name: String,
    routes: Vec<Route>,
}

impl Application {
    /// Creates an empty application description.
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            routes: Vec::new(),
        }
    }

    /// Returns the application name.
    pub fn name(&self) -> &str {
        &self.name
    }

    /// Returns the route descriptions currently attached to the application.
    pub fn routes(&self) -> &[Route] {
        &self.routes
    }

    /// Adds a route description.
    pub fn add_route(&mut self, route: Route) {
        self.routes.push(route);
    }
}

/// HTTP methods understood by the bootstrap application model.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Method {
    Get,
    Post,
    Put,
    Patch,
    Delete,
    Options,
    Head,
}

impl Method {
    /// Returns the canonical uppercase method name.
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Get => "GET",
            Self::Post => "POST",
            Self::Put => "PUT",
            Self::Patch => "PATCH",
            Self::Delete => "DELETE",
            Self::Options => "OPTIONS",
            Self::Head => "HEAD",
        }
    }
}

/// A route in the application description.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Route {
    method: Method,
    path: String,
    handler: String,
}

impl Route {
    /// Creates a route description.
    pub fn new(method: Method, path: impl Into<String>, handler: impl Into<String>) -> Self {
        Self {
            method,
            path: path.into(),
            handler: handler.into(),
        }
    }

    /// Returns the route method.
    pub fn method(&self) -> Method {
        self.method
    }

    /// Returns the route path.
    pub fn path(&self) -> &str {
        &self.path
    }

    /// Returns the symbolic handler name recorded for the route.
    pub fn handler(&self) -> &str {
        &self.handler
    }
}

#[cfg(test)]
mod tests {
    use super::{Application, Method, Route};

    #[test]
    fn application_records_routes() {
        let mut app = Application::new("hello");
        app.add_route(Route::new(Method::Get, "/hello", "hello"));

        assert_eq!(app.name(), "hello");
        assert_eq!(app.routes().len(), 1);
        assert_eq!(app.routes()[0].method().as_str(), "GET");
        assert_eq!(app.routes()[0].path(), "/hello");
    }
}
