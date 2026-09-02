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
