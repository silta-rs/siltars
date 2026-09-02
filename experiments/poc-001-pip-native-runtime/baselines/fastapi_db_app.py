import os
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
from fastapi import Body, FastAPI

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is required. Use scripts/run_fastapi_rates_baseline.sh "
        "to read credentials from the experiment PostgreSQL container."
    )
DATABASE_MIN_CONNECTIONS = int(os.environ.get("FASTAPI_DB_MIN_CONNECTIONS", "1"))
DATABASE_MAX_CONNECTIONS = int(os.environ.get("FASTAPI_DB_MAX_CONNECTIONS", "10"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=DATABASE_MIN_CONNECTIONS,
        max_size=DATABASE_MAX_CONNECTIONS,
    )
    try:
        yield
    finally:
        await app.state.pool.close()


app = FastAPI(lifespan=lifespan)


@app.get("/ping")
async def ping() -> dict[str, bool]:
    return {"ok": True}


@app.get("/rates")
async def list_rates() -> dict[str, list[dict[str, Any]]]:
    rows = await app.state.pool.fetch(
        """
        SELECT rate_type, asset_class, base, quote, rate::text, ts_utc, source
        FROM public.rates
        ORDER BY ts_utc DESC
        LIMIT 100
        """
    )
    return {"rates": [_json_row(row) for row in rows]}


@app.get("/rates/bulk")
async def list_rates_bulk() -> dict[str, Any]:
    rows = await app.state.pool.fetch(
        """
        SELECT
            r.id,
            r.rate_type,
            r.asset_class,
            r.base,
            r.quote,
            r.rate::text,
            r.ts_utc,
            r.source,
            s.provider,
            s.region,
            s.tier
        FROM public.rates AS r
        JOIN public.silta_rate_sources AS s ON s.source = r.source
        ORDER BY r.ts_utc DESC
        LIMIT 3000
        """
    )
    rates = [
        {
            "id": row["id"],
            "instrument": {
                "rate_type": row["rate_type"],
                "asset_class": row["asset_class"],
                "base": row["base"],
                "quote": row["quote"],
            },
            "value": {
                "rate": row["rate"],
                "ts_utc": row["ts_utc"].isoformat(),
            },
            "source": {
                "code": row["source"],
                "provider": row["provider"],
                "region": row["region"],
                "tier": row["tier"],
            },
        }
        for row in rows
    ]
    return {"count": len(rates), "rates": rates}


@app.get("/rates/{base}/{quote}")
async def get_rate(base: str, quote: str) -> dict[str, Any]:
    row = await app.state.pool.fetchrow(
        """
        SELECT rate_type, asset_class, base, quote, rate::text, ts_utc, source
        FROM public.rates
        WHERE base = $1 AND quote = $2
        ORDER BY ts_utc DESC
        LIMIT 1
        """,
        base.upper(),
        quote.upper(),
    )
    return _json_row(row) if row else {"missing": True}


@app.get("/setting")
async def get_setting() -> dict[str, Any]:
    row = await app.state.pool.fetchrow(
        """
        SELECT id, name, value, version
        FROM public.silta_settings
        WHERE id = 1
        """
    )
    return dict(row)


@app.patch("/setting")
async def patch_setting(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    row = await app.state.pool.fetchrow(
        """
        UPDATE public.silta_settings
        SET value = $1,
            version = version + 1
        WHERE id = 1
        RETURNING id, name, value, version
        """,
        str(payload.get("value", "patched")),
    )
    return dict(row)


@app.post("/echo")
async def create_echo(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    return {"method": "POST", "payload": payload}


@app.put("/echo/{item_id}")
async def replace_echo(
    item_id: int, payload: dict[str, Any] = Body(default_factory=dict)
) -> dict[str, Any]:
    return {"method": "PUT", "item_id": item_id, "payload": payload}


@app.patch("/echo/{item_id}")
async def update_echo(
    item_id: int, payload: dict[str, Any] = Body(default_factory=dict)
) -> dict[str, Any]:
    return {"method": "PATCH", "item_id": item_id, "payload": payload}


@app.delete("/echo/{item_id}")
async def delete_echo(item_id: int) -> dict[str, Any]:
    return {"method": "DELETE", "item_id": item_id, "deleted": True}


def _json_row(row: Any) -> dict[str, Any]:
    payload = dict(row)
    for key, value in payload.items():
        if hasattr(value, "isoformat"):
            payload[key] = value.isoformat()
    return payload
