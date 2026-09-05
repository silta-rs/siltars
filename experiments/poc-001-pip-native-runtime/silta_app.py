"""Silta POC app used by the native Rust runtime experiment."""

import time

from silta import App

app = App()


@app.get("/ping", python=False)
def ping():
    return {"ok": True}


@app.get("/users", response={"users": []})
def list_users():
    return {"users": []}


@app.get("/rates", python=False)
def list_rates():
    return {"rates": []}


@app.get("/rates/bulk", python=False)
def list_rates_bulk():
    return {"count": 0, "rates": []}


@app.get("/rates/{base}/{quote}", python=False)
def get_rate():
    return {"base": "EUR", "quote": "USD", "rate": "1.0"}


@app.get("/setting", python=False)
def get_setting():
    return {"id": 1, "name": "alpha", "value": "enabled"}


@app.post("/python/echo", python=True)
def python_echo(request):
    return {"bridge": "python", "payload": request["body"]}


@app.get("/ok", python=True)
def bridge_ok():
    return {"ok": True}


@app.get("/slow", python=True)
def bridge_slow():
    time.sleep(1)
    return {"slow": True}


@app.get("/prints", python=True)
def bridge_prints():
    print("handler stdout noise")
    return {"printed": True}


@app.post("/echo", python=False)
def create_echo():
    return {"method": "POST", "payload": {}}


@app.patch("/setting", python=False)
def patch_setting():
    return {"id": 1, "name": "alpha", "value": "patched"}


@app.post("/users", response={"id": 1, "name": "Ada", "email": "ada@example.com"})
def create_user():
    return {"id": 1, "name": "Ada", "email": "ada@example.com"}


@app.put(
    "/users/{id}",
    response={"id": 1, "name": "Ada Lovelace", "email": "ada@example.com"},
)
def replace_user():
    return {"id": 1, "name": "Ada Lovelace", "email": "ada@example.com"}


@app.patch("/users/{id}", response={"id": 1, "name": "Ada", "email": "ada@example.com"})
def update_user():
    return {"id": 1, "name": "Ada", "email": "ada@example.com"}


@app.delete("/users/{id}", response={"deleted": True})
def delete_user():
    return {"deleted": True}
