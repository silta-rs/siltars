import signal
import subprocess
import unittest
from unittest.mock import Mock, patch

from silta.cli import _wait_for_child


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


if __name__ == "__main__":
    unittest.main()
