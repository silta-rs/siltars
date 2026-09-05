import os
from contextlib import asynccontextmanager
from typing import Any

from urllib.parse import urlsplit

import asyncpg
from fastapi import Body, FastAPI, HTTPException

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is required. Use scripts/run_fastapi_rates_baseline.sh "
        "to read credentials from the experiment PostgreSQL container."
    )
DATABASE_MIN_CONNECTIONS = int(os.environ.get("FASTAPI_DB_MIN_CONNECTIONS", "1"))
DATABASE_MAX_CONNECTIONS = int(os.environ.get("FASTAPI_DB_MAX_CONNECTIONS", "10"))
# Optional ClickHouse path for the experimental /ch/* routes. clickhouse-connect
# is the official driver; its async client rides on aiohttp, and the per-host
# connector limit is raised to match the PostgreSQL pool size so both baselines
# get the same number of in-flight database requests.
CLICKHOUSE_URL = os.environ.get("CLICKHOUSE_URL")
CLICKHOUSE_DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "silta_poc")
CLICKHOUSE_MAX_CONNECTIONS = int(os.environ.get("FASTAPI_CH_MAX_CONNECTIONS", str(DATABASE_MAX_CONNECTIONS)))
CLICKHOUSE_MAX_THREADS = os.environ.get("CLICKHOUSE_MAX_THREADS")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=DATABASE_MIN_CONNECTIONS,
        max_size=DATABASE_MAX_CONNECTIONS,
    )
    app.state.clickhouse = None
    if CLICKHOUSE_URL:
        import clickhouse_connect

        parts = urlsplit(CLICKHOUSE_URL)
        app.state.clickhouse = await clickhouse_connect.get_async_client(
            host=parts.hostname or "127.0.0.1",
            port=parts.port or 8123,
            username=parts.username or "default",
            password=parts.password or "",
            database=CLICKHOUSE_DATABASE,
            secure=parts.scheme == "https",
            connector_limit=CLICKHOUSE_MAX_CONNECTIONS,
            connector_limit_per_host=CLICKHOUSE_MAX_CONNECTIONS,
            settings={"max_threads": int(CLICKHOUSE_MAX_THREADS)} if CLICKHOUSE_MAX_THREADS else None,
        )
    try:
        yield
    finally:
        await app.state.pool.close()
        if app.state.clickhouse is not None:
            await app.state.clickhouse.close()


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


CLICKHOUSE_RATE_COLUMNS = (
    "rate_type, asset_class, base, quote, toString(rate) AS rate, toString(ts_utc) AS ts_utc, source"
)


def _clickhouse():
    client = getattr(app.state, "clickhouse", None)
    if client is None:
        raise HTTPException(status_code=503, detail="clickhouse is not configured for this baseline")
    return client


async def _clickhouse_latest(limit: int) -> dict[str, list[dict[str, Any]]]:
    result = await _clickhouse().query(
        f"SELECT {CLICKHOUSE_RATE_COLUMNS} FROM rates ORDER BY rates.ts_utc DESC LIMIT {int(limit)}"
    )
    return {"rates": [dict(zip(result.column_names, row)) for row in result.result_rows]}


@app.get("/ch/rates")
async def ch_list_rates() -> dict[str, list[dict[str, Any]]]:
    return await _clickhouse_latest(100)


@app.get("/ch/rates/1000")
async def ch_list_rates_1000() -> dict[str, list[dict[str, Any]]]:
    return await _clickhouse_latest(1000)


@app.get("/ch/rates/{base}/{quote}")
async def ch_get_rate(base: str, quote: str) -> dict[str, Any]:
    result = await _clickhouse().query(
        f"SELECT {CLICKHOUSE_RATE_COLUMNS} FROM rates "
        "WHERE base = {base:String} AND quote = {quote:String} ORDER BY rates.ts_utc DESC LIMIT 1",
        parameters={"base": base.upper(), "quote": quote.upper()},
    )
    if not result.result_rows:
        return {"missing": True}
    return dict(zip(result.column_names, result.result_rows[0]))


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


@app.post("/python/echo")
async def python_echo(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    return {"bridge": "python", "payload": payload}


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
