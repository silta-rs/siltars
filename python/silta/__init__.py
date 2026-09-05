"""Public Python API for Silta.

The package records route declarations and emits a versioned execution plan
for the Rust runtime. Arbitrary Python code is not compiled into Rust.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import Any, Callable, Literal, TypeAlias, TypeVar

Handler: TypeAlias = Callable[..., Any]
Method: TypeAlias = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
HandlerT = TypeVar("HandlerT", bound=Handler)
EXECUTION_PLAN_VERSION = 1


class ExecutionMode(str, Enum):
    """Where a prepared route executes at request time."""

    NATIVE = "native"
    HYBRID = "hybrid"
    PYTHON_FALLBACK = "python_fallback"


class OperationKind(str, Enum):
    """The operation currently attached to a route execution plan."""

    STATIC_RESPONSE = "static_response"
    PYTHON_HANDLER = "python_handler"
    LEGACY_SYMBOLIC = "legacy_symbolic"


@dataclass(frozen=True, slots=True)
class RouteExecution:
    """A versioned runtime decision produced from a Python route declaration."""

    mode: ExecutionMode
    operation: OperationKind
    reason: str

    def describe(self) -> dict[str, str]:
        """Return the serializable route execution contract."""

        return {
            "mode": self.mode.value,
            "operation": self.operation.value,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class Route:
    """A route declared through the Python DSL."""

    method: Method
    path: str
    handler: Handler
    native_response: Any | None = None
    python_handler: bool = False
    execution: RouteExecution | None = None

    def __post_init__(self) -> None:
        # Direct Route construction retains the original Pre-Alpha signature.
        execution = self.execution
        if execution is None:
            execution = App._select_execution(
                native_response=self.native_response, python=self.python_handler
            )
            object.__setattr__(self, "execution", execution)
        if execution.mode is ExecutionMode.PYTHON_FALLBACK:
            raise ValueError("python_fallback is not implemented")
        if self.python_handler != (execution.mode is ExecutionMode.HYBRID):
            raise ValueError("python_handler conflicts with execution mode")
        if self.python_handler and self.native_response is not None:
            raise ValueError("python routes cannot also define a native response")


class App:
    """A minimal Silta application description.

    App records route metadata for a future Rust runtime boundary. It does not
    execute requests in Python.
    """

    def __init__(self, *, name: str = "silta") -> None:
        self.name = name
        self._routes: list[Route] = []

    @property
    def routes(self) -> tuple[Route, ...]:
        """Return declared routes as immutable metadata."""

        return tuple(self._routes)

    def route(
        self,
        method: Method,
        path: str,
        *,
        response: Any | None = None,
        native_response: Any | None = None,
        python: bool | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        """Register a handler function as application metadata."""

        self._validate_path(path)
        if python is True and (response is not None or native_response is not None):
            raise ValueError("python routes cannot also define a native response")
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}:
            raise ValueError(f"unsupported HTTP method: {method}")
        if python is not None and type(python) is not bool:
            raise TypeError("python must be True, False, or None")
        route_response = native_response if native_response is not None else response
        if route_response is not None:
            json.dumps(route_response, allow_nan=False)

        def decorator(handler: HandlerT) -> HandlerT:
            self._routes.append(
                Route(
                    method=method,
                    path=path,
                    handler=handler,
                    native_response=route_response,
                    python_handler=route_response is None and python is not False,
                    execution=self._select_execution(
                        native_response=route_response,
                        python=python,
                    ),
                )
            )
            return handler

        return decorator

    def get(
        self,
        path: str,
        *,
        response: Any | None = None,
        native_response: Any | None = None,
        python: bool | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        """Register a GET route."""

        return self.route(
            "GET",
            path,
            response=response,
            native_response=native_response,
            python=python,
        )

    def post(
        self,
        path: str,
        *,
        response: Any | None = None,
        native_response: Any | None = None,
        python: bool | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        """Register a POST route."""

        return self.route(
            "POST",
            path,
            response=response,
            native_response=native_response,
            python=python,
        )

    def put(
        self,
        path: str,
        *,
        response: Any | None = None,
        native_response: Any | None = None,
        python: bool | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        """Register a PUT route."""

        return self.route(
            "PUT",
            path,
            response=response,
            native_response=native_response,
            python=python,
        )

    def patch(
        self,
        path: str,
        *,
        response: Any | None = None,
        native_response: Any | None = None,
        python: bool | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        """Register a PATCH route."""

        return self.route(
            "PATCH",
            path,
            response=response,
            native_response=native_response,
            python=python,
        )

    def delete(
        self,
        path: str,
        *,
        response: Any | None = None,
        native_response: Any | None = None,
        python: bool | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        """Register a DELETE route."""

        return self.route(
            "DELETE",
            path,
            response=response,
            native_response=native_response,
            python=python,
        )

    def options(
        self,
        path: str,
        *,
        response: Any | None = None,
        native_response: Any | None = None,
        python: bool | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        """Register an OPTIONS route."""

        return self.route(
            "OPTIONS",
            path,
            response=response,
            native_response=native_response,
            python=python,
        )

    def head(
        self,
        path: str,
        *,
        response: Any | None = None,
        native_response: Any | None = None,
        python: bool | None = None,
    ) -> Callable[[HandlerT], HandlerT]:
        """Register a HEAD route."""

        return self.route(
            "HEAD",
            path,
            response=response,
            native_response=native_response,
            python=python,
        )

    def describe(self) -> dict[str, Any]:
        """Return a serializable description of the current application."""

        return {
            "plan_version": EXECUTION_PLAN_VERSION,
            "name": self.name,
            "routes": [self._describe_route(route) for route in self._routes],
        }

    @staticmethod
    def _describe_route(route: Route) -> dict[str, Any]:
        assert route.execution is not None
        description: dict[str, Any] = {
            "method": route.method,
            "path": route.path,
            "handler": route.handler.__qualname__,
            "execution": route.execution.describe(),
        }

        if route.native_response is not None:
            description["native_response"] = route.native_response
        if route.python_handler:
            # Kept during the protocol transition so the ExecutionPlan remains
            # safe to consume with the Pre-Alpha runtime from older releases.
            description["python_handler"] = True
        return description

    @staticmethod
    def _select_execution(
        *, native_response: Any | None, python: bool | None
    ) -> RouteExecution:
        if native_response is not None:
            return RouteExecution(
                mode=ExecutionMode.NATIVE,
                operation=OperationKind.STATIC_RESPONSE,
                reason="static_response",
            )
        if python is False:
            return RouteExecution(
                mode=ExecutionMode.NATIVE,
                operation=OperationKind.LEGACY_SYMBOLIC,
                reason="explicit_legacy_native_handler",
            )
        return RouteExecution(
            mode=ExecutionMode.HYBRID,
            operation=OperationKind.PYTHON_HANDLER,
            reason=(
                "explicit_python_handler"
                if python is True
                else "automatic_python_handler"
            ),
        )

    @staticmethod
    def _validate_path(path: str) -> None:
        if not path.startswith("/"):
            raise ValueError("route paths must start with '/'")
        if "{" not in path and "}" not in path:
            return

        for segment in path.split("/"):
            if not segment:
                continue
            if "{" not in segment and "}" not in segment:
                continue
            if not (segment.startswith("{") and segment.endswith("}")):
                raise ValueError(
                    "route parameters must be complete path segments like '{id}'"
                )
            parameter_name = segment[1:-1]
            if (
                not parameter_name
                or parameter_name[0].isdigit()
                or not all(
                    character == "_" or character.isascii() and character.isalnum()
                    for character in parameter_name
                )
            ):
                raise ValueError("route parameter names must be valid identifiers")


__all__ = [
    "App",
    "EXECUTION_PLAN_VERSION",
    "ExecutionMode",
    "OperationKind",
    "Route",
    "RouteExecution",
]
