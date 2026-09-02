"""Public Python API for Silta.

The bootstrap package provides a minimal application description DSL. It does
not start a server, connect to Rust, or implement persistence yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, TypeAlias, TypeVar

Handler: TypeAlias = Callable[..., Any]
Method: TypeAlias = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
HandlerT = TypeVar("HandlerT", bound=Handler)


@dataclass(frozen=True, slots=True)
class Route:
    """A route declared through the Python DSL."""

    method: Method
    path: str
    handler: Handler
    native_response: Any | None = None
    python_handler: bool = False


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
        python: bool = False,
    ) -> Callable[[HandlerT], HandlerT]:
        """Register a handler function as application metadata."""

        self._validate_path(path)
        if python and (response is not None or native_response is not None):
            raise ValueError("python routes cannot also define a native response")
        route_response = native_response if native_response is not None else response

        def decorator(handler: HandlerT) -> HandlerT:
            self._routes.append(
                Route(
                    method=method,
                    path=path,
                    handler=handler,
                    native_response=route_response,
                    python_handler=python,
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
        python: bool = False,
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
        python: bool = False,
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
        python: bool = False,
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
        python: bool = False,
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
        python: bool = False,
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
        python: bool = False,
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
        python: bool = False,
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
            "name": self.name,
            "routes": [self._describe_route(route) for route in self._routes],
        }

    @staticmethod
    def _describe_route(route: Route) -> dict[str, Any]:
        description: dict[str, Any] = {
            "method": route.method,
            "path": route.path,
            "handler": route.handler.__qualname__,
        }

        if route.native_response is not None:
            description["native_response"] = route.native_response
        if route.python_handler:
            description["python_handler"] = True
        return description

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


__all__ = ["App", "Route"]
