"""Alternating-run benchmark orchestrator following docs/architecture/performance.md.

For every run r in 1..R and every cell, the targets are visited in a rotated
order so that no stack always benefits from the same host phase. Each point
runs oha for a fixed duration and records raw JSON, RSS and CPU seconds of the
whole process tree of the target.

Usage: python scripts/bench_program.py config.json (see run_mock_catalog_benchmark.sh)
config = {
  "output_dir": "...", "duration": "30s", "runs": 3, "concurrency": 50,
  "targets": [{"name": "silta", "url": "http://127.0.0.1:8104", "pid": 123}, ...],
  "cells": [{"name": "one-row-hot", "path": "/rates/EUR/USD"} |
            {"name": "one-row-random", "rand_regex": "/rates/(EUR|USD)/(USD|JPY)"},
            {"name": "post-echo", "path": "/echo", "method": "POST", "body": "{}"}]
}
"""
from __future__ import annotations

import csv
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path


def tree_pids(pid: int) -> list[int]:
    out = [pid]
    try:
        kids = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True).stdout.split()
    except Exception:
        kids = []
    for k in kids:
        out += tree_pids(int(k))
    return out


def cputime_seconds(text: str) -> float:
    parts = text.strip().split(":")
    parts = [float(p) for p in parts]
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return sec


def sample(pid: int) -> tuple[int, float]:
    """Return (rss_kb_sum, cpu_seconds_sum) over the process tree."""
    rss = 0
    cpu = 0.0
    for p in tree_pids(pid):
        r = subprocess.run(["ps", "-o", "rss=,cputime=", "-p", str(p)], capture_output=True, text=True).stdout.split()
        if len(r) >= 2:
            rss += int(r[0])
            cpu += cputime_seconds(r[1])
    return rss, cpu


def run_oha(url: str, duration: str, conc: int, method: str, body: str | None, rand: bool) -> dict:
    cmd = ["oha", "-z", duration, "-c", str(conc), "--no-tui", "--output-format", "json", "-m", method]
    if body is not None:
        cmd += ["-H", "content-type: application/json", "-d", body]
    if rand:
        cmd += ["--rand-regex-url", url]
    else:
        cmd += [url]
    out = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(out.stdout)


def main() -> int:
    cfg = json.loads(Path(sys.argv[1]).read_text())
    out_dir = Path(cfg["output_dir"])
    (out_dir / "raw").mkdir(parents=True, exist_ok=True)
    duration = cfg.get("duration", "30s")
    runs = int(cfg.get("runs", 3))
    conc = int(cfg.get("concurrency", 50))
    targets = cfg["targets"]
    cells = cfg["cells"]
    points: list[dict] = []
    log = (out_dir / "progress.log").open("a")

    def say(msg: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {msg}"
        print(line, flush=True)
        log.write(line + "\n")
        log.flush()

    say(f"start: {len(cells)} cells x {len(targets)} targets x {runs} runs x {duration} at c={conc}")
    for r in range(runs):
        order = targets[r % len(targets):] + targets[: r % len(targets)]
        for cell in cells:
            for tgt in order:
                url = tgt["url"] + cell.get("path", cell.get("rand_regex", "/"))
                rand = "rand_regex" in cell
                # short warm-up on this exact target/cell
                run_oha(url, "2s", min(conc, 20), cell.get("method", "GET"), cell.get("body"), rand)
                rss0, cpu0 = sample(tgt["pid"])
                t0 = time.time()
                data = run_oha(url, duration, conc, cell.get("method", "GET"), cell.get("body"), rand)
                elapsed = time.time() - t0
                rss1, cpu1 = sample(tgt["pid"])
                raw_path = out_dir / "raw" / f"{cell['name']}-{tgt['name']}-run{r+1}.json"
                raw_path.write_text(json.dumps(data))
                s = data["summary"]
                lp = data.get("latencyPercentiles") or {}
                codes = data.get("statusCodeDistribution") or {}
                total = sum(codes.values()) or 1
                ok = codes.get("200", 0) / total * 100
                point = {
                    "run": r + 1,
                    "cell": cell["name"],
                    "target": tgt["name"],
                    "concurrency": conc,
                    "duration_s": round(elapsed, 1),
                    "rps": round(s["requestsPerSec"], 1),
                    "p50_ms": round(lp.get("p50", 0) * 1000, 3),
                    "p95_ms": round(lp.get("p95", 0) * 1000, 3),
                    "p99_ms": round(lp.get("p99", 0) * 1000, 3),
                    "ok_pct": round(ok, 2),
                    "codes": json.dumps(codes, sort_keys=True),
                    "bytes_per_resp": round(s.get("sizePerRequest") or (s.get("sizeTotal", 0) / max(1, total))),
                    "cpu_seconds": round(cpu1 - cpu0, 2),
                    "cpu_cores_used": round((cpu1 - cpu0) / max(elapsed, 0.001), 2),
                    "cpu_ms_per_1k_req": round((cpu1 - cpu0) / max(1, s["requestsPerSec"] * elapsed) * 1e6, 2),
                    "rss_kb_after": rss1,
                }
                points.append(point)
                say(f"run{r+1} {cell['name']:<16} {tgt['name']:<16} rps={point['rps']:>9} p99={point['p99_ms']:>8}ms ok={point['ok_pct']}% cpu_cores={point['cpu_cores_used']} rss={rss1//1024}MB")
                with (out_dir / "points.csv").open("w", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=list(points[0].keys()))
                    w.writeheader()
                    w.writerows(points)

    # medians + dispersion
    rows = []
    for cell in cells:
        for tgt in targets:
            pts = [p for p in points if p["cell"] == cell["name"] and p["target"] == tgt["name"]]
            if not pts:
                continue
            rps = [p["rps"] for p in pts]
            rows.append({
                "cell": cell["name"], "target": tgt["name"], "runs": len(pts),
                "rps_median": round(statistics.median(rps), 1),
                "rps_min": min(rps), "rps_max": max(rps),
                "rps_spread_pct": round((max(rps) - min(rps)) / statistics.median(rps) * 100, 1),
                "p50_ms_median": round(statistics.median(p["p50_ms"] for p in pts), 3),
                "p95_ms_median": round(statistics.median(p["p95_ms"] for p in pts), 3),
                "p99_ms_median": round(statistics.median(p["p99_ms"] for p in pts), 3),
                "ok_pct_min": min(p["ok_pct"] for p in pts),
                "cpu_cores_median": round(statistics.median(p["cpu_cores_used"] for p in pts), 2),
                "cpu_ms_per_1k_req_median": round(statistics.median(p["cpu_ms_per_1k_req"] for p in pts), 2),
                "rss_mb_max": max(p["rss_kb_after"] for p in pts) // 1024,
                "bytes_per_resp": pts[0]["bytes_per_resp"],
            })
    with (out_dir / "medians.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    say("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
