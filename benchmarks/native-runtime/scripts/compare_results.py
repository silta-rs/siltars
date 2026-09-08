from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Silta and FastAPI results.")
    parser.add_argument("--silta", type=Path, required=True)
    parser.add_argument("--fastapi", type=Path, required=True)
    parser.add_argument("--min-speedup", type=float, default=1.01)
    args = parser.parse_args()

    silta = json.loads(args.silta.read_text(encoding="utf-8"))
    fastapi = json.loads(args.fastapi.read_text(encoding="utf-8"))

    silta_rps = float(silta["requests_per_second"])
    fastapi_rps = float(fastapi["requests_per_second"])
    speedup = silta_rps / fastapi_rps if fastapi_rps else 0.0

    print(f"Silta RPS:   {silta_rps:.2f}")
    print(f"FastAPI RPS: {fastapi_rps:.2f}")
    print(f"Speedup:     {speedup:.2f}x")

    if speedup < args.min_speedup:
        print(
            f"FAIL: expected Silta to be at least {args.min_speedup:.2f}x FastAPI"
        )
        return 1

    print("PASS: Silta is faster than FastAPI for this measured workload")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
