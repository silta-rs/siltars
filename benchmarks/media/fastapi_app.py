"""In-memory FastAPI baseline for binary and image responses."""

from fastapi import FastAPI
from fastapi.responses import Response


def benchmark_bytes(size: int) -> bytes:
    return bytes(index % 251 for index in range(size))


def benchmark_bmp(width: int, height: int) -> bytes:
    row_size = width * 3
    image_size = row_size * height
    file_size = 54 + image_size
    image = bytearray(b"BM")
    image.extend(file_size.to_bytes(4, "little"))
    image.extend(bytes(4))
    image.extend((54).to_bytes(4, "little"))
    image.extend((40).to_bytes(4, "little"))
    image.extend(width.to_bytes(4, "little", signed=True))
    image.extend(height.to_bytes(4, "little", signed=True))
    image.extend((1).to_bytes(2, "little"))
    image.extend((24).to_bytes(2, "little"))
    image.extend((0).to_bytes(4, "little"))
    image.extend(image_size.to_bytes(4, "little"))
    image.extend((2835).to_bytes(4, "little", signed=True))
    image.extend((2835).to_bytes(4, "little", signed=True))
    image.extend(bytes(8))
    for y in range(height):
        for x in range(width):
            image.extend(((x + y) % 256, (x * 2) % 256, (y * 2) % 256))
    return bytes(image)


BINARY_64K = benchmark_bytes(64 * 1024)
BINARY_1M = benchmark_bytes(1024 * 1024)
BENCHMARK_BMP = benchmark_bmp(512, 512)

app = FastAPI()


@app.get("/media/blob/64k", response_class=Response)
async def get_binary_64k():
    return Response(BINARY_64K, media_type="application/octet-stream", headers={"Cache-Control": "no-store"})


@app.get("/media/blob/1m", response_class=Response)
async def get_binary_1m():
    return Response(BINARY_1M, media_type="application/octet-stream", headers={"Cache-Control": "no-store"})


@app.get("/media/image.bmp", response_class=Response)
async def get_benchmark_bmp():
    return Response(BENCHMARK_BMP, media_type="image/bmp", headers={"Cache-Control": "no-store"})
