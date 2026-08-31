//! HTTP boundary types for Silta.
//!
//! This crate deliberately does not choose an HTTP server implementation yet.
//! It holds the small shared vocabulary that higher-level runtime code can use
//! while HTTP engine decisions are still documented and evaluated.

pub use silta_core::Method;

/// Request metadata needed before body parsing or Python execution decisions.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RequestHead {
    method: Method,
    path: String,
}

impl RequestHead {
    /// Creates request head metadata.
    pub fn new(method: Method, path: impl Into<String>) -> Self {
        Self {
            method,
            path: path.into(),
        }
    }

    /// Returns the request method.
    pub fn method(&self) -> Method {
        self.method
    }

    /// Returns the request path.
    pub fn path(&self) -> &str {
        &self.path
    }
}

/// Response metadata produced before body serialization.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ResponseHead {
    status: u16,
}

impl ResponseHead {
    /// Creates response head metadata.
    pub fn new(status: u16) -> Self {
        Self { status }
    }

    /// Returns the HTTP status code.
    pub fn status(&self) -> u16 {
        self.status
    }
}

#[cfg(test)]
mod tests {
    use super::{Method, RequestHead, ResponseHead};

    #[test]
    fn request_and_response_heads_store_metadata() {
        let request = RequestHead::new(Method::Get, "/hello");
        let response = ResponseHead::new(200);

        assert_eq!(request.method(), Method::Get);
        assert_eq!(request.path(), "/hello");
        assert_eq!(response.status(), 200);
    }
}
