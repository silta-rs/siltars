from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class BenchmarkResult:
    label: str
    method: str
    url: str
    requests: int
    concurrency: int
    ok: int
    errors: int
    elapsed_seconds: float
    requests_per_second: float
    p50_ms: float
    p95_ms: float
    p99_ms: float


def main() -> int:
    parser = argparse.ArgumentParser(description="Small HTTP benchmark harness.")
    parser.add_argument("--label", required=True)
    parser.add_argument("--method", default="GET")
    parser.add_argument("--url", required=True)
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument("--body", default="")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = run_benchmark(
        label=args.label,
        method=args.method,
        url=args.url,
        requests=args.requests,
        concurrency=args.concurrency,
        body=args.body.encode() if args.body else None,
    )

    payload = result.__dict__
    text = json.dumps(payload, indent=2, sort_keys=True)
    print(text)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")

    return 0 if result.errors == 0 else 1


def run_benchmark(
    *,
    label: str,
    method: str,
    url: str,
    requests: int,
    concurrency: int,
    body: bytes | None,
) -> BenchmarkResult:
    latencies: list[float] = []
    errors = 0
    started = time.perf_counter()

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(_request_once, method=method, url=url, body=body)
            for _ in range(requests)
        ]

        for future in as_completed(futures):
            try:
                latencies.append(future.result())
            except (HTTPError, URLError, TimeoutError, OSError):
                errors += 1

    elapsed = time.perf_counter() - started
    ok = len(latencies)
    rps = ok / elapsed if elapsed > 0 else 0.0

    return BenchmarkResult(
        label=label,
        method=method,
        url=url,
        requests=requests,
        concurrency=concurrency,
        ok=ok,
        errors=errors,
        elapsed_seconds=elapsed,
        requests_per_second=rps,
        p50_ms=_percentile(latencies, 50),
        p95_ms=_percentile(latencies, 95),
        p99_ms=_percentile(latencies, 99),
    )


def _request_once(*, method: str, url: str, body: bytes | None) -> float:
    headers: dict[str, str] = {}
    if body is not None:
        headers["content-type"] = "application/json"

    request = Request(url, data=body, headers=headers, method=method)
    started = time.perf_counter()

    with urlopen(request, timeout=10) as response:
        response.read()
        if response.status >= 400:
            raise HTTPError(url, response.status, "HTTP error", response.headers, None)

    return (time.perf_counter() - started) * 1000


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]

    return statistics.quantiles(values, n=100, method="inclusive")[percentile - 1]


if __name__ == "__main__":
    raise SystemExit(main())
