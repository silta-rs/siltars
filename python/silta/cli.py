"""Command line interface for the Silta bootstrap package."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import importlib
import importlib.util
import inspect
import json
import os
import signal
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from silta import App
from silta._json import validate_json


class _ForwardedSignal(Exception):
    def __init__(self, signum: int) -> None:
        super().__init__(signum)
        self.signum = signum


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="silta",
        description="Silta bootstrap CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Load a Python app and print its application definition.",
    )
    inspect_parser.add_argument(
        "target",
        help="Application target, for example app:app or path/to/app.py:app.",
    )

    dev_parser = subparsers.add_parser(
        "dev",
        help="Start the development runtime once the Rust runtime exists.",
    )
    dev_parser.add_argument(
        "target",
        help="Application target, for example app:app or path/to/app.py:app.",
    )
    dev_parser.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    dev_parser.add_argument("--request-timeout-ms", default=None,
                             help="Request deadline in milliseconds (default: SILTA_REQUEST_TIMEOUT_MS or 30000).")
    dev_parser.add_argument("--port", default="8000", help="Port to bind.")
    dev_parser.add_argument(
        "--database-url",
        default=None,
        help="PostgreSQL URL for native database routes. Defaults to DATABASE_URL.",
    )
    dev_parser.add_argument(
        "--db-min-connections",
        default=None,
        help="Minimum native database pool connections.",
    )
    dev_parser.add_argument(
        "--db-max-connections",
        default=None,
        help="Maximum native database pool connections.",
    )
    dev_parser.add_argument(
        "--db-acquire-timeout-ms",
        default=None,
        help="Native database pool acquire timeout in milliseconds.",
    )
    dev_parser.add_argument(
        "--runtime-bin",
        default=None,
        help="Path to the silta-runtime binary. Defaults to SILTA_RUNTIME_BIN or packaged binary.",
    )

    bridge_parser = subparsers.add_parser(
        "_bridge",
        help=argparse.SUPPRESS,
    )
    bridge_parser.add_argument("target")
    bridge_parser.add_argument("--ready", action="store_true", help=argparse.SUPPRESS)

    args = parser.parse_args(argv)

    if args.command == "inspect":
        return _inspect(args.target)

    if args.command == "dev":
        return _dev(
            target=args.target,
            host=args.host,
            port=args.port,
            database_url=args.database_url,
            db_min_connections=args.db_min_connections,
            db_max_connections=args.db_max_connections,
            db_acquire_timeout_ms=args.db_acquire_timeout_ms,
            runtime_bin=args.runtime_bin,
            request_timeout_ms=args.request_timeout_ms,
        )

    if args.command == "_bridge":
        # Isolate the protocol before importing any application/native library.
        # FD 1 (including C stdio and inherited subprocess output) becomes a log
        # stream; only this private, non-inheritable duplicate carries replies.
        sys.stdout.flush()
        protocol_fd = os.dup(1)
        os.set_inheritable(protocol_fd, False)
        try:
            os.dup2(2, 1)
            protocol = os.fdopen(protocol_fd, "w", encoding="utf-8", buffering=1)
        except BaseException:
            os.close(protocol_fd)
            raise
        with protocol:
            return _bridge(args.target, protocol_output=protocol, announce_ready=args.ready)

    parser.error(f"unknown command: {args.command}")
    return 2


def _inspect(target: str) -> int:
    try:
        app = _load_app(target)
        description = app.describe()
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(json.dumps(description, indent=2, sort_keys=True, allow_nan=False))
    return 0


def _dev(
    *,
    target: str,
    host: str,
    port: str,
    database_url: str | None,
    db_min_connections: str | None,
    db_max_connections: str | None,
    db_acquire_timeout_ms: str | None,
    runtime_bin: str | None,
    request_timeout_ms: str | None = None,
) -> int:
    try:
        app = _load_app(target)
        description = app.describe()
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    binary = _find_runtime_binary(runtime_bin)
    if binary is None:
        print(
            "error: silta-runtime binary was not found. Build it with "
            "`cargo build -p silta-runtime` or set SILTA_RUNTIME_BIN.",
            file=sys.stderr,
        )
        return 2

    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", prefix="silta-app-", suffix=".json", delete=False
    ) as definition:
        json.dump(description, definition, sort_keys=True, allow_nan=False)
        definition_path = definition.name

    command = [
        str(binary),
        "--host",
        host,
        "--port",
        port,
        "--definition",
        definition_path,
        "--python-bridge-executable",
        sys.executable,
        "--python-bridge-target",
        target,
    ]
    if request_timeout_ms is not None:
        command.extend(["--request-timeout-ms", request_timeout_ms])
    if database_url is not None:
        command.extend(["--database-url", database_url])
    if db_min_connections is not None:
        command.extend(["--db-min-connections", db_min_connections])
    if db_max_connections is not None:
        command.extend(["--db-max-connections", db_max_connections])
    if db_acquire_timeout_ms is not None:
        command.extend(["--db-acquire-timeout-ms", db_acquire_timeout_ms])

    env = os.environ.copy()
    process = subprocess.Popen(command, env=env)
    try:
        return _wait_for_child(process)
    finally:
        try:
            Path(definition_path).unlink()
        except FileNotFoundError:
            pass


def _wait_for_child(process: subprocess.Popen[Any]) -> int:
    signal_names = ["SIGINT", "SIGTERM", "SIGHUP"]
    previous_handlers: dict[int, Any] = {}

    def forward_signal(signum: int, _frame: Any) -> None:
        if process.poll() is None:
            process.send_signal(signum)
        raise _ForwardedSignal(signum)

    for signal_name in signal_names:
        signum = getattr(signal, signal_name, None)
        if signum is None:
            continue
        previous_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, forward_signal)

    try:
        return process.wait()
    except _ForwardedSignal:
        return process.wait()
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def _bridge(target: str, *, protocol_output: Any = None, announce_ready: bool = False) -> int:
    try:
        with contextlib.redirect_stdout(sys.stderr):
            app = _load_app(target)
        handlers: dict[str, Any] = {}
        for route in app.routes:
            if not route.python_handler:
                continue
            name = route.handler.__qualname__
            if name in handlers and handlers[name] is not route.handler:
                raise ValueError(f"ambiguous Python handler name: {name}")
            handlers[name] = route.handler
        if announce_ready:
            print('{"ready":1}', file=protocol_output, flush=True)
        with _AsyncRunner() as asyncio_runner:
            for line in sys.stdin:
                # A malformed protocol request must close the channel, so Rust
                # observes EOF instead of waiting forever for a skipped reply.
                response = _handle_bridge_line(line, handlers, asyncio_runner)
                print(_encode_bridge_response(response), file=protocol_output, flush=True)
        return 0
    except Exception as error:
        print(f"bridge error: {error}", file=sys.stderr)
        return 1


class _AsyncRunner:
    """One event loop per worker, preserving async resources between requests."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None

    def __enter__(self) -> _AsyncRunner:
        return self

    def __exit__(self, *_exc: Any) -> None:
        if self._loop is None:
            return
        with contextlib.redirect_stdout(sys.stderr):
            try:
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                self._loop.run_until_complete(self._loop.shutdown_asyncgens())
                self._loop.run_until_complete(self._loop.shutdown_default_executor())
            finally:
                self._loop.close()
                self._loop = None

    def run(self, value: Any) -> Any:
        if not inspect.isawaitable(value):
            return value
        if self._loop is None:
            self._loop = asyncio.new_event_loop()

        async def await_value() -> Any:
            return await value

        return self._loop.run_until_complete(await_value())


