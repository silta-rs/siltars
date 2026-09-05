from __future__ import annotations

import argparse
import csv
import html
import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class Target:
    label: str
    method: str
    endpoint: str
    url: str
    body: str | None = None


@dataclass(frozen=True)
class Point:
    label: str
    method: str
    endpoint: str
    run: int
    concurrency: int
    requests: int | None
    duration: str
    success_rate: float
    rps: float
    average_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    status_codes: str


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run an oha load curve and plot response time vs requests/sec."
    )
    parser.add_argument("--silta-url", default="http://127.0.0.1:8104")
    parser.add_argument("--fastapi-url", default="http://127.0.0.1:8103")
    parser.add_argument(
        "--requests",
        type=int,
        default=None,
        help="Fixed request count for smoke tests. Serious runs should use --duration.",
    )
    parser.add_argument(
        "--duration",
        default="30s",
        help="Duration passed to oha -z. Default is 30s.",
    )
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument(
        "--concurrency",
        default="1,5,10,25,50,100,150,200",
        help="Comma-separated oha concurrency levels.",
    )
    parser.add_argument(
        "--endpoint",
        action="append",
        default=[],
        help="GET endpoint path to test. Can be repeated.",
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help='Benchmark case: METHOD PATH [JSON_BODY], for example "PATCH /setting {""value"":""patched""}".',
    )
    parser.add_argument("--output-dir", type=Path, default=Path("results/load-curve"))
    args = parser.parse_args()

    cases = parse_cases(args.case, args.endpoint)
    concurrency_levels = [int(value) for value in args.concurrency.split(",") if value]
    args.output_dir.mkdir(parents=True, exist_ok=True)

    points: list[Point] = []
    for benchmark_case in cases:
        targets = [
            Target(
                "Silta",
                benchmark_case.method,
                benchmark_case.endpoint,
                f"{args.silta_url}{benchmark_case.endpoint}",
                benchmark_case.body,
            ),
            Target(
                "FastAPI",
                benchmark_case.method,
                benchmark_case.endpoint,
                f"{args.fastapi_url}{benchmark_case.endpoint}",
                benchmark_case.body,
            ),
        ]
        for target in targets:
            for concurrency in concurrency_levels:
                for run in range(1, args.runs + 1):
                    points.append(
                        run_oha(
                            target=target,
                            requests=args.requests,
                            duration=args.duration,
                            concurrency=concurrency,
                            run=run,
                            raw_output_dir=args.output_dir / "raw",
                        )
                    )
                    time.sleep(0.2)

    csv_path = args.output_dir / "load-curve.csv"
    svg_path = args.output_dir / "load-curve.svg"
    write_csv(csv_path, points)
    write_svg(svg_path, points)

    print(f"wrote {csv_path}")
    print(f"wrote {svg_path}")
    for benchmark_case in cases:
        endpoint_points = [
            point
            for point in points
            if point.method == benchmark_case.method
            and point.endpoint == benchmark_case.endpoint
        ]
        endpoint_svg_path = args.output_dir / (
            f"{slug(benchmark_case.method)}-{slug(benchmark_case.endpoint)}.svg"
        )
        write_svg(endpoint_svg_path, endpoint_points)
        print(f"wrote {endpoint_svg_path}")
    return 0


@dataclass(frozen=True)
class BenchmarkCase:
    method: str
    endpoint: str
    body: str | None = None


def parse_cases(raw_cases: list[str], endpoints: list[str]) -> list[BenchmarkCase]:
    if raw_cases:
        return [parse_case(value) for value in raw_cases]

    selected_endpoints = endpoints or ["/ping", "/rates/EUR/USD", "/rates"]
    return [BenchmarkCase("GET", endpoint) for endpoint in selected_endpoints]


def parse_case(value: str) -> BenchmarkCase:
    parts = value.split(maxsplit=2)
    if len(parts) < 2:
        raise ValueError("--case must use: METHOD PATH [JSON_BODY]")

    method = parts[0].upper()
    endpoint = parts[1]
    body = parts[2] if len(parts) == 3 else None
    if not endpoint.startswith("/"):
        raise ValueError("--case path must start with '/'")
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}:
        raise ValueError(f"unsupported method in --case: {method}")

    return BenchmarkCase(method, endpoint, body)


