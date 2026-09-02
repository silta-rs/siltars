"""Proposed Silta POC app.

This file documents the target Python developer experience. It is not expected
to run until the native runtime prototype implements the CLI/runtime path.
"""

from silta import App

app = App()


@app.get("/ping")
def ping():
    return {"ok": True}


@app.get("/users")
def list_users():
    return {"users": []}


@app.get("/rates")
def list_rates():
    return {"rates": []}


@app.get("/rates/{base}/{quote}")
def get_rate():
    return {"base": "EUR", "quote": "USD", "rate": "1.0"}


@app.post("/users")
def create_user():
    return {"id": 1, "name": "Ada", "email": "ada@example.com"}


@app.put("/users/{id}")
def replace_user():
    return {"id": 1, "name": "Ada Lovelace", "email": "ada@example.com"}


@app.patch("/users/{id}")
def update_user():
    return {"id": 1, "name": "Ada", "email": "ada@example.com"}


@app.delete("/users/{id}")
def delete_user():
    return {"deleted": True}
