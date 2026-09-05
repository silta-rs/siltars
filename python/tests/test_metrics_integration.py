"""Metrics must reflect real HTTP/worker behavior independently of Python health."""
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
import os
from pathlib import Path
import re
import signal
import socket
import struct
import subprocess
import time
import unittest

from test_runtime_integration import APP, RuntimeServerTestCase


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def values(text, name, **labels):
    result = []
    for line in text.splitlines():
        match = re.fullmatch(re.escape(name) + r'(?:\{(.*)\})? ([^ ]+)', line)
        if not match:
            continue
        found = {key: json.loads('"' + value + '"') for key, value in
                 re.findall(r'(\w+)="((?:\\.|[^"\\])*)"', match[1] or '')}
        if all(found.get(key) == value for key, value in labels.items()):
            result.append(float(match[2]))
    return result


class MetricsIntegrationTests(RuntimeServerTestCase):
    timeout_ms = 1000
    app_source = APP + '''
@app.get("/items/{item_id}", response={"item": True})
def item():
    pass

@app.get("/metrics", response={"application_owned": True})
def own_metrics():
    pass
'''

    @classmethod
    def setUpClass(cls):
        cls.metrics_port = free_port()
        cls.runtime_args = ["--metrics-listen", f"127.0.0.1:{cls.metrics_port}",
                            "--service-name", "metrics-test"]
        super().setUpClass()

    @classmethod
    def scrape(cls):
        connection = http.client.HTTPConnection("127.0.0.1", cls.metrics_port, timeout=3)
        try:
            connection.request("GET", "/metrics")
            response = connection.getresponse()
            if response.status != 200:
                raise AssertionError(f"scrape returned {response.status}")
            if "text/plain; version=0.0.4" not in response.getheader("Content-Type", ""):
                raise AssertionError("wrong Prometheus content type")
            return response.read().decode()
        finally:
            connection.close()

    def wait_metric(self, name, expected, **labels):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            text = self.scrape()
            if sum(values(text, name, **labels)) == expected:
                return text
            time.sleep(.02)
        self.fail(f"{name} {labels} never reached {expected}")

    def count(self, name, **labels):
        return sum(values(self.scrape(), name, **labels))

    def test_http_templates_counters_histograms_and_scrape_isolation(self):
        before = self.count("silta_http_requests_total", route="/items/{item_id}")
        for identifier in ("private-one", "private-two", "private-three"):
            self.assertEqual(self.request("GET", "/items/" + identifier + "?token=secret")[0], 200)
        text = self.scrape()
        self.assertEqual(sum(values(text, "silta_http_requests_total", route="/items/{item_id}", execution="native", status="200")), before + 3)
        count = sum(values(text, "silta_http_request_duration_seconds_count", route="/items/{item_id}"))
        self.assertEqual(count, sum(values(text, "silta_http_request_duration_seconds_bucket", route="/items/{item_id}", le="+Inf")))
        for secret in ("private-one", "private-two", "private-three", "token=", "secret"):
            self.assertNotIn(secret, text)
        for index in range(30):
            connection = http.client.HTTPConnection("127.0.0.1", self.port)
            connection.request("GET", f"/nonexistent-private-{index}")
            response = connection.getresponse()
            self.assertEqual(response.status, 404)
            response.read()
            connection.close()
        text = self.scrape()
        self.assertNotIn("nonexistent-private", text)
        self.assertEqual(len(values(text, "silta_http_requests_total", route="__unmatched__", method="GET", status="404")), 1)
        total = sum(values(text, "silta_http_requests_total"))
        self.assertEqual(sum(values(self.scrape(), "silta_http_requests_total")), total)
        self.assertEqual(self.request("GET", "/metrics"), (200, {"application_owned": True}))
        self.assertIn('service_name="metrics-test"', self.scrape())

    def test_http_errors_and_worker_errors_are_counted_once(self):
        self.assertEqual(self.request("GET", "/worker-pid")[0], 200)
        before = self.count("silta_http_requests_total", route="/echo", status="400")
        self.assertEqual(self.request("POST", "/echo", '{broken')[0], 400)
        self.assertEqual(self.count("silta_http_requests_total", route="/echo", status="400"), before + 1)
        before = self.count("silta_python_calls_total", outcome="handler_error")
        starts = self.count("silta_python_worker_starts_total")
        self.assertEqual(self.request("GET", "/bad")[0], 500)
        self.assertEqual(self.count("silta_python_calls_total", outcome="handler_error"), before + 1)
        self.assertEqual(self.count("silta_python_worker_starts_total"), starts)

    def test_timeout_and_queue_gauges_are_balanced(self):
        marker = Path(self.temp.name) / "metrics-active"
        timeouts = self.count("silta_python_worker_restarts_total", reason="timeout")
        with ThreadPoolExecutor(max_workers=2) as pool:
            active = pool.submit(self.request, "POST", "/blocking", json.dumps({"marker": str(marker)}))
            deadline = time.monotonic() + 3
            while not marker.exists():
                self.assertLess(time.monotonic(), deadline)
                time.sleep(.01)
            self.wait_metric("silta_python_worker_busy", 1)
            queued = pool.submit(self.request, "POST", "/echo", '{}')
            self.wait_metric("silta_python_queue_depth", 1)
            self.assertGreaterEqual(self.count("silta_http_requests_in_flight"), 2)
            self.assertEqual(self.request("GET", "/native")[0], 200)
            self.assertEqual(active.result()[0], 504)
            self.assertEqual(queued.result()[0], 504)
        self.wait_metric("silta_python_worker_restarts_total", timeouts + 1, reason="timeout")
        self.wait_metric("silta_python_worker_busy", 0)
        self.wait_metric("silta_python_queue_depth", 0)
        self.wait_metric("silta_http_requests_in_flight", 0)
        self.assertEqual(self.request("POST", "/echo", '{}')[0], 200)
        self.wait_metric("silta_python_worker_ready", 1)

    @unittest.skipUnless(os.name == "posix", "requires POSIX process checks")
    def test_crash_keeps_metrics_and_native_routes_alive(self):
        restarts = self.count("silta_python_worker_restarts_total", reason="eof")
        pid = self.request("GET", "/worker-pid")[1]["pid"]
        self.assertEqual(self.request("POST", "/crash")[0], 500)
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)
        self.assertEqual(self.count("silta_python_worker_restarts_total", reason="eof"), restarts + 1)
        self.assertEqual(self.request("GET", "/native")[0], 200)
        self.assertEqual(self.request("GET", "/worker-pid")[0], 200)
        self.wait_metric("silta_python_worker_ready", 1)

    @unittest.skipUnless(os.name == "posix", "requires TCP reset")
    def test_disconnect_balances_http_and_worker_gauges(self):
        cancelled = self.count("silta_http_requests_total", route="/blocking", status="cancelled")
        marker = Path(self.temp.name) / "metrics-disconnect"
        payload = json.dumps({"marker": str(marker)}).encode()
        with socket.create_connection(("127.0.0.1", self.port), timeout=3) as sock:
            sock.sendall((f"POST /blocking HTTP/1.1\r\nHost: localhost\r\nContent-Length: {len(payload)}\r\n\r\n").encode() + payload)
            deadline = time.monotonic() + .8
            while not marker.exists():
                self.assertLess(time.monotonic(), deadline)
                time.sleep(.01)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        self.wait_metric("silta_http_requests_total", cancelled + 1, route="/blocking", status="cancelled")
        self.wait_metric("silta_http_requests_in_flight", 0)
        self.wait_metric("silta_python_worker_busy", 0)
        self.wait_metric("silta_python_queue_depth", 0)


