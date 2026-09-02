"""Silta POC app used by the native Rust runtime experiment."""

from silta import App

app = App()


@app.get("/ping")
def ping():
    return {"ok": True}


@app.get("/users", response={"users": []})
def list_users():
    return {"users": []}


@app.get("/rates")
def list_rates():
    return {"rates": []}


@app.get("/rates/{base}/{quote}")
def get_rate():
    return {"base": "EUR", "quote": "USD", "rate": "1.0"}


@app.get("/setting")
def get_setting():
    return {"id": 1, "name": "alpha", "value": "enabled"}


@app.patch("/setting")
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
