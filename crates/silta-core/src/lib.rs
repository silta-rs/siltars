//! Core application representation types for Silta.
//!
//! These types are intentionally small. They model the application boundary that
//! the Python API will eventually produce and the Rust runtime will consume.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::error::Error;
use std::fmt;

/// Execution plan schema understood by this release.
pub const EXECUTION_PLAN_VERSION: u16 = 1;

fn deserialize_plan_version<'de, D>(deserializer: D) -> Result<Option<u16>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    // Missing is legacy; explicit null is not a valid version.
    u16::deserialize(deserializer).map(Some)
}

/// A Silta application description.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Application {
    #[serde(
        default,
        deserialize_with = "deserialize_plan_version",
        skip_serializing_if = "Option::is_none"
    )]
    plan_version: Option<u16>,
    name: String,
    #[serde(default)]
    routes: Vec<Route>,
}

impl Application {
    /// Creates an empty application description.
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            plan_version: Some(EXECUTION_PLAN_VERSION),
            name: name.into(),
            routes: Vec::new(),
        }
    }

    /// Returns the serialized execution plan schema version.
    pub const fn plan_version(&self) -> Option<u16> {
        self.plan_version
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

    /// Validates the versioned execution contract before runtime preparation.
    pub fn validate(&self) -> Result<(), ExecutionPlanError> {
        if let Some(version) = self.plan_version {
            if version != EXECUTION_PLAN_VERSION {
                return Err(ExecutionPlanError::UnsupportedVersion {
                    found: version,
                    supported: EXECUTION_PLAN_VERSION,
                });
            }
        }
        for route in &self.routes {
            if self.plan_version.is_some() != route.execution.is_some() {
                return Err(route.invalid_execution(
                    "versioned plans require execution for every route; legacy plans cannot include execution",
                ));
            }
            route.validate_execution()?;
        }

        Ok(())
    }
}

/// Validation failures in a Python-produced execution plan.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ExecutionPlanError {
    /// The plan was produced for a schema this runtime cannot safely execute.
    UnsupportedVersion { found: u16, supported: u16 },
    /// A route contains a contradictory execution decision.
    InvalidRouteExecution {
        method: Method,
        path: String,
        reason: String,
    },
}

impl fmt::Display for ExecutionPlanError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::UnsupportedVersion { found, supported } => write!(
                formatter,
                "unsupported execution plan version {found}; this runtime supports {supported}"
            ),
            Self::InvalidRouteExecution {
                method,
                path,
                reason,
            } => write!(
                formatter,
                "invalid execution plan for {} {path}: {reason}",
                method.as_str()
            ),
        }
    }
}

impl Error for ExecutionPlanError {}

/// HTTP methods understood by the bootstrap application model.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "UPPERCASE")]
pub enum Method {
    Get,
    Post,
    Put,
    Patch,
    Delete,
    Options,
    Head,
}

/// Runtime selected for a prepared route.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ExecutionMode {
    /// The request does not cross into Python at request time.
    Native,
    /// Rust owns the request data plane and invokes Python business logic.
    Hybrid,
    /// Python owns behavior that cannot yet be represented by native modules.
    PythonFallback,
}

/// Operation attached to a route execution decision.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum OperationKind {
    /// Rust returns an application-definition JSON value.
    StaticResponse,
    /// Rust invokes the declared Python handler.
    PythonHandler,
    /// Temporary Pre-Alpha mapping to a Rust handler by symbolic name.
    LegacySymbolic,
}

/// Prepared execution decision emitted by the Python control plane.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RouteExecution {
    mode: ExecutionMode,
    operation: OperationKind,
    reason: String,
}

impl RouteExecution {
    /// Creates a route execution decision.
    pub fn new(mode: ExecutionMode, operation: OperationKind, reason: impl Into<String>) -> Self {
        Self {
            mode,
            operation,
            reason: reason.into(),
        }
    }

    /// Returns the selected execution mode.
    pub const fn mode(&self) -> ExecutionMode {
        self.mode
    }

    /// Returns the selected operation kind.
    pub const fn operation(&self) -> OperationKind {
        self.operation
    }

    /// Returns the control-plane explanation for the selection.
    pub fn reason(&self) -> &str {
        &self.reason
    }
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
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Route {
    method: Method,
    path: String,
    handler: String,
    #[serde(default)]
    native_response: Option<Value>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    python_handler: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    execution: Option<RouteExecution>,
}

impl Route {
    /// Creates a route description.
    pub fn new(method: Method, path: impl Into<String>, handler: impl Into<String>) -> Self {
        Self {
            method,
            path: path.into(),
            handler: handler.into(),
            native_response: None,
            python_handler: Some(false),
            execution: Some(RouteExecution::new(
                ExecutionMode::Native,
                OperationKind::LegacySymbolic,
                "rust_constructor_legacy_symbolic",
            )),
        }
    }

