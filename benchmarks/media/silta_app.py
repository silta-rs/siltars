"""Silta definition for binary and image response benchmarks."""

from silta import App

app = App(name="media-benchmark")


@app.get("/media/blob/64k", python=False)
def get_binary_64k():
    return None


@app.get("/media/blob/1m", python=False)
def get_binary_1m():
    return None


@app.get("/media/image.bmp", python=False)
def get_benchmark_bmp():
    return None
