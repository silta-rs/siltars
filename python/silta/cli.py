"""Command line interface for the Silta bootstrap package."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
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
    dev_parser.add_argument("--port", default="8000", help="Port to bind.")
    dev_parser.add_argument(
        "--database-url",
        default=None,
        help="PostgreSQL URL for native database routes. Defaults to DATABASE_URL.",
    )
    dev_parser.add_argument(
        "--runtime-bin",
        default=None,
        help="Path to the silta-runtime binary. Defaults to SILTA_RUNTIME_BIN or packaged binary.",
    )

    args = parser.parse_args(argv)

    if args.command == "inspect":
        return _inspect(args.target)

    if args.command == "dev":
        return _dev(
            target=args.target,
            host=args.host,
            port=args.port,
            database_url=args.database_url,
            runtime_bin=args.runtime_bin,
        )

    parser.error(f"unknown command: {args.command}")
    return 2


def _inspect(target: str) -> int:
    try:
        app = _load_app(target)
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(json.dumps(app.describe(), indent=2, sort_keys=True))
    return 0


def _dev(
    *,
    target: str,
    host: str,
    port: str,
    database_url: str | None,
    runtime_bin: str | None,
) -> int:
    try:
        app = _load_app(target)
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
        json.dump(app.describe(), definition, sort_keys=True)
        definition_path = definition.name

    command = [
        str(binary),
        "--host",
        host,
        "--port",
        port,
        "--definition",
        definition_path,
    ]
    if database_url is not None:
        command.extend(["--database-url", database_url])

    env = os.environ.copy()
    process = subprocess.Popen(command, env=env)
    try:
        return process.wait()
    except KeyboardInterrupt:
        process.send_signal(signal.SIGINT)
        return process.wait()
    finally:
        try:
            Path(definition_path).unlink()
        except FileNotFoundError:
            pass


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
