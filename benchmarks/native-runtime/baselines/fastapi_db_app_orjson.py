"""Optimized FastAPI baseline: same routes and SQL as fastapi_db_app.py for the
PostgreSQL rate paths and the mock catalog, served through ORJSONResponse.

The methodology in docs/architecture/performance.md asks for a conventional and
an optimized FastAPI implementation. This is the optimized one: no Pydantic
response model, no jsonable_encoder pass, rows converted to dicts once and
encoded by orjson (datetimes emitted natively).
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from baselines.mock_catalog import MOCK_RATES, clamp

DATABASE_URL = os.environ.get("DATABASE_URL")
DATABASE_MIN_CONNECTIONS = int(os.environ.get("FASTAPI_DB_MIN_CONNECTIONS", "1"))
DATABASE_MAX_CONNECTIONS = int(os.environ.get("FASTAPI_DB_MAX_CONNECTIONS", "10"))

RATE_COLUMNS = "rate_type, asset_class, base, quote, rate::text, ts_utc, source"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = None
    if DATABASE_URL:
        app.state.pool = await asyncpg.create_pool(
            DATABASE_URL, min_size=DATABASE_MIN_CONNECTIONS, max_size=DATABASE_MAX_CONNECTIONS
        )
    try:
        yield
    finally:
        if app.state.pool is not None:
            await app.state.pool.close()


app = FastAPI(lifespan=lifespan, default_response_class=ORJSONResponse)


def _pool():
    if app.state.pool is None:
        return ORJSONResponse({"error": "database is not configured for this baseline"}, status_code=503)
    return app.state.pool


@app.get("/ping")
async def ping() -> ORJSONResponse:
    return ORJSONResponse({"ok": True})


@app.get("/mock/rates/{count}")
async def mock_rates(count: int) -> ORJSONResponse:
    n = clamp(count)
    return ORJSONResponse({"count": n, "rates": MOCK_RATES[:n]})


@app.get("/rates")
async def list_rates() -> ORJSONResponse:
    pool = _pool()
    if isinstance(pool, ORJSONResponse):
        return pool
    rows = await pool.fetch(
        f"SELECT {RATE_COLUMNS} FROM public.rates ORDER BY ts_utc DESC LIMIT 100"
    )
    return ORJSONResponse({"rates": [dict(row) for row in rows]})


@app.get("/rates/bulk")
async def list_rates_bulk() -> ORJSONResponse:
    pool = _pool()
    if isinstance(pool, ORJSONResponse):
        return pool
    rows = await pool.fetch(
        """
        SELECT r.id, r.rate_type, r.asset_class, r.base, r.quote, r.rate::text, r.ts_utc, r.source,
               s.provider, s.region, s.tier
        FROM public.rates AS r
        JOIN public.silta_rate_sources AS s ON s.source = r.source
        ORDER BY r.ts_utc DESC
        LIMIT 3000
        """
    )
    rates: list[dict[str, Any]] = [
        {
            "id": row[0],
            "instrument": {"rate_type": row[1], "asset_class": row[2], "base": row[3], "quote": row[4]},
            "value": {"rate": row[5], "ts_utc": row[6]},
            "source": {"code": row[7], "provider": row[8], "region": row[9], "tier": row[10]},
        }
        for row in rows
    ]
    return ORJSONResponse({"count": len(rates), "rates": rates})


@app.get("/rates/{base}/{quote}")
async def get_rate(base: str, quote: str) -> ORJSONResponse:
    pool = _pool()
    if isinstance(pool, ORJSONResponse):
        return pool
    row = await pool.fetchrow(
        f"SELECT {RATE_COLUMNS} FROM public.rates WHERE base = $1 AND quote = $2 ORDER BY ts_utc DESC LIMIT 1",
        base.upper(),
        quote.upper(),
    )
    return ORJSONResponse(dict(row) if row else {"missing": True})
