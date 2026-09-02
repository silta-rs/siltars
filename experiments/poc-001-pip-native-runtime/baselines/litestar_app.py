from litestar import Litestar, get


@get("/ping")
async def ping() -> dict[str, bool]:
    return {"ok": True}


app = Litestar(route_handlers=[ping])
