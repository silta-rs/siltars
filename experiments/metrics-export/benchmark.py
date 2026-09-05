"""Local HTTP smoke comparison; not a maximum-throughput benchmark.

Uses one release binary for off, Prometheus, and Prometheus + unavailable OTLP.
The Python load generator and loopback stack may hide small runtime overheads.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import platform
import signal
import shutil
import socket
import statistics
import subprocess
import tempfile
import time


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def traffic(port, connections, per_connection):
    samples = []
    async def run():
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        try:
            for _ in range(per_connection):
                start = time.perf_counter()
                writer.write(b"GET /ping HTTP/1.1\r\nHost: localhost\r\n\r\n")
                await writer.drain()
                header = await reader.readuntil(b"\r\n\r\n")
                if not header.startswith(b"HTTP/1.1 200"):
                    raise RuntimeError(header)
                length = next(int(line.partition(b":")[2]) for line in header.lower().split(b"\r\n") if line.startswith(b"content-length:"))
                if json.loads(await reader.readexactly(length)) != {"ok": True}:
                    raise RuntimeError("unexpected response")
                samples.append((time.perf_counter() - start) * 1000)
        finally:
            writer.close()
            await writer.wait_closed()
    start = time.perf_counter()
    await asyncio.wait_for(asyncio.gather(*(run() for _ in range(connections))), timeout=60)
    elapsed = time.perf_counter() - start
    samples.sort()
    return {"requests": len(samples), "seconds": elapsed, "requests_per_second": len(samples) / elapsed,
            "p50_ms": statistics.median(samples), "p95_ms": samples[int(len(samples) * .95)],
            "p99_ms": samples[int(len(samples) * .99)]}


def measure(binary, mode, connections, per_connection):
    port, metrics_port, unavailable_port = free_port(), free_port(), free_port()
    args = [binary, "--port", str(port)]
    if mode != "off":
        args += ["--metrics-listen", f"127.0.0.1:{metrics_port}"]
    if mode == "otlp_unavailable":
        args += ["--otlp-metrics-endpoint", f"http://127.0.0.1:{unavailable_port}/v1/metrics",
                 "--metrics-export-interval-ms", "100", "--metrics-export-timeout-ms", "100"]
    env = {key: value for key, value in os.environ.items() if not key.startswith(("OTEL_", "SILTA_")) and key != "DATABASE_URL"}
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen(args, stdout=log, stderr=log, env=env)
        try:
            deadline = time.monotonic() + 10
            while True:
                if process.poll() is not None:
                    log.seek(0)
                    raise RuntimeError(log.read().decode())
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.1):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("runtime did not start")
                    time.sleep(.02)
            asyncio.run(traffic(port, connections, 100))
            return asyncio.run(traffic(port, connections, per_connection))
        finally:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-bin", required=True)
    parser.add_argument("--connections", type=int, default=16)
    parser.add_argument("--per-connection", type=int, default=1000)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--output", default="metrics-overhead.json")
    args = parser.parse_args()
    modes = ["off", "prometheus", "otlp_unavailable"]
    runs = {mode: [] for mode in modes}
    for round_number in range(args.rounds):
        # Rotate order to reduce warm-cache and host-load ordering bias.
        for mode in modes[round_number % 3:] + modes[:round_number % 3]:
            runs[mode].append(measure(args.runtime_bin, mode, args.connections, args.per_connection))
    report = {"platform": platform.platform(), "python": platform.python_version(),
              "cpu_count": os.cpu_count(), "rustc": subprocess.check_output([shutil.which("rustc") or str(Path.home() / ".cargo/bin/rustc"), "--version"], text=True).strip(),
              "connections": args.connections, "per_connection": args.per_connection, "rounds": args.rounds,
              "workload": "native GET /ping, keep-alive, JSON body validated, Python asyncio generator",
              "limitations": "Shared host and client may limit throughput; not a native-only microbenchmark or a production capacity claim.",
              "runs": runs,
              "medians": {mode: {key: statistics.median(run[key] for run in results) for key in ("requests_per_second", "p50_ms", "p95_ms", "p99_ms")} for mode, results in runs.items()}}
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["medians"], indent=2))


if __name__ == "__main__":
    main()
