"""Exercise the actual Rust HTTP server and Python subprocess together.

Set SILTA_RUNTIME_BIN to a built binary to enable this integration suite.
"""
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import threading
import unittest


APP = '''
import os, sys, subprocess, time, json
from pathlib import Path
from silta import App
import asyncio
app = App()
if "_bridge" in sys.argv:
    with Path(__file__).with_suffix(".workers").open("a") as log:
        log.write(str(os.getpid()) + "\\n")
    if Path(__file__).with_suffix(".fail-import").exists():
        os._exit(9)
    if Path(__file__).with_suffix(".hang-import").exists():
        time.sleep(60)
print("application startup log")
os.write(1, b"import-no-newline")

@app.get("/bounds", response={"min": -(2**63), "max": 2**64 - 1, "unicode": "Καλημέρα"})
def bounds():
    raise AssertionError("static response must not invoke Python")

@app.post("/native-noise")
def native_noise(request):
    os.write(1, b"native-no-newline")
    subprocess.run([sys.executable, "-c", "import os; os.write(1,b'child-no-newline')"], check=True)
    if sys.platform != "win32":
        import ctypes
        libc = ctypes.CDLL(None)
        libc.printf(b"libc-no-newline")
        libc.fflush(None)
    return {"ok": True}

@app.post("/blocking")
def blocking(request):
    marker = Path(request["body"]["marker"])
    temporary = marker.with_suffix(".tmp")
    temporary.write_text(json.dumps({"worker": os.getpid(), "runtime": os.getppid()}))
    temporary.replace(marker)
    time.sleep(request["body"].get("delay", 60))
    return {"done": True}

@app.get("/native", response={"native": True})
def native():
    raise AssertionError("static response must not execute Python")

@app.post("/echo-native", python=False)
def create_echo():
    raise AssertionError("native echo must run in Rust")

@app.post("/echo")
async def echo(request):
    print("handler log")
    return {"body": request["body"]}

@app.get("/worker-pid")
def worker_pid():
    return {"pid": os.getpid()}

@app.post("/close-protocol")
def close_protocol():
    os.closerange(3, 256)
    time.sleep(60)
    return {"done": True}

@app.post("/crash")
def crash():
    with Path(__file__).with_suffix(".crashes").open("a") as log:
        log.write("crash\\n")
    os._exit(7)

@app.post("/touch")
def touch(request):
    Path(request["body"]["marker"]).write_text("executed")
    return {"ok": True}

@app.post("/async-blocking")
async def async_blocking(request):
    Path(request["body"]["marker"]).write_text(str(os.getpid()))
    await asyncio.sleep(60)
    return {"done": True}

@app.get("/oversized")
def oversized():
    return "x" * (16 * 1024 * 1024)

@app.post("/wrong-id")
def wrong_id():
    os.write(3, b'{"id":999999,"status":200,"body":null}\\n')
    time.sleep(60)

@app.get("/loop")
async def loop():
    return {"loop": id(asyncio.get_running_loop())}

@app.get("/bad")
def bad():
    return {"unsupported"}

@app.get("/deep")
def deep():
    value = []
    for _ in range(100):
        value = [value]
    return value

@app.get("/surrogate")
def surrogate():
    return chr(0xd800)
'''


