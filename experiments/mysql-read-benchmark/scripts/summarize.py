from __future__ import annotations

import argparse
import csv
import html
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median


@dataclass(frozen=True)
class Point:
    label: str
    endpoint: str
    concurrency: int
    rps: float
    p95_ms: float
    p99_ms: float


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize MySQL benchmark medians.")
    parser.add_argument("results", type=Path)
    args = parser.parse_args()

    source = args.results / "load-curve.csv"
    points = read_medians(source)
    sample_description = read_sample_description(source)
    write_csv(args.results / "medians.csv", points)
    write_svg(args.results / "mysql-read-throughput.svg", points, sample_description)
    write_markdown(args.results / "README.md", points, sample_description)
    return 0


def read_medians(path: Path) -> list[Point]:
    groups: dict[tuple[str, str, int], list[dict[str, str]]] = defaultdict(list)
    with path.open(encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            groups[(row["label"], row["endpoint"], int(row["concurrency"]))].append(row)

    return sorted(
        (
            Point(
                label=label,
                endpoint=endpoint,
                concurrency=concurrency,
                rps=median(float(row["rps"]) for row in rows),
                p95_ms=median(float(row["p95_ms"]) for row in rows),
                p99_ms=median(float(row["p99_ms"]) for row in rows),
            )
            for (label, endpoint, concurrency), rows in groups.items()
        ),
        key=lambda point: (point.endpoint, point.label, point.concurrency),
    )


def read_sample_description(path: Path) -> str:
    with path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    run_count = max(int(row["run"]) for row in rows)
    durations = {row["duration"] for row in rows if row["duration"]}
    duration = durations.pop() if len(durations) == 1 else "mixed-duration"
    return f"{run_count} x {duration} runs per point; plotted values are medians"


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


def write_svg(path: Path, points: list[Point], sample_description: str) -> None:
    width, height = 1400, 760
    panel_width, panel_height = 400, 440
    panel_top = 150
    panel_lefts = [70, 500, 930]
    endpoints = ["/mysql/events/1", "/mysql/events/100", "/mysql/events/1000"]
    colors = {"Silta": "#2563eb", "FastAPI": "#ef5b2a"}
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#111827;letter-spacing:0}'
        '.grid{stroke:#e5e7eb;stroke-width:1}.axis{stroke:#9ca3af;stroke-width:1}'
        '.line{fill:none;stroke-width:3}.dot{stroke:white;stroke-width:2}</style>',
        '<text x="70" y="58" font-size="32" font-weight="700">Silta Alpha vs FastAPI: MySQL read throughput</text>',
        f'<text x="70" y="92" font-size="16" fill="#4b5563">{html.escape(sample_description)}. Same MySQL 8.4, SQL and JSON.</text>',
        '<line x1="70" y1="118" x2="100" y2="118" stroke="#2563eb" stroke-width="4"/>',
        '<text x="110" y="124" font-size="15">Silta native SQLx/MySQL</text>',
        '<line x1="330" y1="118" x2="360" y2="118" stroke="#ef5b2a" stroke-width="4"/>',
        '<text x="370" y="124" font-size="15">FastAPI + prepared asyncmy + orjson</text>',
    ]

    for endpoint, left in zip(endpoints, panel_lefts):
        selected = [point for point in points if point.endpoint == endpoint]
        max_rps = max(point.rps for point in selected) * 1.12
        max_concurrency = max(point.concurrency for point in selected)

        def x(value: int) -> float:
            return left + value / max_concurrency * panel_width

        def y(value: float) -> float:
            return panel_top + panel_height - value / max_rps * panel_height

        row_count = endpoint.rsplit("/", 1)[-1]
        lines.append(
            f'<text x="{left}" y="{panel_top - 24}" font-size="22" font-weight="700">{row_count} row{"s" if row_count != "1" else ""}</text>'
        )
        for tick in range(6):
            value = max_rps * tick / 5
            yy = y(value)
            lines.append(f'<line class="grid" x1="{left}" y1="{yy:.1f}" x2="{left + panel_width}" y2="{yy:.1f}"/>')
            lines.append(f'<text x="{left - 10}" y="{yy + 5:.1f}" text-anchor="end" font-size="12">{value / 1000:.1f}k</text>')
        for concurrency in sorted({point.concurrency for point in selected}):
            xx = x(concurrency)
            lines.append(f'<line class="grid" x1="{xx:.1f}" y1="{panel_top}" x2="{xx:.1f}" y2="{panel_top + panel_height}"/>')
            lines.append(f'<text x="{xx:.1f}" y="{panel_top + panel_height + 24}" text-anchor="middle" font-size="12">{concurrency}</text>')
        lines.append(f'<line class="axis" x1="{left}" y1="{panel_top + panel_height}" x2="{left + panel_width}" y2="{panel_top + panel_height}"/>')

        for label in ("Silta", "FastAPI"):
            series = [point for point in selected if point.label == label]
            path_data = " ".join(
                f'{"M" if index == 0 else "L"} {x(point.concurrency):.1f} {y(point.rps):.1f}'
                for index, point in enumerate(series)
            )
            lines.append(f'<path class="line" d="{path_data}" stroke="{colors[label]}"/>')
            for point in series:
                lines.append(
                    f'<circle class="dot" cx="{x(point.concurrency):.1f}" cy="{y(point.rps):.1f}" r="5" fill="{colors[label]}">'
                    f'<title>{html.escape(label)} c={point.concurrency}: {point.rps:.0f} RPS, p99 {point.p99_ms:.1f} ms</title></circle>'
                )
        lines.append(f'<text x="{left + panel_width / 2}" y="{panel_top + panel_height + 54}" text-anchor="middle" font-size="14">concurrent connections</text>')

    lines.extend(
        [
            '<text x="28" y="370" transform="rotate(-90 28 370)" text-anchor="middle" font-size="14">requests/sec</text>',
            '<text x="70" y="700" font-size="13" fill="#6b7280">Python 3.14.7 | FastAPI 0.141.1 | Uvicorn 0.52.4 | asyncmy 0.2.13 | orjson 3.12.0 | MySQL 8.4.11</text>',
            '<text x="70" y="728" font-size="13" fill="#6b7280">Local Alpha benchmark. One machine, one run environment; verify independently before making general claims.</text>',
            "</svg>",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_markdown(path: Path, points: list[Point], sample_description: str) -> None:
    rows = [
        "# MySQL read benchmark results",
        "",
        f"{sample_description.capitalize()}.",
        "",
        "| Rows | Silta best RPS | FastAPI best RPS | Ratio |",
        "| ---: | ---: | ---: | ---: |",
    ]
    for endpoint in ("/mysql/events/1", "/mysql/events/100", "/mysql/events/1000"):
        selected = [point for point in points if point.endpoint == endpoint]
        silta = max(point.rps for point in selected if point.label == "Silta")
        fastapi = max(point.rps for point in selected if point.label == "FastAPI")
        rows.append(f"| {endpoint.rsplit('/', 1)[-1]} | {silta:,.0f} | {fastapi:,.0f} | {silta / fastapi:.2f}x |")
    rows.extend(
        [
            "",
            "![MySQL read throughput](mysql-read-throughput.svg)",
            "",
            "This is an Alpha engineering result from one local machine, not a general performance claim.",
        ]
    )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