def run_oha(
    *,
    target: Target,
    requests: int | None,
    duration: str,
    concurrency: int,
    run: int,
    raw_output_dir: Path,
) -> Point:
    command = [
        "oha",
        "-m",
        target.method,
        "-c",
        str(concurrency),
        "--no-tui",
        "--output-format",
        "json",
    ]
    if requests is None:
        command.extend(["-z", duration])
    else:
        command.extend(["-n", str(requests)])
    if target.body is not None:
        command.extend(["-H", "content-type: application/json", "-d", target.body])
    command.append(target.url)

    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    payload = json.loads(completed.stdout)
    raw_output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_output_dir / (
        f"{slug(target.label)}-{slug(target.method)}-{slug(target.endpoint)}-c{concurrency}-run{run}.json"
    )
    raw_path.write_text(completed.stdout, encoding="utf-8")

    summary = payload.get("summary", payload)
    metrics = payload.get("metrics", {})
    latency_ms = metrics.get("latency_ms", {})
    latency_percentiles = payload.get("latencyPercentiles", {})

    return Point(
        label=target.label,
        method=target.method,
        endpoint=target.endpoint,
        run=run,
        concurrency=concurrency,
        requests=requests,
        duration=duration if requests is None else "",
        success_rate=as_float(metrics, "success_rate")
        * 100
        or as_float(summary, "successRate", "success_rate") * 100,
        rps=as_float(metrics, "requests_per_sec")
        or as_float(summary, "requestsPerSec", "requests_per_sec"),
        average_ms=as_float(latency_ms, "mean")
        or seconds_to_ms(as_float(summary, "average", "averageSeconds", "average_ms")),
        p50_ms=as_float(latency_ms, "p50") or percentile_ms(latency_percentiles, 50),
        p95_ms=as_float(latency_ms, "p95") or percentile_ms(latency_percentiles, 95),
        p99_ms=as_float(latency_ms, "p99") or percentile_ms(latency_percentiles, 99),
        status_codes=json.dumps(payload.get("statusCodeDistribution", {}), sort_keys=True),
    )