    /// Creates a route description with a native JSON response payload.
    pub fn with_native_response(
        method: Method,
        path: impl Into<String>,
        handler: impl Into<String>,
        native_response: Value,
    ) -> Self {
        Self {
            method,
            path: path.into(),
            handler: handler.into(),
            native_response: Some(native_response),
            python_handler: Some(false),
            execution: Some(RouteExecution::new(
                ExecutionMode::Native,
                OperationKind::StaticResponse,
                "rust_constructor_static_response",
            )),
        }
    }

    /// Creates a route description that should execute through the Python bridge.
    pub fn with_python_handler(
        method: Method,
        path: impl Into<String>,
        handler: impl Into<String>,
    ) -> Self {
        Self {
            method,
            path: path.into(),
            handler: handler.into(),
            native_response: None,
            python_handler: Some(true),
            execution: Some(RouteExecution::new(
                ExecutionMode::Hybrid,
                OperationKind::PythonHandler,
                "rust_constructor_python_handler",
            )),
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

    /// Returns the optional native JSON response attached to the route.
    pub fn native_response(&self) -> Option<&Value> {
        self.native_response.as_ref()
    }

    /// Returns whether this route should execute through the Python bridge.
    pub fn python_handler(&self) -> bool {
        matches!(
            self.execution_mode(),
            ExecutionMode::Hybrid | ExecutionMode::PythonFallback
        )
    }

    /// Returns the explicit route execution contract when the plan contains one.
    pub fn execution(&self) -> Option<&RouteExecution> {
        self.execution.as_ref()
    }

    /// Resolves the execution mode, including legacy Pre-Alpha definitions.
    pub fn execution_mode(&self) -> ExecutionMode {
        self.execution
            .as_ref()
            .map(RouteExecution::mode)
            .unwrap_or_else(|| {
                if self.python_handler.unwrap_or(false) {
                    ExecutionMode::Hybrid
                } else {
                    ExecutionMode::Native
                }
            })
    }

    fn validate_execution(&self) -> Result<(), ExecutionPlanError> {
        if self.native_response.is_some() && self.python_handler.unwrap_or(false) {
            return Err(self.invalid_execution("Python routes cannot include a native response"));
        }
        let Some(execution) = &self.execution else {
            return Ok(());
        };
        if execution.mode == ExecutionMode::PythonFallback {
            return Err(self.invalid_execution("python_fallback is not implemented"));
        }
        if self
            .python_handler
            .is_some_and(|flag| flag != (execution.mode == ExecutionMode::Hybrid))
        {
            return Err(self.invalid_execution("python_handler conflicts with execution mode"));
        }

        if execution.reason.trim().is_empty() {
            return Err(self.invalid_execution("selection reason must not be empty"));
        }

        let valid = match (execution.mode, execution.operation) {
            (ExecutionMode::Native, OperationKind::StaticResponse) => self
                .native_response
                .as_ref()
                .is_some_and(|value| !value.is_null()),
            (ExecutionMode::Native, OperationKind::LegacySymbolic) => {
                self.native_response.is_none()
            }
            (
                ExecutionMode::Hybrid | ExecutionMode::PythonFallback,
                OperationKind::PythonHandler,
            ) => self.native_response.is_none(),
            _ => false,
        };

        if valid {
            Ok(())
        } else {
            Err(self.invalid_execution(
                "execution mode, operation, and native response are contradictory",
            ))
        }
    }

    fn invalid_execution(&self, reason: impl Into<String>) -> ExecutionPlanError {
        ExecutionPlanError::InvalidRouteExecution {
            method: self.method,
            path: self.path.clone(),
            reason: reason.into(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{
        Application, ExecutionMode, ExecutionPlanError, Method, OperationKind, Route,
        EXECUTION_PLAN_VERSION,
    };

    #[test]
    fn application_records_routes() {
        let mut app = Application::new("hello");
        app.add_route(Route::new(Method::Get, "/hello", "hello"));

        assert_eq!(app.name(), "hello");
        assert_eq!(app.plan_version(), Some(EXECUTION_PLAN_VERSION));
        assert_eq!(app.routes().len(), 1);
        assert_eq!(app.routes()[0].method().as_str(), "GET");
        assert_eq!(app.routes()[0].path(), "/hello");
    }

    #[test]
    fn route_can_mark_python_handler() {
        let route = Route::with_python_handler(Method::Post, "/echo", "echo");

        assert!(route.python_handler());
        assert!(route.native_response().is_none());
        assert_eq!(route.execution_mode(), ExecutionMode::Hybrid);
        assert_eq!(
            route.execution().expect("execution").operation(),
            OperationKind::PythonHandler
        );
    }

    #[test]
    fn legacy_definition_without_execution_plan_stays_compatible() {
        let application: Application = serde_json::from_str(
            r#"{"name":"legacy","routes":[{"method":"POST","path":"/echo","handler":"echo","python_handler":true}]}"#,
        )
        .expect("legacy application definition");

        assert_eq!(application.plan_version(), None);
        application.validate().expect("valid legacy plan");
        assert_eq!(
            application.routes()[0].execution_mode(),
            ExecutionMode::Hybrid
        );
    }

    #[test]
    fn execution_plan_deserializes_explicit_route_decision() {
        let application: Application = serde_json::from_str(
            r#"{"plan_version":1,"name":"planned","routes":[{"method":"GET","path":"/health","handler":"health","native_response":{"ok":true},"execution":{"mode":"native","operation":"static_response","reason":"static_response"}}]}"#,
        )
        .expect("versioned application definition");

        let execution = application.routes()[0].execution().expect("execution");
        assert_eq!(execution.mode(), ExecutionMode::Native);
        assert_eq!(execution.operation(), OperationKind::StaticResponse);
        assert_eq!(execution.reason(), "static_response");
        application.validate().expect("valid plan");
    }

    #[test]
    fn execution_plan_rejects_unknown_version() {
        let application: Application =
            serde_json::from_str(r#"{"plan_version":2,"name":"future","routes":[]}"#)
                .expect("application definition");

        assert_eq!(
            application.validate(),
            Err(ExecutionPlanError::UnsupportedVersion {
                found: 2,
                supported: EXECUTION_PLAN_VERSION,
            })
        );
    }

    #[test]
    fn execution_plan_rejects_contradictory_route() {
        let application: Application = serde_json::from_str(
            r#"{"plan_version":1,"name":"broken","routes":[{"method":"GET","path":"/health","handler":"health","execution":{"mode":"native","operation":"python_handler","reason":"broken"}}]}"#,
        )
        .expect("application definition");

        assert!(matches!(
            application.validate(),
            Err(ExecutionPlanError::InvalidRouteExecution { .. })
        ));
    }
    #[test]
    fn reject_missing_and_conflicting_execution_metadata() {
        let valid = serde_json::json!({
            "plan_version": 1, "name": "test", "routes": [{
                "method": "GET", "path": "/hello", "handler": "hello",
                "execution": {"mode": "hybrid", "operation": "python_handler", "reason": "automatic"}
            }]
        });
        let app: Application = serde_json::from_value(valid.clone()).unwrap();
        app.validate().unwrap();
        for case in 0..7 {
            let mut value = valid.clone();
            match case {
                0 => {
                    value["routes"][0]
                        .as_object_mut()
                        .unwrap()
                        .remove("execution");
                }
                1 => {
                    value.as_object_mut().unwrap().remove("plan_version");
                }
                2 => {
                    value["routes"][0]["python_handler"] = false.into();
                }
                3 => {
                    value["routes"][0]["execution"]["mode"] = "python_fallback".into();
                }
                4 => {
                    value["routes"][0]["execution"]["reason"] = " ".into();
                }
                5 => {
                    value["routes"][0]["native_response"] = serde_json::json!({"ignored": true});
                }
                6 => {
                    value["plan_version"] = 0.into();
                }
                _ => unreachable!(),
            }
            let app: Application = serde_json::from_value(value).unwrap();
            assert!(app.validate().is_err(), "case {case}");
        }
    }

    #[test]
    fn reject_unknown_fields_and_null_version() {
        for value in [
            serde_json::json!({"plan_version": null, "name": "test"}),
            serde_json::json!({"plan_versoin": 1, "name": "test"}),
            serde_json::json!({"name": "test", "routes": [{"method": "GET", "path": "/", "handler": "h", "executoin": {}}]}),
        ] {
            assert!(serde_json::from_value::<Application>(value).is_err());
        }
    }

    #[test]
    fn legacy_and_current_plans_survive_roundtrip() {
        let legacy: Application = serde_json::from_value(serde_json::json!({
            "name": "legacy", "routes": [{"method": "GET", "path": "/", "handler": "h"}]
        }))
        .unwrap();
        let mut current = Application::new("current");
        current.add_route(Route::with_python_handler(Method::Get, "/", "h"));
        current.add_route(Route::with_native_response(
            Method::Get,
            "/static",
            "s",
            serde_json::json!({"ok": true}),
        ));
        for app in [legacy, current] {
            app.validate().unwrap();
            let restored: Application =
                serde_json::from_str(&serde_json::to_string(&app).unwrap()).unwrap();
            restored.validate().unwrap();
            assert_eq!(app, restored);
        }
    }
}
