from silta import App

app = App(name="hello-world")


@app.get("/hello")
async def hello():
    return {"hello": "world"}


if __name__ == "__main__":
    print(app.describe())
