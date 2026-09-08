"""Silta definition for the native MySQL read benchmark."""

from silta import App

app = App(name="mysql-read-benchmark")


@app.get("/mysql/events/{limit}", python=False)
def list_mysql_events():
    return {"count": 0, "rows": []}
