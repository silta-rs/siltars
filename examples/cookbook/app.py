"""Runnable examples for docs/cookbook.md; crash routes are for local testing."""
import asyncio
import os

from silta import App

app = App(name="cookbook")


@app.get("/health", response={"status": "ok"})
def health():
    pass


@app.post("/echo")
async def echo(request):
    return {"received": request["body"]}


@app.get("/async")
async def async_example():
    await asyncio.sleep(0.01)
    return {"completed": True}


@app.get("/worker")
def worker():
    return {"pid": os.getpid()}


@app.post("/slow")
async def slow():
    await asyncio.sleep(60)
    return {"completed": True}


@app.post("/crash")
def crash():
    os._exit(7)
