# Silta

> Write Python. Run Rust.

Silta is a Pre-Alpha runtime-first backend framework for Python developers,
powered by a native Rust execution engine.

The Python distribution name is `siltars`; the import package and CLI are
`silta`.

```bash
pip install siltars
```

This package is not published on PyPI yet. The first public release will be a
Pre-Alpha package and should not be treated as production-ready.

```python
from silta import App

app = App(name="hello")


@app.get("/hello", response={"hello": "world"})
async def hello():
    return {"hello": "world"}
```

Project repository:
<https://github.com/silta-rs/siltars>

Documentation:
<https://github.com/silta-rs/siltars/tree/dev/docs>

License:
Apache-2.0

Original initiator:
[Serrka](https://github.com/Sergey2Gnezdilov/)