@unittest.skipUnless(os.environ.get("SILTA_RUNTIME_BIN"), "requires built Rust runtime")
class RuntimeServerTestCase(unittest.TestCase):
    timeout_ms = 30000
    app_source = APP
    ready_path = "/native"
    runtime_args = ()
    runtime_env = None

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        app_path = Path(cls.temp.name) / "app.py"
        cls.app_path = app_path
        app_path.write_text(cls.app_source, encoding="utf-8")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        cls.log = open(Path(cls.temp.name) / "server.log", "w+")
        cls.addClassCleanup(cls.log.close)
        cls.process = subprocess.Popen([
            sys.executable, "-m", "silta.cli", "dev", str(app_path) + ":app",
            "--port", str(cls.port), "--runtime-bin", os.environ["SILTA_RUNTIME_BIN"],
            "--request-timeout-ms", str(cls.timeout_ms),
        ] + list(cls.runtime_args), stdout=cls.log, stderr=cls.log, env=cls.runtime_env)
        cls.addClassCleanup(cls.stop_server)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if cls.process.poll() is not None:
                cls.log.seek(0)
                raise AssertionError("runtime exited: " + cls.log.read())
            try:
                cls.request("GET", cls.ready_path)
                break
            except OSError:
                time.sleep(0.05)
        else:
            raise AssertionError("runtime did not become ready within 20 seconds")

    @classmethod
    def stop_server(cls):
        if cls.process.poll() is None:
            cls.process.send_signal(signal.SIGINT)
            try:
                cls.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                cls.process.kill()
                cls.process.wait(timeout=5)
                raise AssertionError("runtime did not shut down on SIGINT")

    @classmethod
    def request(cls, method, path, body=None):
        connection = http.client.HTTPConnection("127.0.0.1", cls.port, timeout=5)
        try:
            connection.request(method, path, body, {"Content-Type": "application/json"})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()


class RuntimeIntegrationTests(RuntimeServerTestCase):
    def test_native_stdout_without_newline_cannot_corrupt_protocol(self):
        for _ in range(2):
            self.assertEqual(self.request("POST", "/native-noise", '{}'), (200, {"ok": True}))
            self.assertEqual(self.request("POST", "/echo", '{}'), (200, {"body": {}}))

    def test_static_integer_boundaries_and_unicode_are_exact(self):
        self.assertEqual(self.request("GET", "/bounds"),
                         (200, {"min": -(2**63), "max": 2**64 - 1, "unicode": "Καλημέρα"}))

    def test_native_response_avoids_handler(self):
        self.assertEqual(self.request("GET", "/native"), (200, {"native": True}))

    def test_async_handler_works_without_python_flag(self):
        self.assertEqual(self.request("POST", "/echo", '{"hello":"world"}'),
                         (200, {"body": {"hello": "world"}}))

    def test_loop_reused_across_http_requests(self):
        first = self.request("GET", "/loop")
        second = self.request("GET", "/loop")
        self.assertEqual(first[0], 200)
        self.assertEqual(first, second)

    def test_bad_json_does_not_break_subsequent_requests(self):
        self.assertEqual(self.request("POST", "/echo", '{broken')[0], 400)
        self.assertEqual(self.request("POST", "/echo", '{}'), (200, {"body": {}}))

    def test_bad_responses_do_not_desynchronize_worker(self):
        for path in ("/bad", "/deep", "/surrogate"):
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path)[0], 500)
                self.assertEqual(self.request("POST", "/echo", '{"ok":true}'),
                                 (200, {"body": {"ok": True}}))


