import contextlib
import asyncio
import json
import io
import signal
import subprocess
import unittest
from unittest.mock import Mock, patch

from silta import App
from silta.cli import (
    _AsyncRunner,
    _bridge,
    _encode_bridge_response,
    _handle_bridge_line,
    _wait_for_child,
)


class WaitForChildTests(unittest.TestCase):
    def test_sigterm_is_forwarded_to_child(self) -> None:
        process = Mock(spec=subprocess.Popen)
        process.poll.return_value = None

        with patch("signal.signal") as set_signal, patch("signal.getsignal", return_value=None):
            handlers = {}

            def capture_handler(signum: int, handler: object) -> None:
                handlers[signum] = handler

            def wait() -> int:
                if process.wait.call_count == 1:
                    handlers[signal.SIGTERM](signal.SIGTERM, None)
                return 0

            process.wait.side_effect = wait
            set_signal.side_effect = capture_handler

            result = _wait_for_child(process)

        self.assertEqual(result, 0)
        process.send_signal.assert_called_once_with(signal.SIGTERM)
        self.assertIn(signal.SIGTERM, handlers)


class BridgeWorkerTests(unittest.TestCase):
    def test_bridge_line_calls_handler_with_body(self) -> None:
        def echo(request: dict[str, object]) -> dict[str, object]:
            return {"payload": request["body"]}

        response = _handle_bridge_line(
            '{"id":1,"handler":"echo","body":{"ok":true}}',
            {"echo": echo},
            _AsyncRunner(),
        )

        self.assertEqual(response, {"id": 1, "status": 200, "body": {"payload": {"ok": True}}})

    def test_bridge_line_redirects_handler_stdout_to_stderr(self) -> None:
        def noisy() -> dict[str, object]:
            print("handler noise")
            return {"ok": True}

        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            response = _handle_bridge_line(
                '{"id":1,"handler":"noisy","body":null}',
                {"noisy": noisy},
                _AsyncRunner(),
            )

        self.assertEqual(response, {"id": 1, "status": 200, "body": {"ok": True}})
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("handler noise", stderr.getvalue())

    def test_unserializable_handler_result_becomes_error_response(self) -> None:
        response = {"id": 7, "status": 200, "body": {"unsupported"}}

        encoded = _encode_bridge_response(response)

        self.assertIn('"id":7', encoded)
        self.assertIn('"status":500', encoded)
        self.assertIn("cannot be serialized", encoded)

    def test_non_finite_number_becomes_error_response(self) -> None:
        response = {"id": 8, "status": 200, "body": float("nan")}

        encoded = _encode_bridge_response(response)

        self.assertIn('"id":8', encoded)
        self.assertIn('"status":500', encoded)
        self.assertNotIn("NaN", encoded)

    def test_bridge_survives_unserializable_handler_result(self) -> None:
        app = App()

        @app.get("/broken")
        def broken() -> set[str]:
            return {"unsupported"}

        handler_name = app.routes[0].handler.__qualname__
        stdin = io.StringIO(
            f'{{"id":1,"handler":"{handler_name}","body":null}}\n'
            f'{{"id":2,"handler":"{handler_name}","body":null}}\n'
        )
        stdout = io.StringIO()

        with (
            patch("silta.cli._load_app", return_value=app),
            patch("sys.stdin", stdin),
            contextlib.redirect_stdout(stdout),
        ):
            result = _bridge("ignored:app")

        self.assertEqual(result, 0)
        lines = stdout.getvalue().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn('"id":1', lines[0])
        self.assertIn('"status":500', lines[0])
        self.assertIn('"id":2', lines[1])

    def test_bridge_closes_channel_on_malformed_protocol_line(self) -> None:
        app = App()

        @app.get("/ok")
        def ok() -> dict[str, bool]:
            return {"ok": True}

        handler_name = app.routes[0].handler.__qualname__
        stdin = io.StringIO(
            'not-json\n'
            f'{{"id":2,"handler":"{handler_name}","body":null}}\n'
        )
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch("silta.cli._load_app", return_value=app),
            patch("sys.stdin", stdin),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            result = _bridge("ignored:app")

        self.assertEqual(result, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("bridge error", stderr.getvalue())


class BridgeRegressionTests(unittest.TestCase):
    def test_async_requests_reuse_loop_and_resources(self):
        loops = []
        future = None

        async def handler():
            nonlocal future
            loop = asyncio.get_running_loop()
            loops.append(loop)
            if future is None:
                future = loop.create_future()
                loop.call_soon(future.set_result, 42)
            return await future

        with _AsyncRunner() as runner:
            for request_id in (1, 2):
                response = _handle_bridge_line(
                    json.dumps({"id": request_id, "handler": "handler"}),
                    {"handler": handler}, runner,
                )
                self.assertEqual(response["status"], 200)
                self.assertEqual(response["body"], 42)
        self.assertIs(loops[0], loops[1])
        self.assertTrue(loops[0].is_closed())

    def test_invalid_protocol_envelope_is_rejected(self):
        for value in ([], None, {}, {"id": True, "handler": "h"},
                      {"id": -1, "handler": "h"}, {"id": 2**64, "handler": "h"},
                      {"id": 1, "handler": []}, {"id": 1, "handler": ""}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _handle_bridge_line(json.dumps(value), {}, _AsyncRunner())

    def test_serialization_failures_preserve_response_id(self):
        deep = []
        for _ in range(2000):
            deep = [deep]
        cyclic = []
        cyclic.append(cyclic)
        for body in (deep, cyclic, "\ud800", float("inf"), object()):
            with self.subTest(kind=type(body).__name__):
                response = json.loads(_encode_bridge_response(
                    {"id": 42, "status": 200, "body": body}
                ))
                self.assertEqual(response["id"], 42)
                self.assertEqual(response["status"], 500)
                self.assertNotIn("detail", response["body"])

    def test_worker_rejects_ambiguous_handler_names(self):
        app = App()
        def make_handler():
            def handler():
                return {"ok": True}
            return handler
        app.get("/a")(make_handler())
        app.get("/b")(make_handler())
        stderr = io.StringIO()
        with patch("silta.cli._load_app", return_value=app), contextlib.redirect_stderr(stderr):
            self.assertEqual(_bridge("ignored:app"), 1)
        self.assertIn("ambiguous Python handler", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
