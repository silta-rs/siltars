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
import unittest


APP = '''
from silta import App
import asyncio
app = App()
print("application startup log")

@app.get("/native", response={"native": True})
def native():
    raise AssertionError("static response must not execute Python")

@app.post("/echo")
async def echo(request):
    print("handler log")
    return {"body": request["body"]}

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
class RuntimeIntegrationTests(unittest.TestCase):
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