@unittest.skipUnless(os.environ.get("SILTA_RUNTIME_BIN") and os.name == "posix", "requires Rust runtime and Unix signals")
class ShutdownIntegrationTests(unittest.TestCase):
    def test_sigterm_reaps_active_worker(self):
        for target in ("cli", "runtime"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temp:
                app = Path(temp) / "app.py"
                app.write_text(APP)
                marker = Path(temp) / "worker.json"
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", 0))
                    port = sock.getsockname()[1]
                with open(Path(temp) / "server.log", "w+") as log:
                    process = subprocess.Popen([
                        sys.executable, "-m", "silta.cli", "dev", str(app) + ":app",
                        "--port", str(port), "--runtime-bin", os.environ["SILTA_RUNTIME_BIN"],
                    ], stdout=log, stderr=log)
                    pids = {}
                    thread = None
                    def blocking_request():
                        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
                        try:
                            connection.request("POST", "/blocking", json.dumps({"marker": str(marker)}))
                            connection.getresponse().read()
                        except (OSError, http.client.HTTPException):
                            pass
                        finally:
                            connection.close()
                    try:
                        deadline = time.monotonic() + 10
                        while time.monotonic() < deadline:
                            try:
                                with socket.create_connection(("127.0.0.1", port), timeout=.1):
                                    break
                            except OSError:
                                time.sleep(.02)
                        else:
                            self.fail("server did not start")
                        thread = threading.Thread(target=blocking_request, daemon=True)
                        thread.start()
                        deadline = time.monotonic() + 5
                        while not marker.exists() and time.monotonic() < deadline:
                            time.sleep(.02)
                        self.assertTrue(marker.exists(), "handler did not start")
                        pids = json.loads(marker.read_text())
                        os.kill(process.pid if target == "cli" else pids["runtime"], signal.SIGTERM)
                        process.wait(timeout=12)
                        # The runtime must reap its child before it exits, including
                        # during an active call that owns the IPC mutex.
                        with self.assertRaises(ProcessLookupError):
                            os.kill(pids["worker"], 0)
                        with self.assertRaises(ProcessLookupError):
                            os.kill(pids["runtime"], 0)
                    finally:
                        for pid in (pids.get("worker"), pids.get("runtime"), process.pid):
                            if pid:
                                try:
                                    os.kill(pid, signal.SIGKILL)
                                except ProcessLookupError:
                                    pass
                        process.wait(timeout=5)
                        if thread:
                            thread.join(timeout=5)


@unittest.skipUnless(os.environ.get("SILTA_RUNTIME_BIN") and os.name == "posix", "requires Rust runtime and POSIX PID existence check")
class WorkerCrashIntegrationTests(RuntimeServerTestCase):
    exit_route = "/crash"

    def test_closed_worker_channel_is_reaped_before_http_error(self):
        status, body = self.request("GET", "/worker-pid")
        self.assertEqual(status, 200)
        worker_pid = body["pid"]
        self.assertEqual(self.request("POST", self.exit_route, '{}')[0], 500)
        # kill(pid, 0) also succeeds for zombies: require the PID to be gone,
        # not just a process whose state is no longer running.
        with self.assertRaises(ProcessLookupError):
            os.kill(worker_pid, 0)
        self.assertIsNone(self.process.poll(), "runtime must remain alive")
        self.assertEqual(self.request("GET", "/native"), (200, {"native": True}))
        status, body = self.request("GET", "/worker-pid")
        self.assertEqual(status, 200)
        self.assertNotEqual(body["pid"], worker_pid)
        self.assertEqual(self.request("POST", "/echo", '{"new":true}'),
                         (200, {"body": {"new": True}}))
        if self.exit_route == "/crash":
            self.assertEqual(self.app_path.with_suffix(".crashes").read_text(), "crash\n")


class WorkerClosedPipeIntegrationTests(WorkerCrashIntegrationTests):
    # EOF can precede process exit. Reaping must not block shutdown forever
    # while a handler that closed its protocol descriptor continues running.
    exit_route = "/close-protocol"


@unittest.skipUnless(os.environ.get("SILTA_RUNTIME_BIN") and os.name == "posix", "requires Rust runtime and POSIX")
class WorkerRecoveryIntegrationTests(RuntimeServerTestCase):
    timeout_ms = 1000

    def wait_until(self, predicate, message, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.02)
        self.fail(message)

    def assert_pid_gone(self, pid):
        def gone():
            try:
                os.kill(pid, 0)
                return False
            except ProcessLookupError:
                return True
        self.wait_until(gone, f"PID {pid} was not reaped")

    def test_sync_and_async_timeouts_restart_worker(self):
        for route in ("/blocking", "/async-blocking"):
            with self.subTest(route=route):
                pid = self.request("GET", "/worker-pid")[1]["pid"]
                marker = Path(self.temp.name) / "timeout-marker"
                started = time.monotonic()
                self.assertEqual(self.request("POST", route, json.dumps({"marker": str(marker)})),
                                 (504, {"error": "request deadline exceeded"}))
                self.assertLess(time.monotonic() - started, 3)
                self.assertTrue(marker.exists())
                self.assert_pid_gone(pid)
                status, body = self.request("GET", "/worker-pid")
                self.assertEqual(status, 200)
                self.assertNotEqual(body["pid"], pid)
                self.assertEqual(self.request("GET", "/native"), (200, {"native": True}))
                self.assertEqual(self.request("POST", "/echo", '{"after":"timeout"}'),
                                 (200, {"body": {"after": "timeout"}}))
                marker.unlink()

    def test_idle_crash_is_reaped_and_restarted_without_traffic(self):
        pid = self.request("GET", "/worker-pid")[1]["pid"]
        workers = self.app_path.with_suffix(".workers")
        count = len(workers.read_text().splitlines())
        os.kill(pid, signal.SIGKILL)
        self.assert_pid_gone(pid)
        self.wait_until(lambda: len(workers.read_text().splitlines()) > count,
                        "worker was not restarted without HTTP traffic")
        self.assertEqual(self.request("GET", "/worker-pid")[0], 200)

    def test_protocol_error_restarts_worker(self):
        pid = self.request("GET", "/worker-pid")[1]["pid"]
        self.assertEqual(self.request("POST", "/wrong-id", '{}')[0], 500)
        self.assert_pid_gone(pid)
        self.assertEqual(self.request("POST", "/echo", '{}'), (200, {"body": {}}))

    def test_partial_request_body_has_same_deadline(self):
        pid = self.request("GET", "/worker-pid")[1]["pid"]
        for path in ("/echo", "/echo-native"):
            # /echo-native is added as a native handler below: both execution
            # modes must time out during body extraction, before Python dispatch.
            with self.subTest(path=path), socket.create_connection(("127.0.0.1", self.port), timeout=4) as sock:
                sock.sendall(f"POST {path} HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: 100\r\n\r\n{{".encode())
                response = http.client.HTTPResponse(sock)
                response.begin()
                self.assertEqual(response.status, 504)
                response.read()
        self.assertEqual(self.request("GET", "/worker-pid"), (200, {"pid": pid}))

    def test_queued_deadline_does_not_execute_or_kill_next_worker(self):
        marker = Path(self.temp.name) / "queue-active"
        untouched = Path(self.temp.name) / "queue-expired"
        payload = json.dumps({"marker": str(untouched)}).encode()
        with socket.create_connection(("127.0.0.1", self.port), timeout=4) as sock:
            # Start the queued request's budget first, but hold its body until
            # another request owns the worker. It must expire before that owner.
            sock.sendall((f"POST /touch HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\n\r\n").encode())
            time.sleep(.25)
            with ThreadPoolExecutor(max_workers=1) as pool:
                active = pool.submit(self.request, "POST", "/blocking", json.dumps({"marker": str(marker)}))
                self.wait_until(marker.exists, "blocking request did not start")
                owner = json.loads(marker.read_text())["worker"]
                sock.sendall(payload)
                response = http.client.HTTPResponse(sock)
                response.begin()
                self.assertEqual(response.status, 504)
                response.read()
                os.kill(owner, 0)  # Expiry of waiting work must not kill its owner.
                self.assertEqual(active.result()[0], 504)
        self.assertEqual(self.request("POST", "/echo", '{}')[0], 200)
        self.assertFalse(untouched.exists(), "expired queued handler was executed")

    def test_queue_overload_is_bounded_and_native_remains_available(self):
        marker = Path(self.temp.name) / "overload-active"
        with ThreadPoolExecutor(max_workers=1) as pool:
            active = pool.submit(self.request, "POST", "/blocking", json.dumps({"marker": str(marker)}))
            self.wait_until(marker.exists, "blocking request did not start")
            sockets = []
            try:
                for _ in range(70):
                    sock = socket.create_connection(("127.0.0.1", self.port), timeout=4)
                    sockets.append(sock)
                    sock.sendall(b"POST /echo HTTP/1.1\r\nHost: localhost\r\nContent-Length: 2\r\nContent-Type: application/json\r\n\r\n{}")
                self.assertEqual(self.request("GET", "/native")[0], 200)
                statuses = []
                for sock in sockets:
                    response = http.client.HTTPResponse(sock)
                    response.begin()
                    statuses.append(response.status)
                    response.read()
                self.assertIn(503, statuses)
                self.assertTrue(set(statuses) <= {200, 503, 504}, statuses)
            finally:
                for sock in sockets:
                    sock.close()
            self.assertEqual(active.result()[0], 504)
        self.wait_until(lambda: self.request("POST", "/echo", '{}')[0] == 200,
                        "worker did not recover after overload")

    def test_repeated_import_crash_backs_off_then_recovers(self):
        pid = self.request("GET", "/worker-pid")[1]["pid"]
        workers = self.app_path.with_suffix(".workers")
        fail = self.app_path.with_suffix(".fail-import")
        before = len(workers.read_text().splitlines())
        fail.touch()
        try:
            os.kill(pid, signal.SIGKILL)
            self.wait_until(lambda: len(workers.read_text().splitlines()) >= before + 3,
                            "import failures not exercised")
            self.assert_pid_gone(pid)
            self.assertEqual(self.request("GET", "/native")[0], 200)
            self.assertEqual(self.request("POST", "/echo", '{}')[0], 504)
            self.assertLessEqual(len(workers.read_text().splitlines()) - before, 5)
        finally:
            fail.unlink()
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if self.request("POST", "/echo", '{}')[0] == 200:
                break
        else:
            self.fail("worker did not recover after import failure was removed")


@unittest.skipUnless(os.environ.get("SILTA_RUNTIME_BIN") and os.name == "posix", "requires Rust runtime and POSIX")
class ShutdownRecoveryIntegrationTests(RuntimeServerTestCase):
    def test_sigterm_during_restart_backoff_leaves_no_workers(self):
        pid = self.request("GET", "/worker-pid")[1]["pid"]
        workers = self.app_path.with_suffix(".workers")
        before = len(workers.read_text().splitlines())
        self.app_path.with_suffix(".fail-import").touch()
        os.kill(pid, signal.SIGKILL)
        deadline = time.monotonic() + 5
        while len(workers.read_text().splitlines()) < before + 3:
            self.assertLess(time.monotonic(), deadline, "restart backoff did not start")
            time.sleep(.02)
        self.process.send_signal(signal.SIGTERM)
        self.process.wait(timeout=7)
        for pid in map(int, workers.read_text().splitlines()):
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)


