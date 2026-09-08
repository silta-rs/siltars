"""Optimized single-worker FastAPI baseline for the MySQL read benchmark."""

import os
from contextlib import asynccontextmanager

import asyncmy
from fastapi import FastAPI, HTTPException
from fastapi.responses import ORJSONResponse

MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "53306"))
MYSQL_POOL_SIZE = int(os.environ.get("MYSQL_POOL_SIZE", "32"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await asyncmy.create_pool(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user="silta",
        password="silta",
        db="silta_bench",
        minsize=MYSQL_POOL_SIZE,
        maxsize=MYSQL_POOL_SIZE,
        autocommit=True,
        stmt_cache_size=32,
    )
    try:
        yield
    finally:
        app.state.pool.close()
        await app.state.pool.wait_closed()


app = FastAPI(lifespan=lifespan, default_response_class=ORJSONResponse)


@app.get("/mysql/events/{limit}", response_class=ORJSONResponse)
async def list_mysql_events(limit: int):
    queries = {
        1: "SELECT id, group_id, metric, label FROM benchmark_events ORDER BY id LIMIT 1",
        100: "SELECT id, group_id, metric, label FROM benchmark_events ORDER BY id LIMIT 100",
        1000: "SELECT id, group_id, metric, label FROM benchmark_events ORDER BY id LIMIT 1000",
    }
    query = queries.get(limit)
    if query is None:
        raise HTTPException(status_code=400, detail="limit must be 1, 100, or 1000")
    async with app.state.pool.acquire() as connection:
        async with connection.cursor() as cursor:
            await cursor.execute(query, ())
            records = await cursor.fetchall()

    rows = [
        {"id": row[0], "group_id": row[1], "metric": row[2], "label": row[3]}
        for row in records
    ]
    return ORJSONResponse({"count": len(rows), "rows": rows})