def as_float(mapping: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return float(value)
    return 0.0


def seconds_to_ms(value: float) -> float:
    return value * 1000 if value < 100 else value


def percentile_ms(distribution: dict[str, Any], percentile: int) -> float:
    keys = [
        str(percentile),
        f"{percentile}.0",
        f"{percentile}.00",
        f"p{percentile}",
        f"{percentile}%",
    ]
    for key in keys:
        value = distribution.get(key)
        if value is not None:
            return seconds_to_ms(float(value))
    return 0.0


def write_csv(path: Path, points: list[Point]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(Point.__dataclass_fields__),
            lineterminator="\n",
        )
        writer.writeheader()
        for point in points:
            writer.writerow(point.__dict__)


def slug(value: str) -> str:
    normalized = value.strip("/").replace("/", "-").replace("_", "-")
    return normalized or "root"


def write_svg(path: Path, points: list[Point]) -> None:
    points = average_points(points)
    width = 1100
    height = 720
    margin_left = 78
    margin_right = 28
    margin_top = 56
    margin_bottom = 70
    chart_width = width - margin_left - margin_right
    chart_height = height - margin_top - margin_bottom

    max_rps = max(point.rps for point in points) * 1.08
    max_p95 = max(point.p95_ms for point in points) * 1.18

    def x(value: float) -> float:
        return margin_left + (value / max_rps) * chart_width

    def y(value: float) -> float:
        return margin_top + chart_height - (value / max_p95) * chart_height

    colors = {"Silta": "#2563eb", "FastAPI": "#dc2626"}
    endpoints = list(dict.fromkeys(f"{point.method} {point.endpoint}" for point in points))
    labels = ["Silta", "FastAPI"]

    lines: list[str] = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>text{font-family:Arial,sans-serif;font-size:13px;fill:#111827}'
        '.axis{stroke:#111827;stroke-width:1}.grid{stroke:#e5e7eb;stroke-width:1}'
        '.series{fill:none;stroke-width:2.5}.point{stroke:white;stroke-width:1.5}</style>',
        f'<text x="{width / 2}" y="28" text-anchor="middle" '
        'font-size="18" font-weight="700">Response time vs throughput</text>',
        f'<line class="axis" x1="{margin_left}" y1="{margin_top}" '
        f'x2="{margin_left}" y2="{margin_top + chart_height}"/>',
        f'<line class="axis" x1="{margin_left}" y1="{margin_top + chart_height}" '
        f'x2="{margin_left + chart_width}" y2="{margin_top + chart_height}"/>',
        f'<text x="{margin_left + chart_width / 2}" y="{height - 22}" '
        'text-anchor="middle">Requests/sec</text>',
        f'<text transform="translate(22 {margin_top + chart_height / 2}) rotate(-90)" '
        'text-anchor="middle">p95 response time, ms</text>',
    ]

    for i in range(6):
        value = max_p95 * i / 5
        yy = y(value)
        lines.append(
            f'<line class="grid" x1="{margin_left}" y1="{yy:.1f}" '
            f'x2="{margin_left + chart_width}" y2="{yy:.1f}"/>'
        )
        lines.append(
            f'<text x="{margin_left - 10}" y="{yy + 4:.1f}" '
            f'text-anchor="end">{value:.0f}</text>'
        )

    for i in range(6):
        value = max_rps * i / 5
        xx = x(value)
        lines.append(
            f'<line class="grid" x1="{xx:.1f}" y1="{margin_top}" '
            f'x2="{xx:.1f}" y2="{margin_top + chart_height}"/>'
        )
        lines.append(
            f'<text x="{xx:.1f}" y="{margin_top + chart_height + 22}" '
            f'text-anchor="middle">{value:,.0f}</text>'
        )

    legend_x = margin_left + 12
    for label_index, label in enumerate(labels):
        color = colors[label]
        lines.append(
            f'<circle cx="{legend_x + label_index * 110}" cy="48" r="5" fill="{color}"/>'
        )
        lines.append(
            f'<text x="{legend_x + 10 + label_index * 110}" y="52">{label}</text>'
        )

    dash_patterns = {"Silta": "", "FastAPI": " stroke-dasharray=\"7 5\""}
    for endpoint_index, endpoint in enumerate(endpoints):
        endpoint_points = [
            point for point in points if f"{point.method} {point.endpoint}" == endpoint
        ]
        for label in labels:
            series = sorted(
                [point for point in endpoint_points if point.label == label],
                key=lambda point: point.concurrency,
            )
            if not series:
                continue

            color = colors[label]
            path_data = " ".join(
                f"{'M' if index == 0 else 'L'} {x(point.rps):.1f} {y(point.p95_ms):.1f}"
                for index, point in enumerate(series)
            )
            lines.append(
                f'<path class="series" d="{path_data}" stroke="{color}"'
                f'{dash_patterns[label]}/>'
            )
            for point in series:
                radius = 4 + endpoint_index
                lines.append(
                    f'<circle class="point" cx="{x(point.rps):.1f}" '
                    f'cy="{y(point.p95_ms):.1f}" r="{radius}" fill="{color}">'
                    f'<title>{html.escape(label)} {html.escape(endpoint)} '
                    f'c={point.concurrency}, rps={point.rps:.0f}, '
                    f'p95={point.p95_ms:.2f}ms</title></circle>'
                )

    endpoint_text = " / ".join(endpoints)
    lines.append(
        f'<text x="{width - margin_right}" y="52" text-anchor="end">'
        f'Endpoints: {html.escape(endpoint_text)}</text>'
    )
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def average_points(points: list[Point]) -> list[Point]:
    groups: dict[tuple[str, str, str, int], list[Point]] = {}
    for point in points:
        key = (point.label, point.method, point.endpoint, point.concurrency)
        groups.setdefault(key, []).append(point)

    averaged: list[Point] = []
    for (label, method, endpoint, concurrency), group in groups.items():
        averaged.append(
            Point(
                label=label,
                method=method,
                endpoint=endpoint,
                run=0,
                concurrency=concurrency,
                requests=group[0].requests,
                duration=group[0].duration,
                success_rate=mean(point.success_rate for point in group),
                rps=mean(point.rps for point in group),
                average_ms=mean(point.average_ms for point in group),
                p50_ms=mean(point.p50_ms for point in group),
                p95_ms=mean(point.p95_ms for point in group),
                p99_ms=mean(point.p99_ms for point in group),
                status_codes="averaged",
            )
        )

    return sorted(
        averaged,
        key=lambda point: (
            point.method,
            point.endpoint,
            point.label,
            point.concurrency,
        ),
    )


def mean(values: Iterable[float]) -> float:
    collected = list(values)
    return sum(collected) / len(collected)


if __name__ == "__main__":
    raise SystemExit(main())
