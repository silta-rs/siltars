"""Deterministic in-memory catalog shared by the FastAPI baselines.

Mirrors `build_mock_rates` in the Rust runtime field for field, so that
`GET /mock/rates/{count}` returns byte-identical bodies from every server.
"""
from __future__ import annotations

from typing import Any

MOCK_RATES_MAX = 10_000
_PAIRS = [
    ("EUR", "USD", 108_000_000),
    ("USD", "EUR", 92_500_000),
    ("GBP", "USD", 127_000_000),
    ("USD", "JPY", 14_650_000_000),
    ("BTC", "USD", 6_500_000_000_000),
]


def build_mock_rates(count: int = MOCK_RATES_MAX) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i in range(count):
        base, quote, rate_micro = _PAIRS[i % len(_PAIRS)]
        rate = rate_micro + (i % 1000) * 1000
        seconds = i % 86_400
        rows.append(
            {
                "id": i + 1,
                "instrument": {"rate_type": "spot", "asset_class": "fiat", "base": base, "quote": quote},
                "value": {
                    "rate": f"{rate // 100_000_000}.{rate % 100_000_000:08d}",
                    "ts_utc": f"2026-01-01T{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}+00:00",
                },
                "source": {
                    "code": "silta-poc-seed",
                    "provider": "Silta POC Market Data",
                    "region": "local",
                    "tier": "alpha",
                },
            }
        )
    return rows


MOCK_RATES = build_mock_rates()


def clamp(count: int) -> int:
    return max(1, min(int(count), MOCK_RATES_MAX))
