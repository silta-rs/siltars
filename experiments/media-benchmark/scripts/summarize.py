from __future__ import annotations

import argparse
import csv
import html
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median


PAYLOADS = {
    "/media/blob/64k": ("64 KiB binary", 65_536),
    "/media/blob/1m": ("1 MiB binary", 1_048_576),
    "/media/image.bmp": ("512x512 BMP", 786_486),
}


@dataclass(frozen=True)
class Point:
    label: str
    endpoint: str
    concurrency: int
    rps: float
    gib_per_sec: float
    p95_ms: float
    p99_ms: float


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize media benchmark medians.")
    parser.add_argument("results", type=Path)
    args = parser.parse_args()

    source = args.results / "load-curve.csv"
    points = read_medians(source)
    sample = read_sample_description(source)
    write_csv(args.results / "medians.csv", points)
    write_svg(args.results / "media-throughput.svg", points, sample)
    write_markdown(args.results / "README.md", points, sample)
    return 0


def read_medians(path: Path) -> list[Point]:
    groups: dict[tuple[str, str, int], list[dict[str, str]]] = defaultdict(list)
    with path.open(encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            groups[(row["label"], row["endpoint"], int(row["concurrency"]))].append(row)

    points = []
    for (label, endpoint, concurrency), rows in groups.items():
        rps = median(float(row["rps"]) for row in rows)
        size = PAYLOADS[endpoint][1]
        points.append(
            Point(
                label=label,
                endpoint=endpoint,
                concurrency=concurrency,
                rps=rps,
                gib_per_sec=rps * size / 1024**3,
                p95_ms=median(float(row["p95_ms"]) for row in rows),
                p99_ms=median(float(row["p99_ms"]) for row in rows),
            )
        )
    return sorted(points, key=lambda point: (point.endpoint, point.label, point.concurrency))


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


def write_svg(path: Path, points: list[Point], sample: str) -> None:
    width, height = 1400, 780
    panel_width, panel_height = 400, 430
    panel_top = 170
    panel_lefts = [70, 500, 930]
    colors = {"Silta": "#2563eb", "FastAPI": "#ef5b2a"}
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#111827;letter-spacing:0}'
        '.grid{stroke:#e5e7eb;stroke-width:1}.axis{stroke:#9ca3af;stroke-width:1}'
        '.line{fill:none;stroke-width:3}.dot{stroke:white;stroke-width:2}</style>',
        '<text x="70" y="58" font-size="32" font-weight="700">Silta Alpha vs FastAPI: binary response throughput</text>',
        f'<text x="70" y="92" font-size="16" fill="#4b5563">{html.escape(sample)}. Identical in-memory response bytes.</text>',
        '<line x1="70" y1="122" x2="100" y2="122" stroke="#2563eb" stroke-width="4"/>',
        '<text x="110" y="128" font-size="15">Silta native Rust bytes</text>',
        '<line x1="330" y1="122" x2="360" y2="122" stroke="#ef5b2a" stroke-width="4"/>',
        '<text x="370" y="128" font-size="15">FastAPI Response, one worker</text>',
    ]

    for (endpoint, (title, size)), left in zip(PAYLOADS.items(), panel_lefts):
        selected = [point for point in points if point.endpoint == endpoint]
        max_rate = max(point.gib_per_sec for point in selected) * 1.12
        max_concurrency = max(point.concurrency for point in selected)

        def x(value: int) -> float:
            return left + value / max_concurrency * panel_width

        def y(value: float) -> float:
            return panel_top + panel_height - value / max_rate * panel_height

        lines.append(f'<text x="{left}" y="{panel_top - 24}" font-size="22" font-weight="700">{html.escape(title)}</text>')
        lines.append(f'<text x="{left}" y="{panel_top - 4}" font-size="13" fill="#6b7280">{size:,} bytes per response</text>')
        for tick in range(6):
            value = max_rate * tick / 5
            yy = y(value)
            lines.append(f'<line class="grid" x1="{left}" y1="{yy:.1f}" x2="{left + panel_width}" y2="{yy:.1f}"/>')
            lines.append(f'<text x="{left - 10}" y="{yy + 5:.1f}" text-anchor="end" font-size="12">{value:.1f}</text>')
        for concurrency in sorted({point.concurrency for point in selected}):
            xx = x(concurrency)
            lines.append(f'<line class="grid" x1="{xx:.1f}" y1="{panel_top}" x2="{xx:.1f}" y2="{panel_top + panel_height}"/>')
            lines.append(f'<text x="{xx:.1f}" y="{panel_top + panel_height + 24}" text-anchor="middle" font-size="12">{concurrency}</text>')
        lines.append(f'<line class="axis" x1="{left}" y1="{panel_top + panel_height}" x2="{left + panel_width}" y2="{panel_top + panel_height}"/>')

        for label in ("Silta", "FastAPI"):
            series = [point for point in selected if point.label == label]
            path_data = " ".join(
                f'{"M" if index == 0 else "L"} {x(point.concurrency):.1f} {y(point.gib_per_sec):.1f}'
                for index, point in enumerate(series)
            )
            lines.append(f'<path class="line" d="{path_data}" stroke="{colors[label]}"/>')
            for point in series:
                lines.append(
                    f'<circle class="dot" cx="{x(point.concurrency):.1f}" cy="{y(point.gib_per_sec):.1f}" r="5" fill="{colors[label]}">'
                    f'<title>{html.escape(label)} c={point.concurrency}: {point.gib_per_sec:.2f} GiB/s, {point.rps:.0f} RPS, p99 {point.p99_ms:.1f} ms</title></circle>'
                )
        lines.append(f'<text x="{left + panel_width / 2}" y="{panel_top + panel_height + 54}" text-anchor="middle" font-size="14">concurrent connections</text>')

    lines.extend(
        [
            '<text x="28" y="385" transform="rotate(-90 28 385)" text-anchor="middle" font-size="14">GiB/s</text>',
            '<text x="70" y="708" font-size="13" fill="#6b7280">Python 3.14.7 | FastAPI 0.141.1 | Uvicorn 0.52.4 | Rust release build | oha 1.16</text>',
            '<text x="70" y="736" font-size="13" fill="#6b7280">Loopback, in-memory payloads, no filesystem or image encoding. Local Alpha evidence, not a general performance claim.</text>',
            "</svg>",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_markdown(path: Path, points: list[Point], sample: str) -> None:
    rows = [
        "# Binary response benchmark results",
        "",
        f"{sample.capitalize()}.",
        "",
        "| Payload | Silta peak | FastAPI peak | Ratio | Silta p99 at peak | FastAPI p99 at peak |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for endpoint, (title, _) in PAYLOADS.items():
        selected = [point for point in points if point.endpoint == endpoint]
        silta = max((point for point in selected if point.label == "Silta"), key=lambda point: point.gib_per_sec)
        fastapi = max((point for point in selected if point.label == "FastAPI"), key=lambda point: point.gib_per_sec)
        rows.append(
            f"| {title} | {silta.gib_per_sec:.2f} GiB/s | {fastapi.gib_per_sec:.2f} GiB/s | "
            f"{silta.gib_per_sec / fastapi.gib_per_sec:.2f}x | {silta.p99_ms:.1f} ms | {fastapi.p99_ms:.1f} ms |"
        )
    rows.extend(
        [
            "",
            "![Binary response throughput](media-throughput.svg)",
            "",
            "The runner validates MIME types, exact sizes, byte equality, and the BMP file structure before load generation.",
            "This is an Alpha engineering result from one local machine, not a general performance claim.",
        ]
    )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
