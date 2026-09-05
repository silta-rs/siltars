"""Exercise the actual Rust HTTP server and Python subprocess together.

Set SILTA_RUNTIME_BIN to a built binary to enable this integration suite.
"""
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
    time.sleep(60)
    return {"done": True}

@app.get("/native", response={"native": True})
def native():
    raise AssertionError("static response must not execute Python")

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
    os._exit(7)

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
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        app_path = Path(cls.temp.name) / "app.py"
        app_path.write_text(APP, encoding="utf-8")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        cls.log = open(Path(cls.temp.name) / "server.log", "w+")
        cls.addClassCleanup(cls.log.close)
        cls.process = subprocess.Popen([
            sys.executable, "-m", "silta.cli", "dev", str(app_path) + ":app",
            "--port", str(cls.port), "--runtime-bin", os.environ["SILTA_RUNTIME_BIN"],
        ], stdout=cls.log, stderr=cls.log)
        cls.addClassCleanup(cls.stop_server)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if cls.process.poll() is not None:
                cls.log.seek(0)
                raise AssertionError("runtime exited: " + cls.log.read())
            try:
                cls.request("GET", "/native")
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


class WorkerClosedPipeIntegrationTests(WorkerCrashIntegrationTests):
    # EOF can precede process exit. Reaping must not block shutdown forever
    # while a handler that closed its protocol descriptor continues running.
    exit_route = "/close-protocol"
