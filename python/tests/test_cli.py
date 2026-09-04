import contextlib
import io
import signal
import subprocess
import unittest
from unittest.mock import Mock, patch

from silta.cli import _AsyncRunner, _handle_bridge_line, _wait_for_child


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


if __name__ == "__main__":
    unittest.main()
