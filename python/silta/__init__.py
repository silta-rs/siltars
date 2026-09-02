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

    def route(self, method: Method, path: str) -> Callable[[HandlerT], HandlerT]:
        """Register a handler function as application metadata."""

        self._validate_path(path)

        def decorator(handler: HandlerT) -> HandlerT:
            self._routes.append(Route(method=method, path=path, handler=handler))
            return handler

        return decorator

    def get(self, path: str) -> Callable[[HandlerT], HandlerT]:
        """Register a GET route."""

        return self.route("GET", path)

    def post(self, path: str) -> Callable[[HandlerT], HandlerT]:
        """Register a POST route."""

        return self.route("POST", path)

    def put(self, path: str) -> Callable[[HandlerT], HandlerT]:
        """Register a PUT route."""

        return self.route("PUT", path)

    def patch(self, path: str) -> Callable[[HandlerT], HandlerT]:
        """Register a PATCH route."""

        return self.route("PATCH", path)

    def delete(self, path: str) -> Callable[[HandlerT], HandlerT]:
        """Register a DELETE route."""

        return self.route("DELETE", path)

    def options(self, path: str) -> Callable[[HandlerT], HandlerT]:
        """Register an OPTIONS route."""

        return self.route("OPTIONS", path)

    def head(self, path: str) -> Callable[[HandlerT], HandlerT]:
        """Register a HEAD route."""

        return self.route("HEAD", path)

    def describe(self) -> dict[str, Any]:
        """Return a serializable description of the current application."""

        return {
            "name": self.name,
            "routes": [
                {
                    "method": route.method,
                    "path": route.path,
                    "handler": route.handler.__qualname__,
                }
                for route in self._routes
            ],
        }

    @staticmethod
    def _validate_path(path: str) -> None:
        if not path.startswith("/"):
            raise ValueError("route paths must start with '/'")


__all__ = ["App", "Route"]