class OtlpIntegrationTests(RuntimeServerTestCase):
    @classmethod
    def setUpClass(cls):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading
        cls.mode = "unavailable"
        cls.received = []
        class Collector(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                cls.received.append((self.path, self.headers.get("Content-Type"), self.headers.get("Authorization"), body))
                if cls.mode == "hang":
                    time.sleep(.5)
                try:
                    self.send_response(503 if cls.mode == "unavailable" else 200)
                    self.send_header("Content-Type", "application/x-protobuf")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                except (OSError, BrokenPipeError):
                    pass
            def log_message(self, *_args):
                pass
        cls.collector = ThreadingHTTPServer(("127.0.0.1", 0), Collector)
        cls.addClassCleanup(cls.collector.server_close)
        thread = threading.Thread(target=cls.collector.serve_forever, daemon=True)
        thread.start()
        cls.addClassCleanup(cls.collector.shutdown)
        cls.metrics_port = free_port()
        cls.runtime_env = {**os.environ,
            "SILTA_METRICS_LISTEN": f"127.0.0.1:{cls.metrics_port}",
            "OTEL_EXPORTER_OTLP_ENDPOINT": f"http://127.0.0.1:{cls.collector.server_port}",
            "OTEL_SERVICE_NAME": "otlp-env-test",
            "OTEL_METRIC_EXPORT_INTERVAL": "100",
            "OTEL_METRIC_EXPORT_TIMEOUT": "100",
            "OTEL_EXPORTER_OTLP_METRICS_HEADERS": "Authorization=test-token",
        }
        super().setUpClass()

    def scrape(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.metrics_port, timeout=2)
        try:
            connection.request("GET", "/metrics")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            return response.read().decode()
        finally:
            connection.close()

    def wait_export(self, outcome):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if sum(values(self.scrape(), "silta_metrics_exports_total", outcome=outcome)) > 0:
                return
            time.sleep(.02)
        self.fail(f"no {outcome} export observed")

    def test_collector_failure_recovery_and_shutdown_do_not_block_http(self):
        self.wait_export("failure")
        started = time.monotonic()
        for _ in range(5):
            self.assertEqual(self.request("GET", "/native")[0], 200)
            self.assertEqual(self.request("POST", "/echo", '{}')[0], 200)
        self.assertLess(time.monotonic() - started, 3)
        type(self).mode = "ok"
        self.wait_export("success")
        self.assertTrue(self.received)
        for path, content_type, auth, body in self.received:
            self.assertEqual(path, "/v1/metrics")
            self.assertEqual(content_type, "application/x-protobuf")
            self.assertEqual(auth, "test-token")
            self.assertIn(b"silta_http_requests", body)
            self.assertIn(b"otlp-env-test", body)
        self.assertIn('service_name="otlp-env-test"', self.scrape())
        type(self).mode = "hang"
        started = time.monotonic()
        self.assertEqual(self.request("POST", "/echo", '{}')[0], 200)
        self.scrape()
        self.assertLess(time.monotonic() - started, 1)
        self.process.send_signal(signal.SIGTERM)
        self.process.wait(timeout=7)
        self.assertLess(time.monotonic() - started, 6)


class NativeOnlyMetricsIntegrationTests(RuntimeServerTestCase):
    app_source = '''
from silta import App
app = App(name="native-only")
@app.get("/native", response={"native": True})
def native():
    pass
'''
    @classmethod
    def setUpClass(cls):
        cls.metrics_port = free_port()
        cls.runtime_args = ["--metrics-listen", f"127.0.0.1:{cls.metrics_port}"]
        super().setUpClass()

    def test_native_only_application_exports_without_starting_python(self):
        self.assertEqual(self.request("GET", "/native")[0], 200)
        connection = http.client.HTTPConnection("127.0.0.1", self.metrics_port, timeout=2)
        try:
            connection.request("GET", "/metrics")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            text = response.read().decode()
            self.assertEqual(values(text, "silta_python_worker_ready"), [0])
            self.assertEqual(sum(values(text, "silta_python_worker_starts_total")), 0)
            self.assertGreater(sum(values(text, "silta_http_requests_total", execution="native")), 0)
        finally:
            connection.close()


@unittest.skipUnless(os.environ.get("SILTA_RUNTIME_BIN"), "requires built Rust runtime")
class MetricsConfigIntegrationTests(unittest.TestCase):
    def test_invalid_config_exits_before_worker_start(self):
        for flag, value in (("--metrics-listen", "not-an-address"),
                            ("--otlp-metrics-endpoint", "ftp://localhost/metrics"),
                            ("--otlp-metrics-endpoint", "http://user:do-not-print@localhost/metrics"),
                            ("--metrics-export-interval-ms", "0"),
                            ("--metrics-export-timeout-ms", "6000"),
                            ("--service-name", "")):
            with self.subTest(flag=flag, value=value):
                result = subprocess.run([os.environ["SILTA_RUNTIME_BIN"], "--port", "0", flag, value],
                                        capture_output=True, text=True, timeout=5)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("do-not-print", result.stderr)

    def test_occupied_management_port_fails_startup(self):
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            result = subprocess.run([os.environ["SILTA_RUNTIME_BIN"], "--port", "0",
                                     "--metrics-listen", f"127.0.0.1:{occupied.getsockname()[1]}"],
                                    capture_output=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