def _handle_bridge_line(
    line: str, handlers: dict[str, Any], asyncio_runner: _AsyncRunner
) -> dict[str, Any]:
    request = json.loads(line)
    if not isinstance(request, dict):
        raise ValueError("bridge request must be an object")
    request_id = request.get("id")
    handler_name = request.get("handler")
    if type(request_id) is not int or not 0 <= request_id < 2**64:
        raise ValueError("bridge id must be an unsigned 64-bit integer")
    if not isinstance(handler_name, str) or not handler_name:
        raise ValueError("bridge handler must be a nonempty string")
    handler = handlers.get(handler_name)
    if handler is None:
        return {
            "id": request_id,
            "status": 500,
            "body": {"error": f"python handler not found: {handler_name}"},
        }

    bridge_request = {
        "body": request.get("body"),
    }
    try:
        with contextlib.redirect_stdout(sys.stderr):
            signature = inspect.signature(handler)
            result = handler(bridge_request) if signature.parameters else handler()
            body = asyncio_runner.run(result)
        return {
            "id": request_id,
            "status": 200,
            "body": body,
        }
    except Exception as error:
        return {
            "id": request_id,
            "status": 500,
            "body": {"error": str(error)},
        }


def _encode_bridge_response(response: dict[str, Any]) -> str:
    """Serialize one response without allowing application data to kill the worker."""

    try:
        validate_json(response)
        encoded = json.dumps(response, separators=(",", ":"), allow_nan=False, ensure_ascii=False)
        encoded.encode("utf-8")  # Reject unpaired surrogates before writing a reply.
        return encoded
    except (TypeError, ValueError, RecursionError, OverflowError) as error:
        print(f"bridge response serialization failed: {type(error).__name__}", file=sys.stderr)
        fallback = {
            "id": response.get("id", 0),
            "status": 500,
            "body": {
                "error": "python handler returned a value that cannot be serialized",
            },
        }
        return json.dumps(fallback, separators=(",", ":"), allow_nan=False)


def _find_runtime_binary(explicit: str | None) -> Path | None:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))

    env_value = os.environ.get("SILTA_RUNTIME_BIN")
    if env_value:
        candidates.append(Path(env_value))

    package_root = Path(__file__).resolve().parent
    executable_name = "silta-runtime.exe" if sys.platform == "win32" else "silta-runtime"
    candidates.append(package_root / "bin" / executable_name)

    for parent in package_root.parents:
        candidates.append(parent / "target" / "debug" / executable_name)
        candidates.append(parent / "target" / "release" / executable_name)

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    return None


def _load_app(target: str) -> App:
    module_ref, separator, attribute = target.partition(":")
    if not separator or not module_ref or not attribute:
        raise ValueError("target must use module:attribute or path.py:attribute format")

    module = _load_module(module_ref)
    value: Any = module

    for part in attribute.split("."):
        value = getattr(value, part)

    if not isinstance(value, App):
        raise TypeError(f"{target} did not resolve to a silta.App instance")

    return value


def _load_module(module_ref: str) -> Any:
    path = Path(module_ref)

    if module_ref.endswith(".py") or path.exists():
        if not path.exists():
            raise FileNotFoundError(f"application file not found: {module_ref}")
        if path.suffix != ".py":
            raise ValueError("file targets must point to a .py file")

        module_name = f"_silta_app_{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"could not load application file: {module_ref}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    return importlib.import_module(module_ref)


if __name__ == "__main__":
    raise SystemExit(main())