@unittest.skipUnless(os.environ.get("SILTA_RUNTIME_BIN") and os.name == "posix", "requires Rust runtime and POSIX")
class WorkerDisconnectIntegrationTests(RuntimeServerTestCase):
    def test_disconnect_cancels_active_call_before_request_deadline(self):
        import struct
        pid = self.request("GET", "/worker-pid")[1]["pid"]
        marker = Path(self.temp.name) / "disconnect-active"
        body = json.dumps({"marker": str(marker)}).encode()
        with socket.create_connection(("127.0.0.1", self.port), timeout=4) as sock:
            sock.sendall((f"POST /blocking HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n").encode() + body)
            deadline = time.monotonic() + 3
            while not marker.exists():
                self.assertLess(time.monotonic(), deadline, "handler did not start")
                time.sleep(.02)
            # Reset the connection so Hyper observes cancellation immediately.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        deadline = time.monotonic() + 3
        while True:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            self.assertLess(time.monotonic(), deadline, "disconnected handler was not reaped before its 30-second deadline")
            time.sleep(.02)
        self.assertEqual(self.request("POST", "/echo", '{"new":true}'),
                         (200, {"body": {"new": True}}))


@unittest.skipUnless(os.environ.get("SILTA_RUNTIME_BIN"), "requires built Rust runtime")
class TimeoutConfigIntegrationTests(unittest.TestCase):
    def test_cli_timeout_override_survives_database_flag(self):
        env = {**os.environ, "SILTA_REQUEST_TIMEOUT_MS": "1000"}
        result = subprocess.run([
            os.environ["SILTA_RUNTIME_BIN"], "--request-timeout-ms", "0",
            "--database-url", "invalid",
        ], env=env, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("request timeout must be", result.stderr)

    def test_invalid_timeouts_fail_before_binding(self):
        for value in ("0", "-1", "abc", "86400001", str(2**64 - 1)):
            for source in ("flag", "env"):
                with self.subTest(value=value, source=source):
                    env = os.environ.copy()
                    env.pop("SILTA_REQUEST_TIMEOUT_MS", None)
                    command = [os.environ["SILTA_RUNTIME_BIN"], "--port", "0"]
                    if source == "flag":
                        command += ["--request-timeout-ms", value]
                    else:
                        env["SILTA_REQUEST_TIMEOUT_MS"] = value
                    result = subprocess.run(command, env=env, capture_output=True, timeout=5)
                    self.assertNotEqual(result.returncode, 0)


class CookbookIntegrationTests(RuntimeServerTestCase):
    @classmethod
    def setUpClass(cls):
        sample = Path(__file__).resolve().parents[2] / "examples/cookbook/app.py"
        if not sample.exists():
            raise unittest.SkipTest("cookbook example requires a repository checkout")
        cls.app_source = sample.read_text()
        super().setUpClass()
    ready_path = "/health"
    timeout_ms = 1000

    def test_documented_recipes_over_http(self):
        self.assertEqual(self.request("GET", "/health"), (200, {"status": "ok"}))
        self.assertEqual(self.request("POST", "/echo", '{"order_id":42}'),
                         (200, {"received": {"order_id": 42}}))
        self.assertEqual(self.request("GET", "/async"), (200, {"completed": True}))
        self.assertEqual(self.request("POST", "/echo", '{broken')[0], 400)
        pid = self.request("GET", "/worker")[1]["pid"]
        self.assertEqual(self.request("POST", "/slow")[0], 504)
        status, body = self.request("GET", "/worker")
        self.assertEqual(status, 200)
        self.assertNotEqual(pid, body["pid"])
        self.assertEqual(self.request("POST", "/crash")[0], 500)
        self.assertEqual(self.request("GET", "/health")[0], 200)
        self.assertEqual(self.request("GET", "/worker")[0], 200)


@unittest.skipUnless(os.environ.get("SILTA_RUNTIME_BIN") and os.name == "posix", "requires Rust runtime and POSIX")
class StartupDeadlineIntegrationTests(RuntimeServerTestCase):
    timeout_ms = 1000

    def test_hung_import_is_reaped_at_startup_deadline(self):
        pid = self.request("GET", "/worker-pid")[1]["pid"]
        workers = self.app_path.with_suffix(".workers")
        count = len(workers.read_text().splitlines())
        hang = self.app_path.with_suffix(".hang-import")
        hang.touch()
        try:
            os.kill(pid, signal.SIGKILL)
            deadline = time.monotonic() + 5
            while len(workers.read_text().splitlines()) == count:
                self.assertLess(time.monotonic(), deadline, "replacement did not start")
                time.sleep(.02)
            hung_pid = int(workers.read_text().splitlines()[-1])
            self.assertEqual(self.request("POST", "/echo", '{}')[0], 504)
            self.assertEqual(self.request("GET", "/native")[0], 200)
            hang.unlink()
            # No handler was dispatched: the independent startup watchdog must
            # terminate a stuck import even after the waiting request expires.
            deadline = time.monotonic() + 12
            while True:
                try:
                    os.kill(hung_pid, 0)
                except ProcessLookupError:
                    break
                self.assertLess(time.monotonic(), deadline, "startup timeout did not reap worker")
                time.sleep(.05)
            self.assertEqual(self.request("POST", "/echo", '{}')[0], 200)
        finally:
            hang.unlink(missing_ok=True)


@unittest.skipUnless(os.environ.get("SILTA_RUNTIME_BIN") and os.name == "posix", "requires Rust runtime and POSIX")
class WorkerProtocolLimitIntegrationTests(RuntimeServerTestCase):
    def test_oversized_reply_is_bounded_and_worker_recovers(self):
        pid = self.request("GET", "/worker-pid")[1]["pid"]
        self.assertEqual(self.request("GET", "/oversized")[0], 500)
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)
        self.assertEqual(self.request("POST", "/echo", '{}'), (200, {"body": {}}))
